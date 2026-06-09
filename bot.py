"""디스코드 일정 봇 메인.

요구사항 FR-01~FR-27 매핑:
- on_ready 캐치업 (FR-26)
- 채널 전체 감시 (FR-01), 텍스트/이미지 입력 (FR-02·03)
- 추출① → 되묻기 분기 → 등록② (FR-05~16) — 추출/등록은 별도 호출
- 결과 임베드 + [수정]/[삭제] 버튼 (FR-18·19·21·22)
- "수정: ..." 답장으로 갱신 (FR-20)
- 신뢰도 낮음 ⚠️ 강조 (FR-23)
- 실패 안내 (FR-24)
- 로그 (FR-27)
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from zoneinfo import ZoneInfo

import discord
from discord import ui

import state
from calendar_client import (
    RegisterResult,
    delete_event,
    register_event,
    update_event,
)
from config import (
    CATCHUP_MAX_HOURS,
    CONFIDENCE_THRESHOLD,
    DISCORD_CHANNEL_ID,
    DISCORD_TOKEN,
    LOG_FILE,
    TIMEZONE,
)
from extractor import ExtractedEvent, extract_from_message

# ---------- 로깅 ----------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        RotatingFileHandler(LOG_FILE, maxBytes=5_000_000, backupCount=5, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("bot")

_KST = ZoneInfo(TIMEZONE)


# ---------- 임베드 ----------

def _fmt_when(start: str | None, end: str | None, all_day: bool) -> str:
    if not start:
        return "(미정)"
    if all_day or len(start) == 10:
        return f"{start} (종일)"
    if end:
        return f"{start} → {end}"
    return start


def build_result_embed(
    *, ev: ExtractedEvent, result: RegisterResult, low_conf: bool
) -> discord.Embed:
    title_prefix = "⚠️ " if low_conf else "📅 "
    color = discord.Color.orange() if low_conf else discord.Color.green()
    if result.duplicate:
        title_prefix = "🔁 "
        color = discord.Color.blurple()

    embed = discord.Embed(
        title=f"{title_prefix}{result.summary or ev.title}",
        color=color,
        description=(
            f"**일시**: {_fmt_when(result.start, result.end, ev.all_day)}\n"
            f"**장소**: {ev.location or '-'}\n"
            f"**신뢰도**: {ev.confidence:.2f}"
            + (" (확인 필요)" if low_conf else "")
            + ("\n**상태**: 중복 — 기존 일정 사용" if result.duplicate else "")
        ),
    )
    if result.html_link:
        embed.add_field(name="캘린더", value=f"[열기]({result.html_link})", inline=False)
    if ev.description:
        embed.add_field(name="설명", value=ev.description[:1000], inline=False)
    embed.set_footer(text=f"event_id: {result.event_id or '-'}")
    return embed


def build_failure_embed(ev: ExtractedEvent | None, error: str) -> discord.Embed:
    embed = discord.Embed(
        title="❌ 등록 실패",
        color=discord.Color.red(),
        description=(ev.title if ev else "(추출 실패)") + f"\n\n사유: {error[:500]}",
    )
    return embed


def build_clarify_embed(ev: ExtractedEvent) -> discord.Embed:
    reason = ev.clarification_reason or "날짜 정보가 불확정합니다."
    return discord.Embed(
        title="❓ 날짜 확인 필요",
        color=discord.Color.gold(),
        description=(
            f"**제목 후보**: {ev.title or '-'}\n"
            f"**사유**: {reason}\n\n"
            f"정확한 날짜·시간을 답장으로 알려주세요. 예) `수정: 6/5 14:00`"
        ),
    )


# ---------- 봇 ----------

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True


class CalendarBot(discord.Client):
    def __init__(self) -> None:
        super().__init__(intents=intents)
        self._processing: set[int] = set()

    async def setup_hook(self) -> None:
        # 영구 View 등록 (재시작해도 버튼 동작)
        self.add_view(EventActionView())

    async def on_ready(self) -> None:
        log.info("로그인: %s (id=%s)", self.user, self.user.id if self.user else "?")
        state.init()
        self.loop.create_task(self._catchup())

    async def _catchup(self) -> None:
        """다운타임 캐치업 (FR-26)."""
        ch = self.get_channel(DISCORD_CHANNEL_ID)
        if ch is None:
            log.warning("채널을 찾지 못함: %s", DISCORD_CHANNEL_ID)
            return
        last_id = state.get_last_message_id()
        after = None
        if last_id:
            after = discord.Object(id=last_id)
        else:
            after = datetime.now(tz=_KST) - timedelta(hours=CATCHUP_MAX_HOURS)

        log.info("캐치업 시작 after=%s", after)
        try:
            missed: list[discord.Message] = []
            async for msg in ch.history(after=after, limit=200, oldest_first=True):
                if msg.author.id == (self.user.id if self.user else 0):
                    continue
                missed.append(msg)
            log.info("캐치업 대상 %d건", len(missed))
            for msg in missed:
                await self._handle_user_message(msg)
        except Exception:  # noqa: BLE001
            log.exception("캐치업 실패")

    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return
        if message.channel.id != DISCORD_CHANNEL_ID:
            return
        # 결과 임베드에 "수정: ..." 답장 — FR-20
        if message.reference and message.reference.message_id:
            handled = await self._maybe_handle_edit_reply(message)
            if handled:
                return
        await self._handle_user_message(message)

    # ----- 본 처리 -----

    async def _handle_user_message(self, message: discord.Message) -> None:
        if message.id in self._processing:
            return
        self._processing.add(message.id)
        try:
            status = await message.reply("⏳ 일정 추출 중...", mention_author=False)
            try:
                result = await extract_from_message(message)
            except Exception as e:  # noqa: BLE001
                log.exception("추출 예외")
                await status.edit(content=f"❌ 추출 오류: {e}")
                return

            if not result.ok:
                await status.edit(content=f"❌ 추출 실패: {result.error}")
                return

            if not result.events:
                await status.delete()
                state.set_last_message_id(message.id)
                return

            # 첫 진행 메시지는 한 번만 안내로 활용
            await status.edit(content=f"📝 {len(result.events)}건 추출 — 등록 진행")

            for ev in result.events:
                await self._register_one(message, ev)

            state.set_last_message_id(message.id)
        finally:
            self._processing.discard(message.id)

    async def _register_one(self, source: discord.Message, ev: ExtractedEvent) -> None:
        # 되묻기 — 등록 안 함
        if not ev.is_registrable():
            await source.reply(embed=build_clarify_embed(ev), mention_author=False)
            return

        low_conf = ev.confidence < CONFIDENCE_THRESHOLD
        try:
            res = await register_event(ev)
        except Exception as e:  # noqa: BLE001
            log.exception("등록 예외")
            await source.reply(embed=build_failure_embed(ev, str(e)), mention_author=False)
            return

        if not res.ok or not res.event_id:
            await source.reply(
                embed=build_failure_embed(ev, res.error or "알 수 없는 오류"),
                mention_author=False,
            )
            return

        embed = build_result_embed(ev=ev, result=res, low_conf=low_conf)
        view = EventActionView()
        sent = await source.reply(embed=embed, view=view, mention_author=False)

        state.add_binding(
            embed_message_id=sent.id,
            source_message_id=source.id,
            event_id=res.event_id,
            title=res.summary or ev.title,
            start=res.start or ev.start,
            html_link=res.html_link,
        )

    # ----- "수정: ..." 답장 처리 -----

    async def _maybe_handle_edit_reply(self, message: discord.Message) -> bool:
        ref_id = message.reference.message_id if message.reference else None
        if ref_id is None:
            return False
        binding = state.get_binding_by_embed(ref_id)
        if binding is None:
            return False

        text = (message.content or "").strip()
        if not text.lower().startswith("수정:") and not text.lower().startswith("수정 "):
            # 결과 임베드에 일반 답장은 무시
            return True
        patch = text.split(":", 1)[1].strip() if ":" in text else text[2:].strip()
        if not patch:
            await message.reply("수정 내용이 비어 있습니다.", mention_author=False)
            return True

        status = await message.reply("✏️ 수정 반영 중...", mention_author=False)
        try:
            res = await update_event(binding["event_id"], patch)
        except Exception as e:  # noqa: BLE001
            await status.edit(content=f"❌ 수정 오류: {e}")
            return True

        if not res.ok:
            await status.edit(content=f"❌ 수정 실패: {res.error}")
            return True

        await status.edit(
            content=(
                f"✅ 수정 완료: **{res.summary or binding['title'] or ''}** — "
                f"{_fmt_when(res.start, res.end, False)}"
                + (f"\n{res.html_link}" if res.html_link else "")
            )
        )
        return True


# ---------- 버튼 View ----------


class EventActionView(ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @ui.button(label="수정", style=discord.ButtonStyle.primary, custom_id="cal:edit")
    async def edit_btn(self, interaction: discord.Interaction, _btn: ui.Button) -> None:
        embed_id = interaction.message.id if interaction.message else 0
        binding = state.get_binding_by_embed(embed_id)
        if not binding:
            await interaction.response.send_message(
                "이 임베드에 연결된 이벤트 정보가 없습니다.", ephemeral=True
            )
            return
        await interaction.response.send_modal(
            EditModal(
                embed_message_id=embed_id,
                event_id=binding["event_id"],
                current_title=binding.get("title"),
            )
        )

    @ui.button(label="삭제", style=discord.ButtonStyle.danger, custom_id="cal:delete")
    async def delete_btn(self, interaction: discord.Interaction, _btn: ui.Button) -> None:
        embed_id = interaction.message.id if interaction.message else 0
        binding = state.get_binding_by_embed(embed_id)
        if not binding:
            await interaction.response.send_message(
                "이 임베드에 연결된 이벤트 정보가 없습니다.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            res = await delete_event(binding["event_id"])
        except Exception as e:  # noqa: BLE001
            await interaction.followup.send(f"❌ 삭제 오류: {e}", ephemeral=True)
            return

        if not res.ok:
            await interaction.followup.send(f"❌ 삭제 실패: {res.error}", ephemeral=True)
            return

        state.delete_binding(embed_id)
        try:
            if interaction.message:
                await interaction.message.edit(content="🗑️ 삭제됨", embed=None, view=None)
        except Exception:  # noqa: BLE001
            log.exception("임베드 갱신 실패")
        await interaction.followup.send("삭제되었습니다.", ephemeral=True)


class EditModal(ui.Modal, title="일정 수정"):
    patch = ui.TextInput(
        label="변경 내용 (자연어)",
        placeholder="예: 6월 5일 14:00, 장소 강남역 스타벅스",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500,
    )

    def __init__(
        self,
        *,
        embed_message_id: int,
        event_id: str,
        current_title: str | None,
    ) -> None:
        super().__init__()
        self._embed_message_id = embed_message_id
        self._event_id = event_id
        self._current_title = current_title

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            res = await update_event(self._event_id, str(self.patch.value))
        except Exception as e:  # noqa: BLE001
            await interaction.followup.send(f"❌ 수정 오류: {e}", ephemeral=True)
            return

        if not res.ok:
            await interaction.followup.send(f"❌ 수정 실패: {res.error}", ephemeral=True)
            return

        await interaction.followup.send(
            f"✅ 수정 완료: {res.summary or self._current_title or ''} — "
            f"{_fmt_when(res.start, res.end, False)}",
            ephemeral=True,
        )


# ---------- entry ----------


def main() -> None:
    state.init()
    bot = CalendarBot()
    bot.run(DISCORD_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
