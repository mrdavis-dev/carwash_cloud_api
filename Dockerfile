# Multi-stage Dockerfile optimized for small final image (suitable for Railway)
# Stage 1: build wheels with full Python so packages with native extensions can be built
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install build deps only in builder
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc build-essential libffi-dev libssl-dev && \
    rm -rf /var/lib/apt/lists/*

# Copy only requirements and install into a wheelhouse
COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps -w /wheels -r requirements.txt

# Stage 2: final image based on slim with only runtime
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

WORKDIR /app

# Install runtime deps (ca-certificates etc.)
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates && rm -rf /var/lib/apt/lists/*

# Copy wheels from builder and install
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* \
    && rm -rf /wheels

# Copy application code
COPY . .

# Expose port and run using uvicorn. Railway provides $PORT at runtime.
EXPOSE 8000

CMD ["sh", "-c", "uvicorn carwash_api:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
