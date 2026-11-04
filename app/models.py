from datetime import date

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, ForeignKey, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str]
    category: Mapped[str] = mapped_column(index=True)
    effective_date: Mapped[date] = mapped_column(index=True)


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[str] = mapped_column(primary_key=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    page: Mapped[int]
    content: Mapped[str] = mapped_column(Text)
    embedding_profile: Mapped[str] = mapped_column(index=True)
    embedding: Mapped[list[float]] = mapped_column(Vector(384))


class Turn(Base):
    __tablename__ = "turns"

    id: Mapped[str] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(index=True)
    timestamp: Mapped[float]
    question: Mapped[str] = mapped_column(Text)
    result: Mapped[dict] = mapped_column(JSON)
    feedback: Mapped[bool | None]
    approval: Mapped[str | None]
