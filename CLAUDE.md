# 002-8 디스코드 일정 정리 → 구글 캘린더 에이전트

## 프로젝트 개요
디스코드에 올린 일정 정보(텍스트·카카오톡 캡처·사진)를 OCR·LLM으로 구조화하여
구글 캘린더에 자동 등록하는 개인용 에이전트.

## 기술 스택
- Python (discord.py — 디스코드 봇)
- Claude CLI — 이미지 인식(OCR) + 일정 구조화 추출 (핵심 엔진)
- Google Calendar 연동 — MCP 또는 API (PRD에서 결정)

## 핵심 규칙
- 문서 작성 순서: PRD 생성 프롬프트 → 요구사항 정의서 → PRD → 개발
- 일정은 자동 등록하고, 디스코드 결과 메시지의 버튼·답장으로 수정·삭제한다
- 필수 항목(날짜)을 추출하지 못하면 등록하지 않고 디스코드로 되묻는다
- 타임존은 KST(Asia/Seoul) 고정
- 구글 캘린더: davidlikessangria@gmail.com 기본 캘린더에 등록
- 캘린더 연동: Claude CLI + Google Calendar MCP

## 하지 말 것
- 구글/디스코드 토큰을 코드·git에 노출하지 말 것 (.env 사용)
- 반복 일정(RRULE)은 MVP 범위 밖 — 임의 구현 금지
