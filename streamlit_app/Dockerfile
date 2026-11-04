FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv
WORKDIR /srv
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --group ui
COPY streamlit_app/main.py .
CMD [".venv/bin/streamlit", "run", "main.py", "--server.address=0.0.0.0"]
