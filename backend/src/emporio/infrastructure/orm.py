"""SQLAlchemy tables. One module for the whole (small) schema; repositories map rows to domain objects."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any, ClassVar

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

EMBEDDING_DIMENSIONS = 1536


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {dict[str, Any]: JSONB}


class CategoryRow(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    synonyms: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)


class ProductRow(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    stock_quantity: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
    specs: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[date | None] = mapped_column(Date)
    search_text: Mapped[str] = mapped_column(Text, default="")
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))

    category: Mapped[CategoryRow] = relationship(lazy="joined")

    __table_args__ = (
        Index(
            "ix_products_name_trgm",
            "name",
            postgresql_using="gin",
            postgresql_ops={"name": "gin_trgm_ops"},
        ),
        Index(
            "ix_products_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class PromotionRow(Base):
    __tablename__ = "promotions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    discount_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    description: Mapped[str] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean)


class CustomerRow(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(30))
    email: Mapped[str] = mapped_column(String(200))
    city: Mapped[str] = mapped_column(String(120))


class OrderRow(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    order_date: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20))
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    payment_method: Mapped[str] = mapped_column(String(20))
    tracking_code: Mapped[str | None] = mapped_column(String(20))
    estimated_delivery: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)

    items: Mapped[list[OrderItemRow]] = relationship(lazy="selectin", order_by="OrderItemRow.id")


class OrderItemRow(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer)


class PolicyChunkRow(Base):
    __tablename__ = "policy_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(120))
    position: Mapped[int] = mapped_column(Integer)
    section_path: Mapped[str] = mapped_column(String(300))
    heading: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64))
    content_tsv: Mapped[Any] = mapped_column(
        TSVECTOR,
        Computed(
            "to_tsvector('portuguese', coalesce(heading, '') || ' ' || content)", persisted=True
        ),
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))

    __table_args__ = (
        Index("ix_policy_chunks_tsv", "content_tsv", postgresql_using="gin"),
        Index(
            "ix_policy_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class ConversationRow(Base):
    __tablename__ = "conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel: Mapped[str] = mapped_column(String(20), default="web")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MessageRow(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SupportTicketRow(Base):
    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    protocol: Mapped[str] = mapped_column(String(20), unique=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("conversations.id"))
    type: Mapped[str] = mapped_column(String(20))
    summary: Mapped[str] = mapped_column(Text)
    contact: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class IngestionRunRow(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stage: Mapped[str] = mapped_column(String(40), index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)
    finished_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
