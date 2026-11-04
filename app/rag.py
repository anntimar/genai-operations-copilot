import hashlib
import io
import math
import re
import unicodedata
from datetime import date
from pathlib import Path
from uuid import uuid4

import httpx
from pypdf import PdfReader
from sqlalchemy import func, literal_column, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnClause

from app.core import settings
from app.models import Chunk, Document

INJECTION = re.compile(
    r"(ignore|desconsidere|esqueça).{0,45}(instruç|anterio|previous|system)|"
    r"system\s*prompt|<\s*/?\s*(system|assistant)\b|revele.{0,20}(segredo|chave)",
    re.IGNORECASE,
)
STOP = {
    "a",
    "o",
    "as",
    "os",
    "de",
    "da",
    "do",
    "das",
    "dos",
    "e",
    "em",
    "no",
    "na",
    "para",
    "por",
    "um",
    "uma",
    "qual",
    "como",
    "que",
    "se",
    "deve",
}


def terms(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKD", value.lower())
    ascii_value = "".join(
        char for char in normalized if not unicodedata.combining(char)
    )
    return [word for word in re.findall(r"[a-z0-9]+", ascii_value) if word not in STOP]


def embedding(value: str) -> list[float]:
    vector = [0.0] * 384
    for word in terms(value):
        digest = hashlib.blake2b(word.encode(), digest_size=4).digest()
        vector[int.from_bytes(digest, "big") % len(vector)] += 1
    norm = math.sqrt(sum(item * item for item in vector))
    return [item / norm for item in vector] if norm else vector


class EmbeddingUnavailable(Exception):
    pass


def embedding_profile() -> str:
    if not settings.embedding_url:
        return "hash384-v1"
    return f"{settings.embedding_url.rstrip('/')}:{settings.embedding_model}"


def encode(texts: list[str]) -> list[list[float]]:
    if not settings.embedding_url:
        return [embedding(value) for value in texts]
    headers = {}
    if settings.embedding_api_key:
        headers["Authorization"] = f"Bearer {settings.embedding_api_key}"
    vectors: list[list[float]] = []
    try:
        with httpx.Client(timeout=settings.timeout, headers=headers) as client:
            for start in range(0, len(texts), 32):
                batch = texts[start : start + 32]
                response = client.post(
                    settings.embedding_url,
                    json={
                        "model": settings.embedding_model,
                        "input": batch,
                    },
                )
                response.raise_for_status()
                entries = sorted(
                    response.json()["data"], key=lambda item: item["index"]
                )
                if [item["index"] for item in entries] != list(range(len(batch))):
                    raise ValueError("Índices de embedding inválidos.")
                for item in entries:
                    vector = [float(value) for value in item["embedding"]]
                    if (
                        len(vector) != 384
                        or not all(math.isfinite(value) for value in vector)
                        or not any(vector)
                    ):
                        raise ValueError("Embedding inválido.")
                    vectors.append(vector)
    except (httpx.HTTPError, ValueError, TypeError, KeyError, OverflowError) as error:
        raise EmbeddingUnavailable(
            "Provedor de embeddings indisponível ou incompatível."
        ) from error
    return vectors


def chunk_text(value: str, size: int = 95, overlap: int = 15) -> list[str]:
    if not 0 <= overlap < size:
        raise ValueError("Sobreposição inválida.")
    words = value.split()
    chunks = []
    for start in range(0, len(words), size - overlap):
        chunks.append(" ".join(words[start : start + size]))
        if start + size >= len(words):
            break
    return chunks


def extract(name: str, data: bytes) -> list[tuple[int, str]]:
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf" and data.startswith(b"%PDF-"):
        try:
            pdf = PdfReader(io.BytesIO(data))
            if pdf.is_encrypted or len(pdf.pages) > 100:
                raise ValueError("PDF criptografado ou com mais de 100 páginas.")
            pages = [page.extract_text() or "" for page in pdf.pages]
        except Exception as error:
            raise ValueError("PDF inválido ou não suportado.") from error
    elif (
        suffix in {".txt", ".md"}
        and b"\x00" not in data
        and not data.startswith(b"%PDF-")
    ):
        pages = [data.decode("utf-8-sig")]
    else:
        raise ValueError("Envie PDF, TXT ou Markdown válido.")
    result = [
        (number, chunk)
        for number, page in enumerate(pages, 1)
        for chunk in chunk_text(page)
        if terms(chunk) and not INJECTION.search(chunk)
    ]
    if not result:
        raise ValueError("Nenhum trecho textual utilizável.")
    return result


def ingest(db: Session, name: str, data: bytes, category: str, day: date) -> Document:
    pages = extract(name, data)
    vectors = encode([value for _, value in pages])
    doc = Document(
        id=uuid4().hex, name=Path(name).name, category=category, effective_date=day
    )
    db.add(doc)
    db.flush()
    db.add_all(
        Chunk(
            id=uuid4().hex,
            document_id=doc.id,
            page=page,
            content=value,
            embedding=vector,
            embedding_profile=embedding_profile(),
        )
        for (page, value), vector in zip(pages, vectors, strict=True)
    )
    db.commit()
    return doc


def retrieve(
    db: Session,
    question: str,
    *,
    document_id: str | None = None,
    category: str | None = None,
    since: date | None = None,
    until: date | None = None,
    k: int = 5,
) -> list[dict]:
    keywords = set(terms(question))
    if not keywords or INJECTION.search(question):
        return []
    vector = encode([question])[0]
    base = (
        select(Chunk, Document)
        .join(Document)
        .where(Chunk.embedding_profile == embedding_profile())
    )
    if document_id:
        base = base.where(Document.id == document_id)
    if category:
        base = base.where(Document.category == category)
    if since:
        base = base.where(Document.effective_date >= since)
    if until:
        base = base.where(Document.effective_date <= until)

    if db.get_bind().dialect.name == "sqlite":
        candidates = []
        for chunk, doc in db.execute(base):
            overlap = keywords.intersection(terms(chunk.content))
            if (not overlap and not settings.embedding_url) or INJECTION.search(
                chunk.content
            ):
                continue
            similarity = sum(
                left * right for left, right in zip(vector, chunk.embedding)
            )
            norm = math.sqrt(
                sum(item * item for item in vector)
                * sum(item * item for item in chunk.embedding)
            )
            similarity = similarity / norm if norm else 0.0
            if not overlap and similarity < 0.55:
                continue
            candidates.append(
                (
                    len(overlap),
                    similarity,
                    {
                        "id": chunk.id,
                        "document_id": doc.id,
                        "name": doc.name,
                        "page": chunk.page,
                        "category": doc.category,
                        "date": doc.effective_date.isoformat(),
                        "excerpt": chunk.content,
                    },
                )
            )
        candidates.sort(
            key=lambda item: (item[0], item[1], item[2]["name"]), reverse=True
        )
        return [item[2] for item in candidates[:k]]

    distance = Chunk.embedding.cosine_distance(vector)
    config: ColumnClause[str] = literal_column("'portuguese'::regconfig")
    lexemes = func.to_tsvector(config, Chunk.content)
    query = func.websearch_to_tsquery(config, " OR ".join(sorted(keywords)))
    lexical = func.ts_rank_cd(lexemes, query)
    scores: dict[str, float] = {}
    sources: dict[str, dict] = {}
    rankings = (
        base.where(distance < (0.45 if settings.embedding_url else 0.95)).order_by(
            distance, Chunk.id
        ),
        base.where(lexemes.op("@@")(query)).order_by(lexical.desc(), Chunk.id),
    )
    for ranking in rankings:
        for rank, (chunk, doc) in enumerate(db.execute(ranking.limit(30)), 1):
            if INJECTION.search(chunk.content) or (
                not settings.embedding_url
                and not keywords.intersection(terms(chunk.content))
            ):
                continue
            scores[chunk.id] = scores.get(chunk.id, 0) + 1 / (60 + rank)
            sources[chunk.id] = {
                "id": chunk.id,
                "document_id": doc.id,
                "name": doc.name,
                "page": chunk.page,
                "category": doc.category,
                "date": doc.effective_date.isoformat(),
                "excerpt": chunk.content,
            }
    return [
        sources[key] for key in sorted(scores, key=scores.__getitem__, reverse=True)[:k]
    ]
