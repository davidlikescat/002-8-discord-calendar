"""추출 호출 ① — 디스코드 메시지 → 일정 JSON.

이미지 첨부는 첨부 폴더에 다운로드한 뒤 경로를 프롬프트에 넣어 Claude CLI 비전이 읽도록 한다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import aiohttp

from claude_runner import parse_json_loose, run_claude
from config import ATTACH_DIR, CLAUDE_TIMEOUT_EXTRACT, TIMEZONE
from prompts import build_extract_prompt

log = logging.getLogger(__name__)

_KST = ZoneInfo(TIMEZONE)
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".heic", ".bmp"}


@dataclass
class ExtractedEvent:
    title: str
    start: str | None
    end: str | None
    all_day: bool
    location: str | None
    description: str | None
    confidence: float
    needs_clarification: bool
    clarification_reason: str | None

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "ExtractedEvent":
        return cls(
            title=str(raw.get("title") or "").strip(),
            start=raw.get("start"),
            end=raw.get("end"),
            all_day=bool(raw.get("all_day", False)),
            location=raw.get("location"),
            description=raw.get("description"),
            confidence=float(raw.get("confidence") or 0.0),
            needs_clarification=bool(raw.get("needs_clarification", False)),
            clarification_reason=raw.get("clarification_reason"),
        )

    def is_registrable(self) -> bool:
        if self.needs_clarification:
            return False
        if not self.title:
            return False
        if not self.start:
            return False
        return True


@dataclass
class ExtractResult:
    events: list[ExtractedEvent] = field(default_factory=list)
    ok: bool = True
    error: str | None = None
    raw_text: str = ""


async def _download_attachments(attachments, msg_id: int) -> list[str]:
    """디스코드 첨부 중 이미지를 로컬에 저장하고 경로 리스트 반환."""
    if not attachments:
        return []
    paths: list[str] = []
    out_dir = ATTACH_DIR / str(msg_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    async with aiohttp.ClientSession() as sess:
        for i, att in enumerate(attachments):
            filename = att.filename or f"img_{i}"
            ext = Path(filename).suffix.lower()
            if ext not in _IMAGE_EXTS:
                continue
            dest = out_dir / filename
            try:
                async with sess.get(att.url) as resp:
                    resp.raise_for_status()
                    dest.write_bytes(await resp.read())
                paths.append(str(dest))
            except Exception as e:  # noqa: BLE001
                log.warning("첨부 다운로드 실패 %s: %s", att.url, e)
    return paths


async def extract_from_message(message) -> ExtractResult:
    """discord.Message → 일정 추출 결과."""
    text = message.content or ""
    image_paths = await _download_attachments(message.attachments, message.id)

    if not text.strip() and not image_paths:
        return ExtractResult(events=[], ok=True)

    received_dt = message.created_at.astimezone(_KST)
    received_iso = received_dt.strftime("%Y-%m-%dT%H:%M:%S+09:00")
    received_human = received_dt.strftime("%Y년 %m월 %d일 (%a) %H:%M KST")

    prompt = build_extract_prompt(
        message_text=text,
        image_paths=image_paths,
        received_at_kst=f"{received_iso}  ({received_human})",
    )

    res = await run_claude(prompt, timeout=CLAUDE_TIMEOUT_EXTRACT)
    if not res.ok:
        log.error("extract claude 실패: %s", res.error)
        return ExtractResult(events=[], ok=False, error=res.error, raw_text=res.text)

    parsed = parse_json_loose(res.text)
    if parsed is None:
        return ExtractResult(
            events=[],
            ok=False,
            error="JSON 파싱 실패",
            raw_text=res.text[:500],
        )

    # {"events": [...]} 또는 [...] 둘 다 허용
    if isinstance(parsed, dict):
        items = parsed.get("events", [])
    elif isinstance(parsed, list):
        items = parsed
    else:
        items = []

    events = [ExtractedEvent.from_raw(it) for it in items if isinstance(it, dict)]
    return ExtractResult(events=events, ok=True, raw_text=res.text)


def now_kst() -> datetime:
    return datetime.now(tz=_KST)
