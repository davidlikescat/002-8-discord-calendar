"""등록 호출 ② — Claude CLI + Google Calendar MCP.

추출된 일정 객체를 받아 Calendar MCP로 등록/수정/삭제한다.
중복 판정과 KST 고정은 프롬프트에서 지시한다.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from claude_runner import parse_json_loose, run_claude
from config import CLAUDE_TIMEOUT_REGISTER
from extractor import ExtractedEvent
from prompts import build_delete_prompt, build_register_prompt, build_update_prompt

log = logging.getLogger(__name__)


@dataclass
class RegisterResult:
    ok: bool
    duplicate: bool = False
    event_id: str | None = None
    html_link: str | None = None
    summary: str | None = None
    start: str | None = None
    end: str | None = None
    error: str | None = None
    raw_text: str = ""


def _event_to_payload(ev: ExtractedEvent) -> dict:
    return {
        "title": ev.title,
        "start": ev.start,
        "end": ev.end,
        "all_day": ev.all_day,
        "location": ev.location,
        "description": ev.description,
        "confidence": ev.confidence,
    }


async def register_event(ev: ExtractedEvent) -> RegisterResult:
    prompt = build_register_prompt(_event_to_payload(ev))
    res = await run_claude(prompt, timeout=CLAUDE_TIMEOUT_REGISTER)
    if not res.ok:
        return RegisterResult(ok=False, error=res.error, raw_text=res.text[:500])

    parsed = parse_json_loose(res.text)
    if not isinstance(parsed, dict):
        return RegisterResult(ok=False, error="JSON 파싱 실패", raw_text=res.text[:500])

    return RegisterResult(
        ok=bool(parsed.get("ok")),
        duplicate=bool(parsed.get("duplicate", False)),
        event_id=parsed.get("event_id"),
        html_link=parsed.get("html_link"),
        summary=parsed.get("summary") or ev.title,
        start=parsed.get("start") or ev.start,
        end=parsed.get("end") or ev.end,
        error=parsed.get("error"),
        raw_text=res.text,
    )


async def update_event(event_id: str, patch_text: str) -> RegisterResult:
    prompt = build_update_prompt(event_id, patch_text)
    res = await run_claude(prompt, timeout=CLAUDE_TIMEOUT_REGISTER)
    if not res.ok:
        return RegisterResult(ok=False, error=res.error, raw_text=res.text[:500])

    parsed = parse_json_loose(res.text)
    if not isinstance(parsed, dict):
        return RegisterResult(ok=False, error="JSON 파싱 실패", raw_text=res.text[:500])
    return RegisterResult(
        ok=bool(parsed.get("ok")),
        event_id=parsed.get("event_id") or event_id,
        html_link=parsed.get("html_link"),
        summary=parsed.get("summary"),
        start=parsed.get("start"),
        end=parsed.get("end"),
        error=parsed.get("error"),
        raw_text=res.text,
    )


async def delete_event(event_id: str) -> RegisterResult:
    prompt = build_delete_prompt(event_id)
    res = await run_claude(prompt, timeout=CLAUDE_TIMEOUT_REGISTER)
    if not res.ok:
        return RegisterResult(ok=False, error=res.error, raw_text=res.text[:500])

    parsed = parse_json_loose(res.text)
    if not isinstance(parsed, dict):
        return RegisterResult(ok=False, error="JSON 파싱 실패", raw_text=res.text[:500])
    return RegisterResult(
        ok=bool(parsed.get("ok")),
        event_id=event_id,
        error=parsed.get("error"),
        raw_text=res.text,
    )
