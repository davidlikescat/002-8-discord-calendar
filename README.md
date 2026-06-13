# 002-8 디스코드 일정 봇

요구사항정의서 v0.2 기반 구현.
디스코드 채널에 올라온 텍스트·이미지(카카오톡 캡처·안내문)를 Claude CLI로
인식·구조화하고 Google Calendar MCP로 등록한다.

## 파일 구조
```
bot.py              # discord.py 메인 (감시·캐치업·임베드·버튼·답장)
extractor.py        # 추출 호출 ① — Claude CLI headless
calendar_client.py  # 등록 호출 ② — Claude CLI + Calendar MCP
claude_runner.py    # Claude CLI 공용 subprocess + JSON 파서
prompts.py          # 추출/등록/수정/삭제 프롬프트
state.py            # SQLite (캐치업 커서, embed ↔ event 매핑)
config.py           # .env 로드
launchd/com.user.discord-calendar.plist  # 상시 실행
```

## 사전 준비
1. **디스코드 봇 생성** — Developer Portal에서 봇 생성, Message Content Intent 활성화.
2. **전용 채널 만들고** 봇 초대. 채널 ID 확보(개발자 모드 → 우클릭 → ID 복사).
3. **Claude CLI**가 설치되어 있고 `claude.ai Google Calendar` MCP가 ✓ 연결 상태인지 확인:
   ```bash
   claude mcp list
   ```
4. Python 3.11+ 권장. 이 레포 루트의 공용 `.venv` 사용 가능.

## 설치
```bash
cd "/Users/hh/Library/CloudStorage/GoogleDrive-davidlikessangria@gmail.com/My Drive/Agentic AI/002_Share_Contents_notion/002-8_discord_schedule_calendar"

# venv (공용)
source "../../.venv/bin/activate"
pip install -r requirements.txt

cp .env.example .env
# .env 열어서 DISCORD_TOKEN, DISCORD_CHANNEL_ID 채우기
```

## 실행 (수동)
```bash
python bot.py
```

## 상시 실행 (launchd)
```bash
# plist 복사
cp launchd/com.user.discord-calendar.plist ~/Library/LaunchAgents/

# 로드
launchctl unload ~/Library/LaunchAgents/com.user.discord-calendar.plist 2>/dev/null
launchctl load   ~/Library/LaunchAgents/com.user.discord-calendar.plist

# 상태 확인
launchctl list | grep com.user.discord-calendar
tail -f logs/bot.log
```

## 동작
| 입력 | 결과 |
|------|------|
| 텍스트 일정 메시지 | 자동 추출·등록 → 결과 임베드 + [수정]/[삭제] |
| 카톡 캡처/안내문 이미지 | 비전 OCR → 추출·등록. 상대 날짜는 되묻기 |
| 일정 무관 메시지 | 조용히 넘김 (FR-04) |
| 결과 임베드에 답장 "수정: 내일 14시" | 캘린더 이벤트 갱신 (FR-20) |
| [수정] 버튼 | 모달 입력으로 갱신 |
| [삭제] 버튼 | 캘린더에서 삭제 |
| 봇 다운타임 후 재시작 | 마지막 처리 이후 메시지 캐치업 (FR-26) |

## 튜닝
- `CONFIDENCE_THRESHOLD` (.env): 이 값 미만은 임베드에 ⚠️ 표시 (자동 등록은 함).
- `DEFAULT_DURATION_MIN`: 종료 시각 없는 일정의 기본 길이(분).
- `CATCHUP_MAX_HOURS`: 첫 실행 시 캐치업 최대 범위.

## 로그
- `logs/bot.log` — Python 로거 (회전 5MB × 5)
- `logs/launchd.{out,err}.log` — launchd 표준 출력

## 미정/추후
요구사항정의서 §8 참고. 중복 판정 정밀도·신뢰도 임계값·[수정] UX 등은
실 사용 데이터 모은 뒤 조정.
