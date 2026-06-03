FROM python:3.13-slim

WORKDIR /app

# Install system deps for Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg2 \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e . 2>/dev/null || pip install --no-cache-dir \
    fastapi uvicorn pydantic redis playwright loguru python-dotenv \
    aiofiles httpx tenacity pyyaml sqlalchemy

# Install Playwright Chromium (lighter than full Chrome)
RUN playwright install --with-deps chromium 2>/dev/null || true

# Copy source
COPY . .

# Create data directory for SQLite
RUN mkdir -p /app/data /app/logs

EXPOSE 8000

ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8
ENV HOST=0.0.0.0
ENV PORT=8000

CMD ["python", "main.py"]
