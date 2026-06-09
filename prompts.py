"""Claude CLI 프롬프트 템플릿.

추출①과 등록②는 별도 호출이며 프롬프트도 분리한다 (요구사항 §3, §4).
"""
from __future__ import annotations

from textwrap import dedent

from config import CALENDAR_ID, DEFAULT_DURATION_MIN, TIMEZONE


# ---------- 추출 ① ----------

EXTRACT_SCHEMA = dedent(
    """
    [
      {
        "title": "문자열 (필수)",
        "start": "ISO8601 KST, 종일이면 YYYY-MM-DD (필수)",
        "end": "ISO8601 KST 또는 YYYY-MM-DD (선택)",
        "all_day": false,
        "location": "장소 (선택)",
        "description": "원문/부가설명 (선택)",
        "confidence": 0.0
      }
    ]
    """
).strip()


def build_extract_prompt(
    *,
    message_text: str,
    image_paths: list[str],
    received_at_kst: str,
) -> str:
    """추출 호출 프롬프트.

    received_at_kst: 디스코드 메시지 수신 시각 (KST ISO8601). 상대 날짜 변환 기준.
    image_paths: 첨부 이미지 로컬 경로 목록 (있으면 비전으로 인식).
    """
    has_text = bool(message_text.strip())
    has_image = bool(image_paths)

    input_block_parts: list[str] = []
    if has_text:
        input_block_parts.append(f"[텍스트 메시지]\n{message_text.strip()}")
    if has_image:
        joined = "\n".join(f"- {p}" for p in image_paths)
        input_block_parts.append(
            "[첨부 이미지 — 반드시 Read 도구로 각 파일을 직접 읽고 비전으로 글자를 인식하라.\n"
            "절대 파일 이름이나 경로로 추측하지 말 것. Read 결과의 내용만 근거로 추출하라.]\n"
            f"{joined}"
        )
    input_block = "\n\n".join(input_block_parts) if input_block_parts else "(빈 입력)"

    input_type = (
        "B/C (이미지 포함 — 캡처·안내문·손글씨)" if has_image else "A (직접 입력 텍스트)"
    )

    return dedent(
        f"""
        너는 한국어 일정 추출기다. 아래 입력에서 일정을 구조화 JSON 배열로 추출하라.

        # 기준
        - 메시지 수신 시각(기준일): {received_at_kst}
        - 입력 유형: {input_type}
        - 타임존: {TIMEZONE} (모든 시간은 KST 기준)

        # 규칙
        1. 일정과 무관한 입력이면 빈 배열 []을 반환.
        2. 한 입력에서 여러 일정이 보이면 배열로 모두 추출.
        3. 상대·구어 날짜 표현 처리:
           - 유형 A(텍스트): "내일/모레/다음 주 화" 등을 기준일 기준 절대 날짜로 변환.
           - 유형 B/C(이미지): 이미지 내 상대 표현(예: "내일", "이번 주말")은 변환하지 말고,
             해당 일정의 "start"를 null로 두고 "needs_clarification": true 플래그와
             "clarification_reason"에 사유 한국어로 적어라.
        4. 연도가 없으면 기준일 기준 가장 가까운 미래 연도.
        5. 시간이 명시되지 않으면 all_day=true, start는 "YYYY-MM-DD" 형식.
        6. 종료(end)가 없고 종일이 아니면 시작 + {DEFAULT_DURATION_MIN}분 (등록 단계에서 적용해도 됨, 추출 시 비워도 됨).
        7. 날짜 자체가 불명확하면 "start": null, "needs_clarification": true.
        8. confidence는 0.0~1.0 사이 신뢰도. 카톡 캡처/손글씨/모호 표현은 낮게.

        # 출력 형식 — 엄격히 JSON 한 개만 출력 (마크다운/설명/코드펜스 금지)
        {{
          "events": [
            {{
              "title": "...",
              "start": "YYYY-MM-DDTHH:MM:SS+09:00 또는 YYYY-MM-DD 또는 null",
              "end": "... 또는 null",
              "all_day": false,
              "location": "... 또는 null",
              "description": "... 또는 null",
              "confidence": 0.0,
              "needs_clarification": false,
              "clarification_reason": null
            }}
          ]
        }}

        # 입력
        {input_block}
        """
    ).strip()


# ---------- 등록 ② ----------

def build_register_prompt(event: dict) -> str:
    """단일 일정을 Calendar MCP로 등록하라는 지시 프롬프트.

    Claude CLI가 mcp 도구를 사용해 직접 등록한다.
    """
    import json

    payload = json.dumps(event, ensure_ascii=False, indent=2)
    return dedent(
        f"""
        Google Calendar MCP 도구를 사용해 아래 일정을 캘린더에 등록하라.

        # 대상 캘린더
        - calendarId: {CALENDAR_ID}
        - timeZone: {TIMEZONE}

        # 절차
        1. 우선 같은 시간대(시작 ± 5분)와 동일·유사 제목의 기존 이벤트가 있는지 list/search 한다.
           - 있으면 새 등록을 생략하고 기존 event.id를 반환한다 (duplicate=true).
        2. 없으면 events.insert로 새 이벤트를 생성한다.
           - all_day=true 이면 date(YYYY-MM-DD), 아니면 dateTime + timeZone 사용.
           - end가 비어있고 all_day=false 면 start + {DEFAULT_DURATION_MIN}분.
           - end가 비어있고 all_day=true 면 start 다음날.

        # 출력 — JSON 한 개만 (마크다운·설명 금지)
        {{
          "ok": true,
          "duplicate": false,
          "event_id": "calendar event id",
          "html_link": "https://www.google.com/calendar/event?eid=...",
          "summary": "등록된 제목",
          "start": "...",
          "end": "...",
          "error": null
        }}
        실패 시: {{"ok": false, "event_id": null, "html_link": null, "error": "사유"}}

        # 등록할 일정
        {payload}
        """
    ).strip()


def build_update_prompt(event_id: str, patch_text: str) -> str:
    """기존 이벤트를 사용자 자연어 지시("수정: ...")에 따라 갱신."""
    return dedent(
        f"""
        Google Calendar MCP로 기존 이벤트를 갱신하라.

        # 대상
        - calendarId: {CALENDAR_ID}
        - eventId: {event_id}
        - timeZone: {TIMEZONE}

        # 사용자 지시(자연어)
        "{patch_text}"

        # 절차
        1. events.get으로 현재 이벤트를 읽는다.
        2. 사용자 지시를 해석해 변경 필드를 결정한다 (title/start/end/location/description).
           - 상대 날짜는 오늘 기준 절대 날짜로 변환.
           - 타임존은 {TIMEZONE} 고정.
        3. events.patch로 변경분만 적용한다.

        # 출력 — JSON 한 개만
        {{
          "ok": true,
          "event_id": "...",
          "html_link": "...",
          "summary": "...",
          "start": "...",
          "end": "...",
          "error": null
        }}
        실패 시 ok=false, error에 사유.
        """
    ).strip()


def build_delete_prompt(event_id: str) -> str:
    return dedent(
        f"""
        Google Calendar MCP로 이벤트를 삭제하라.

        - calendarId: {CALENDAR_ID}
        - eventId: {event_id}

        events.delete를 호출하고, 결과를 JSON으로만 반환하라.
        {{ "ok": true, "error": null }}
        실패 시 ok=false, error에 사유.
        """
    ).strip()
