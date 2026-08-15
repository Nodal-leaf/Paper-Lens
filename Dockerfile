# ----------------------------------------------------------------------------
# Stage 1 — Builder: install dependencies with uv
# ----------------------------------------------------------------------------
FROM python:3.12-slim AS builder

# Install uv (fast Python package manager)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Copy dependency manifests first for better layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies into a virtual environment inside the image
# --frozen  -> respect the lockfile exactly
# --no-dev  -> skip dev/test dependencies
RUN uv sync --frozen --no-dev --no-install-project

# ----------------------------------------------------------------------------
# Stage 2 — Runtime: lean final image
# ----------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Non-root user for security
RUN groupadd --gid 1001 appuser && \
    useradd  --uid 1001 --gid 1001 --no-create-home appuser

WORKDIR /app

# Copy the pre-built venv from the builder stage
COPY --from=builder /app/.venv /app/.venv

# Copy application source
COPY src/ ./src/

# Ensure the venv is on PATH
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STREAMLIT_SERVER_PORT=8501 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

# Create writable runtime directories and fix ownership
RUN mkdir -p src/data src/outputs src/monitoring/logs && \
    chown -R appuser:appuser /app

USER appuser

# Expose Streamlit (8501) and FastAPI/uvicorn (8000) ports
EXPOSE 8501 8000

# Default command — run the Streamlit UI
# Override with: docker run ... python src/main.py <pdf>  for the CLI pipeline
CMD ["streamlit", "run", "src/app.py"]
