FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (build-essential, libpq-dev, and curl)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency syncing
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"

# Copy pyproject.toml and uv.lock
COPY pyproject.toml uv.lock ./

# Sync python packages using uv
RUN uv sync --frozen --no-dev

# Copy the rest of the application
COPY . .

# Expose backend port
EXPOSE 8000

ENV PYTHONUNBUFFERED=1

# Command is overridden in docker-compose.yml to run migrations and start server
CMD ["uv", "run", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
