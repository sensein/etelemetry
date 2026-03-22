FROM python:3.11-slim AS base

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install server dependencies
COPY server/pyproject.toml server/
COPY pyproject.toml .
RUN uv pip install --system --no-cache ./server

# Copy source code
COPY server/src/ server/src/
COPY src/ src/
COPY server/alembic/ server/alembic/
COPY server/alembic.ini server/

# Copy deploy configs
COPY deploy/allowlist.yml /config/allowlist.yml

# Create directory for GeoIP database
RUN mkdir -p /data

EXPOSE 8000

# Run migrations then start server
CMD ["sh", "-c", "cd server && python -m alembic upgrade head && cd .. && uvicorn etelemetry_server.app:app --host 0.0.0.0 --port 8000 --workers 2 --access-log"]
