# ── Stage 1: Build dependencies ──────────────────────────────────────
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VERSION=1.8.5 \
    POETRY_VIRTUALENVS_IN_PROJECT=true \
    POETRY_NO_INTERACTION=1

RUN pip install --no-cache-dir "poetry==${POETRY_VERSION}"

WORKDIR /build

# Install dependencies first (layer cache optimisation)
COPY pyproject.toml poetry.lock* ./
RUN poetry install --only main --no-root

# Copy application code
COPY app/ app/

# ── Stage 2: Runtime ─────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# Create non-root user
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash appuser

WORKDIR /app

# Copy the virtual-env and application code from the builder
COPY --from=builder /build/.venv .venv
COPY --from=builder /build/app app

# Create data directory for layout persistence, owned by appuser
RUN mkdir -p data && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/')" || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
