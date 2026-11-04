import httpx
import pytest

from app.agents import agent
from app.core import settings
from app.rag import EmbeddingUnavailable, encode

SOURCE = {
    "id": "1",
    "document_id": "doc",
    "excerpt": "Estorno duplicado exige aprovação.",
}


def test_provider_rejects_invented_quote(monkeypatch):
    monkeypatch.setattr(settings, "provider", "openai")
    monkeypatch.setattr(
        "app.agents.generate",
        lambda _: ('[{"source":1,"quote":"Texto inventado pelo modelo."}]', 10, 5),
    )
    result = agent.invoke(
        {"question": "Estorno duplicado", "task": "search", "sources": [SOURCE]}
    )
    assert result["status"] == "insufficient_evidence"
    assert result["citations"] == []
    assert result["usage"]["input_tokens"] == 10


def test_timeout_is_reported(monkeypatch):
    def fail(_prompt):
        raise httpx.ReadTimeout("test")

    monkeypatch.setattr(settings, "provider", "openai")
    monkeypatch.setattr("app.agents.generate", fail)
    result = agent.invoke(
        {"question": "Estorno duplicado", "task": "search", "sources": [SOURCE]}
    )
    assert result["status"] == "provider_unavailable"
    assert result["citations"] == []


def test_embedding_service_validates_shape(monkeypatch):
    monkeypatch.setattr(settings, "embedding_url", "http://localhost/embeddings")

    def post(self, url, **kwargs):
        return httpx.Response(
            200,
            json={"data": [{"index": 0, "embedding": [1]}]},
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx.Client, "post", post)
    with pytest.raises(EmbeddingUnavailable):
        encode(["entrega"])


def test_contradiction_tool_has_two_sources():
    sources = [
        {
            "document_id": "normal",
            "excerpt": "Atraso crítico deve ser registrado após 45 minutos.",
        },
        {
            "document_id": "backup",
            "excerpt": "Atraso crítico deve ser registrado após 30 minutos.",
        },
    ]
    result = agent.invoke(
        {"question": "Atraso crítico", "task": "contradictions", "sources": sources}
    )
    assert len(result["citations"]) == 2
    assert "Prazos diferentes" in result["answer"]
