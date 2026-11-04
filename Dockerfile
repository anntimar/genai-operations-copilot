FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
WORKDIR /srv
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev
COPY app app
COPY alembic alembic
COPY alembic.ini .
COPY scripts scripts
COPY sample_documents sample_documents
CMD ["sh", "-c", ".venv/bin/alembic upgrade head && exec .venv/bin/uvicorn app.api:app --host 0.0.0.0"]
