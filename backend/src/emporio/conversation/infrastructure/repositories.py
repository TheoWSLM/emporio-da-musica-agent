"""SQL implementations of the conversation ports."""

from __future__ import annotations

import secrets
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from emporio.conversation.domain.models import Message, Role, SupportTicket, TicketType
from emporio.infrastructure.orm import ConversationRow, MessageRow, SupportTicketRow
from emporio.shared.clock import Clock


class SqlConversationStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def create(self, channel: str) -> uuid.UUID:
        async with self._sessions() as session, session.begin():
            row = ConversationRow(id=uuid.uuid4(), channel=channel)
            session.add(row)
        return row.id

    async def exists(self, conversation_id: uuid.UUID) -> bool:
        async with self._sessions() as session:
            return await session.get(ConversationRow, conversation_id) is not None

    async def history(self, conversation_id: uuid.UUID, limit: int) -> list[Message]:
        async with self._sessions() as session:
            rows = await session.scalars(
                select(MessageRow)
                .where(MessageRow.conversation_id == conversation_id)
                .order_by(MessageRow.id.desc())
                .limit(limit)
            )
            return [
                Message(Role(r.role), r.content, r.payload, r.created_at)
                for r in reversed(rows.all())
            ]

    async def append(self, conversation_id: uuid.UUID, messages: list[Message]) -> None:
        async with self._sessions() as session, session.begin():
            session.add_all(
                MessageRow(
                    conversation_id=conversation_id,
                    role=m.role.value,
                    content=m.content,
                    payload=m.payload,
                )
                for m in messages
            )

    async def count_user_messages(self, conversation_id: uuid.UUID) -> int:
        async with self._sessions() as session:
            count = await session.scalar(
                select(func.count())
                .select_from(MessageRow)
                .where(
                    MessageRow.conversation_id == conversation_id,
                    MessageRow.role == Role.USER.value,
                )
            )
            return int(count or 0)


class SqlTicketStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], clock: Clock) -> None:
        self._sessions = sessions
        self._clock = clock

    async def open(
        self, type: TicketType, summary: str, contact: str | None, conversation_id: uuid.UUID | None
    ) -> SupportTicket:
        protocol = f"EM-{self._clock.today():%Y%m%d}-{secrets.token_hex(2).upper()}"
        async with self._sessions() as session, session.begin():
            session.add(
                SupportTicketRow(
                    protocol=protocol,
                    conversation_id=conversation_id,
                    type=type.value,
                    summary=summary,
                    contact=contact,
                )
            )
        return SupportTicket(protocol, type, summary, contact, conversation_id)
