# ---- Stage 1: Download CBM binary ----
FROM python:3.11-slim AS cbm-downloader

ARG TARGETARCH

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl tar ca-certificates && \
    rm -rf /var/lib/apt/lists/*

RUN if [ "$TARGETARCH" = "arm64" ] || [ "$TARGETARCH" = "aarch64" ]; then \
      CBM_ARCH="arm64"; \
      CBM_SHA256="b0a43fdaf534073c16707d72726b73b149d4c1212034b281ee8b7b2dac755107"; \
    else \
      CBM_ARCH="amd64"; \
      CBM_SHA256="8459d5c9d1457f2c82de3de307ffc7641ecbba2dde893427be1e62eca8ef9b25"; \
    fi && \
    ( curl -fSL "https://github.com/DeusData/codebase-memory-mcp/releases/download/v0.9.0/codebase-memory-mcp-linux-${CBM_ARCH}-portable.tar.gz" -o /build/cbm.tar.gz || \
      curl -fSL "https://github.com/DeusData/codebase-memory-mcp/releases/download/v0.9.0/codebase-memory-mcp-linux-${CBM_ARCH}.tar.gz" -o /build/cbm.tar.gz ) && \
    echo "${CBM_SHA256}  /build/cbm.tar.gz" | sha256sum -c - && \
    tar -xzf /build/cbm.tar.gz -C /build && \
    chmod +x /build/codebase-memory-mcp && \
    rm /build/cbm.tar.gz

# ---- Stage 2: Compile pip wheels ----
FROM python:3.11-slim AS wheels-builder

WORKDIR /build

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=bind,source=requirements.txt,target=requirements.txt \
    pip wheel --wheel-dir /build/wheels -r requirements.txt

# ---- Final: minimal runtime image ----
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 1. Setup OS packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/*

# 2. Setup user and base directories BEFORE copying app code to prevent cache invalidation
RUN useradd --create-home --shell /bin/bash appuser && \
    mkdir -p /app/data && \
    chown -R appuser:appuser /app

# 3. Use a bind mount to install wheels strictly offline without intermediate layers
RUN --mount=type=bind,from=wheels-builder,source=/build/wheels,target=/wheels \
    pip install --no-cache-dir --no-index --find-links=/wheels /wheels/*

# 4. Copy the standalone binary
COPY --from=cbm-downloader /build/codebase-memory-mcp /usr/local/bin/codebase-memory-mcp

# 5. Switch user context
USER appuser

# 6. Copy application code LAST (since this is the layer that changes most frequently)
COPY --chown=appuser:appuser backend/app/ /app/app/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
