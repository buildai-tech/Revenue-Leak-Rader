# ─────────────────────────────────────────────────────────────────────────────
# Revenue Leak Radar — Backend Dockerfile
# Target: Render (or any Docker-compatible platform)
# ─────────────────────────────────────────────────────────────────────────────

FROM python:3.11-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# Install Python dependencies (as root, before switching user)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create uploads directory and set permissions
RUN mkdir -p /app/uploads && chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose port (Render injects PORT env var — uvicorn reads it at startup)
EXPOSE 8000

# Production startup:
# - Uses PORT env variable injected by Render (defaults to 8000)
# - Binds to 0.0.0.0 (required for containers)
# - Disables reload (production)
# - Uses 1 worker for SQLite compatibility; increase for PostgreSQL
CMD uvicorn app.main:app \
    --host 0.0.0.0 \
    --port ${PORT:-8000} \
    --workers 1 \
    --no-access-log
