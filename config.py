from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _env(key: str, default: str | None = None, required: bool = False) -> str:
    val = os.getenv(key, default)
    if required and not val:
        raise RuntimeError(f"환경변수 누락: {key}")
    return val  # type: ignore[return-value]


DISCORD_TOKEN = _env("DISCORD_TOKEN", required=True)
DISCORD_CHANNEL_ID = int(_env("DISCORD_CHANNEL_ID", required=True))

CLAUDE_BIN = _env("CLAUDE_BIN", "claude")
CLAUDE_WORK_DIR = _env("CLAUDE_WORK_DIR", str(BASE_DIR))
CLAUDE_TIMEOUT_EXTRACT = int(_env("CLAUDE_TIMEOUT_EXTRACT", "120"))
CLAUDE_TIMEOUT_REGISTER = int(_env("CLAUDE_TIMEOUT_REGISTER", "120"))

CALENDAR_ID = _env("CALENDAR_ID", "davidlikessangria@gmail.com")
TIMEZONE = _env("TIMEZONE", "Asia/Seoul")

CONFIDENCE_THRESHOLD = float(_env("CONFIDENCE_THRESHOLD", "0.6"))
DEFAULT_DURATION_MIN = int(_env("DEFAULT_DURATION_MIN", "60"))
CATCHUP_MAX_HOURS = int(_env("CATCHUP_MAX_HOURS", "72"))

DATA_DIR = (BASE_DIR / _env("DATA_DIR", "./data")).resolve()
LOG_DIR = (BASE_DIR / _env("LOG_DIR", "./logs")).resolve()
ATTACH_DIR = (BASE_DIR / _env("ATTACH_DIR", "./data/attachments")).resolve()

for p in (DATA_DIR, LOG_DIR, ATTACH_DIR):
    p.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "state.sqlite3"
LOG_FILE = LOG_DIR / "bot.log"
