#!/bin/bash
# 002-8 디스코드 일정 봇 — launchd/프로세스 상태 점검 (캡처용)
# 실행: bash status.sh

LABEL="com.user.discord-calendar"
RUNDIR="$HOME/.discord-calendar"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

# 색상
B=$'\033[1m'; D=$'\033[2m'; G=$'\033[32m'; R=$'\033[31m'; Y=$'\033[33m'; C=$'\033[36m'; N=$'\033[0m'
LINE="${D}────────────────────────────────────────────────────────${N}"

echo
echo "${B}${C}  002-8 디스코드 일정 봇  상태 점검${N}   ${D}$(date '+%Y-%m-%d %H:%M:%S')${N}"
echo "$LINE"

# 1) launchd 로드 상태
ENTRY=$(launchctl list | grep "$LABEL")
if [ -n "$ENTRY" ]; then
  PID=$(echo "$ENTRY" | awk '{print $1}')
  EXIT=$(echo "$ENTRY" | awk '{print $2}')
  if [ "$PID" != "-" ]; then
    echo "  ${B}launchd${N}      ${G}● LOADED${N}   PID ${B}$PID${N}   last-exit $EXIT"
  else
    echo "  ${B}launchd${N}      ${Y}● LOADED (실행 안 됨)${N}   last-exit ${R}$EXIT${N}"
  fi
else
  echo "  ${B}launchd${N}      ${R}● NOT LOADED${N}"
  PID=""
fi

# 2) plist 설치 여부
if [ -f "$PLIST" ]; then
  echo "  ${B}plist${N}        ${G}설치됨${N}   ${D}$PLIST${N}"
else
  echo "  ${B}plist${N}        ${R}없음${N}"
fi

# 3) 프로세스 상세 (가동시간/메모리)
if [ -n "$PID" ] && [ "$PID" != "-" ]; then
  PS=$(ps -o etime=,rss=,command= -p "$PID" 2>/dev/null)
  ET=$(echo "$PS" | awk '{print $1}')
  RSS=$(echo "$PS" | awk '{printf "%.1f", $2/1024}')
  echo "  ${B}프로세스${N}     가동 ${B}$ET${N}   메모리 ${B}${RSS}MB${N}"
fi

# 4) 실행 디렉토리
if [ -d "$RUNDIR" ]; then
  echo "  ${B}실행 위치${N}    ${G}$RUNDIR${N}"
else
  echo "  ${B}실행 위치${N}    ${R}$RUNDIR (없음)${N}"
fi

echo "$LINE"

# 5) 최근 로그 (마지막 6줄)
LOG="$RUNDIR/logs/bot.log"
echo "  ${B}최근 로그${N}  ${D}($LOG)${N}"
if [ -f "$LOG" ]; then
  tail -n 6 "$LOG" | sed "s/^/    ${D}│${N} /"
else
  echo "    ${D}│${N} ${Y}로그 파일 없음${N}"
fi

echo "$LINE"

# 6) 종합 판정
if [ -n "$PID" ] && [ "$PID" != "-" ]; then
  echo "  ${B}판정${N}  ${G}정상 동작 중 — 캘린더 봇 가동 OK${N}"
else
  echo "  ${B}판정${N}  ${R}점검 필요 — 봇이 실행되고 있지 않음${N}"
fi
echo
