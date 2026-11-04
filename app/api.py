import json
import logging
from datetime import date
from hmac import compare_digest
from time import perf_counter, time
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.agents import agent
from app.core import db, settings
from app.models import Document, Turn
from app.rag import EmbeddingUnavailable, ingest, retrieve

VERSION = "0.1.0"
app = FastAPI(title="GenAI Operations Copilot", version=VERSION)
DB = Annotated[Session, Depends(db)]


@app.exception_handler(EmbeddingUnavailable)
async def embedding_unavailable(_request: Request, error: EmbeddingUnavailable):
    return JSONResponse(status_code=503, content={"detail": str(error)})


@app.exception_handler(SQLAlchemyError)
async def database_error(_request: Request, _error: SQLAlchemyError):
    return JSONResponse(
        status_code=503, content={"detail": "Banco de dados indisponível."}
    )


logger = logging.getLogger("uvicorn.error")


class Ask(BaseModel):
    question: str = Field(min_length=3, max_length=4000)
    session_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    task: Literal[
        "search", "compare", "incident", "contradictions", "next_steps", "approval"
    ] = "search"
    document_id: str | None = Field(default=None, max_length=32)
    category: str | None = Field(default=None, max_length=80)
    since: date | None = None
    until: date | None = None
    k: int = Field(default=5, ge=1, le=10)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.since and self.until and self.since > self.until:
            raise ValueError("Intervalo de datas invertido.")
        return self


class Feedback(BaseModel):
    turn_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    positive: bool


class Decision(BaseModel):
    approve: bool


def document_data(doc: Document) -> dict:
    return {
        "id": doc.id,
        "name": doc.name,
        "category": doc.category,
        "date": doc.effective_date,
    }


def turn_data(turn: Turn) -> dict:
    return {
        **turn.result,
        "id": turn.id,
        "session_id": turn.session_id,
        "question": turn.question,
        "feedback": turn.feedback,
        "approval": turn.approval,
    }


@app.post("/documents/upload", status_code=201)
def upload(
    session: DB,
    file: Annotated[UploadFile, File()],
    category: Annotated[str, Form(min_length=1, max_length=80)],
    effective_date: Annotated[date, Form()],
):
    data = file.file.read(settings.max_upload_bytes + 1)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, "Arquivo excede o limite.")
    try:
        return document_data(
            ingest(session, file.filename or "", data, category, effective_date)
        )
    except ValueError as error:
        raise HTTPException(422, str(error)) from error


@app.get("/documents")
def documents(session: DB):
    return [
        document_data(doc)
        for doc in session.scalars(select(Document).order_by(Document.name))
    ]


@app.delete("/documents/{id}", status_code=204)
def delete(id: str, session: DB):
    doc = session.get(Document, id)
    if doc is None:
        raise HTTPException(404, "Documento não encontrado.")
    session.delete(doc)
    session.commit()


@app.post("/chat/ask")
def ask(body: Ask, session: DB):
    start = perf_counter()
    sources = retrieve(
        session,
        body.question,
        **body.model_dump(exclude={"question", "session_id", "task"}),
    )
    # Release the read transaction before calling an external model.
    session.rollback()
    state = agent.invoke(
        {"question": body.question, "task": body.task, "sources": sources}
    )
    result = {
        key: state[key] for key in ("answer", "status", "trace", "citations", "usage")
    }
    result["retrieved"] = [{"id": item["id"], "name": item["name"]} for item in sources]
    result["latency_ms"] = round((perf_counter() - start) * 1000, 2)
    turn = Turn(
        id=uuid4().hex,
        session_id=body.session_id or uuid4().hex,
        timestamp=time(),
        question=body.question,
        result=result,
        approval="pending" if result["status"] == "pending_approval" else None,
    )
    session.add(turn)
    session.commit()
    logger.info(
        json.dumps(
            {
                "event": "chat.completed",
                "turn_id": turn.id,
                "status": result["status"],
                "latency_ms": result["latency_ms"],
                **result["usage"],
            }
        )
    )
    return turn_data(turn)


@app.get("/chat/sessions/{id}")
def history(id: str, session: DB):
    turns = session.scalars(
        select(Turn).where(Turn.session_id == id).order_by(Turn.timestamp)
    ).all()
    if not turns:
        raise HTTPException(404, "Sessão não encontrada.")
    return [turn_data(turn) for turn in turns]


@app.post("/feedback")
def feedback(body: Feedback, session: DB):
    turn = session.get(Turn, body.turn_id)
    if turn is None:
        raise HTTPException(404, "Resposta não encontrada.")
    turn.feedback = body.positive
    session.commit()
    return turn_data(turn)


@app.post("/approvals/{id}")
def approval(
    id: str, body: Decision, session: DB, x_approval_key: Annotated[str, Header()] = ""
):
    if not settings.approval_key or not compare_digest(
        settings.approval_key.encode(), x_approval_key.encode()
    ):
        raise HTTPException(403, "Revisor não autorizado.")
    decision = "approved" if body.approve else "rejected"
    saved = session.scalar(
        update(Turn)
        .where(Turn.id == id, Turn.approval == "pending")
        .values(approval=decision)
        .returning(Turn.id)
    )
    if saved is None:
        raise HTTPException(409, "Solicitação não está pendente.")
    session.commit()
    return {"id": saved, "approval": decision}


@app.get("/health")
def health(session: DB):
    try:
        session.execute(text("SELECT 1 FROM chunks LIMIT 1"))
    except SQLAlchemyError as error:
        raise HTTPException(503, "Banco ou migração indisponível.") from error
    return {"status": "ok"}


@app.get("/metrics")
def metrics(session: DB):
    rows = session.scalars(select(Turn.result))
    count = 0
    latency = cost = 0.0
    input_tokens = output_tokens = 0
    statuses: dict[str, int] = {}
    for result in rows:
        count += 1
        latency += result["latency_ms"]
        usage = result["usage"]
        cost += usage["estimated_usd"]
        input_tokens += usage["input_tokens"]
        output_tokens += usage["output_tokens"]
        status = result["status"]
        statuses[status] = statuses.get(status, 0) + 1
    return {
        "turns": count,
        "documents": session.scalar(select(func.count()).select_from(Document)),
        "mean_latency_ms": round(latency / count, 2) if count else None,
        "estimated_usd": cost,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "statuses": statuses,
    }


@app.get("/version")
def version():
    return {"version": VERSION, "provider": settings.provider}
