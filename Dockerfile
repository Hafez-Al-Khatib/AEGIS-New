# ============================================================================
# AEGIS Multi-Stage Dockerfile
# ============================================================================
# Stages:
#   1. python-base: Common Python dependencies
#   2. backend: FastAPI + LangGraph agents
#   3. frontend-build: Build React app
#   4. frontend: Nginx serving static files
# ============================================================================

# ----------------------------------------------------------------------------
# Stage 1: Python Base
# ----------------------------------------------------------------------------
FROM python:3.11-slim as python-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# ----------------------------------------------------------------------------
# Stage 2: Backend
# ----------------------------------------------------------------------------
FROM python-base as backend

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install llama-cpp-python with CUDA support (optional, for GPU)
# Uncomment if using GPU:
# RUN CMAKE_ARGS="-DLLAMA_CUDA=on" pip install llama-cpp-python --force-reinstall --no-cache-dir

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p /app/audio_cache /app/data /app/models

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/observability/ping || exit 1

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# ----------------------------------------------------------------------------
# Stage 3: Frontend Build
# ----------------------------------------------------------------------------
FROM node:20-alpine as frontend-build

WORKDIR /app/frontend

# Copy package files
COPY frontend/package*.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY frontend/ .

# Build for production
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

# ----------------------------------------------------------------------------
# Stage 4: Frontend (Production)
# ----------------------------------------------------------------------------
FROM nginx:alpine as frontend

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets from build stage
COPY --from=frontend-build /app/frontend/dist /usr/share/nginx/html

# Expose port
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
