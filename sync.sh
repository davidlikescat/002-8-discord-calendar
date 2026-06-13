#!/bin/bash
# Google Drive 원본 → 로컬 운영 폴더로 코드 동기화.
# launchd가 Google Drive(CloudStorage)에 접근 권한이 없어 운영은 ~/.discord-calendar/에서 한다.
# 코드 편집은 이 폴더에서, 변경 후 이 스크립트로 sync.
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)/"
DST="$HOME/.discord-calendar/"

mkdir -p "$DST"
rsync -av --delete \
  --exclude '.venv' \
  --exclude 'data' \
  --exclude 'logs' \
  --exclude '__pycache__' \
  --exclude '.env' \
  --exclude 'sync.sh' \
  "$SRC" "$DST"

echo
echo "==> 동기화 완료: $DST"
echo "==> requirements.txt가 바뀌었다면:"
echo "    $DST.venv/bin/python -m pip install -r $DST/requirements.txt"
echo "==> 봇 재시작:"
echo "    launchctl unload ~/Library/LaunchAgents/com.user.discord-calendar.plist"
echo "    launchctl load   ~/Library/LaunchAgents/com.user.discord-calendar.plist"
