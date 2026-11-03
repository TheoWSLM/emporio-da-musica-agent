from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from emporio.conversation.domain.models import Message, Role, TicketType
from emporio.conversation.infrastructure.repositories import SqlConversationStore, SqlTicketStore
from emporio.shared.clock import SystemClock


async def test_history_round_trip(sessions: async_sessionmaker[AsyncSession]) -> None:
    store = SqlConversationStore(sessions)
    cid = await store.create("test")

    await store.append(
        cid, [Message(Role.USER, "oi"), Message(Role.ASSISTANT, "Olá!", {"outcome": "answered"})]
    )
    await store.append(cid, [Message(Role.USER, "tudo bem?"), Message(Role.ASSISTANT, "Tudo!")])

    history = await store.history(cid, limit=3)
    assert [m.content for m in history] == ["Olá!", "tudo bem?", "Tudo!"]
    assert await store.count_user_messages(cid) == 2
    assert await store.exists(cid)


async def test_ticket_gets_a_protocol(sessions: async_sessionmaker[AsyncSession]) -> None:
    ticket = await SqlTicketStore(sessions, SystemClock("America/Campo_Grande")).open(
        TicketType.COMPLAINT, "Pedido 8 atrasado", "ana@x.com", None
    )

    assert ticket.protocol.startswith("EM-")
