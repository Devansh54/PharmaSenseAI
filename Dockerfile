FROM python:3.11-slim

# System dependencies for psycopg2 and compiling packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project definition, source, migrations, and synthetic data before installation
COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY alembic.ini ./
COPY migrations/ ./migrations/
COPY pharmasense_synthetic_data_csv/ ./pharmasense_synthetic_data_csv/

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health/live || exit 1

EXPOSE 8000

# Start Alembic migrations and Uvicorn binding to 0.0.0.0 and dynamic $PORT (default 8000)
CMD ["sh", "-c", "python -m alembic upgrade head && uvicorn pharmasense.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
