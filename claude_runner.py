"""Claude CLI headless 호출 공용 모듈.

추출①·등록② 모두 동일한 진입점을 쓰되, 프롬프트와 타임아웃·허용 도구만 다르게 준다.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass

from config import CLAUDE_BIN, CLAUDE_WORK_DIR

log = logging.getLogger(__name__)


@dataclass
class ClaudeResult:
    ok: bool
    text: str
    error: str | None = None


async def run_claude(
    prompt: str,
    *,
    timeout: int,
    allowed_tools: list[str] | None = None,
    extra_args: list[str] | None = None,
) -> ClaudeResult:
    """`claude --print` 로 headless 호출.

    allowed_tools 미지정 시 --dangerously-skip-permissions로 전체 허용한다.
    (등록 호출은 MCP 도구가 필요하므로 기본값이 편하다.)
    """
    args: list[str] = [CLAUDE_BIN, "--print"]
    if allowed_tools is None:
        args.append("--dangerously-skip-permissions")
    else:
        for tool in allowed_tools:
            args.extend(["--allowedTools", tool])
    if extra_args:
        args.extend(extra_args)
    args.append(prompt)

    log.debug("claude args: %s", args[:4] + ["...(prompt %d chars)" % len(prompt)])

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=CLAUDE_WORK_DIR,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        return ClaudeResult(ok=False, text="", error=f"claude 타임아웃 ({timeout}s)")
    except FileNotFoundError:
        return ClaudeResult(ok=False, text="", error=f"claude 바이너리 없음: {CLAUDE_BIN}")

    out = stdout.decode("utf-8", errors="replace").strip()
    err = stderr.decode("utf-8", errors="replace").strip()

    if proc.returncode != 0:
        return ClaudeResult(ok=False, text=out, error=err or f"exit {proc.returncode}")
    return ClaudeResult(ok=True, text=out, error=None)


_JSON_BLOCK_RE = re.compile(r"\{.*\}|\[.*\]", re.DOTALL)
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def parse_json_loose(text: str) -> dict | list | None:
    """모델이 코드펜스·전후 잡설을 붙여도 JSON만 뽑아 파싱."""
    if not text:
        return None

    # 1) 코드펜스가 있으면 안쪽 우선
    m = _FENCE_RE.search(text)
    if m:
        candidate = m.group(1).strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # 2) 첫 { ... } 또는 [ ... ] 매치
    m = _JSON_BLOCK_RE.search(text)
    if m:
        candidate = m.group(0)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # 3) raw
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None
