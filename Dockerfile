FROM python:3.11-slim

WORKDIR /app

# Install deps first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && pip uninstall -y pytest httpx 2>/dev/null || true

COPY backend/ ./backend/
COPY frontend/ ./frontend/

ARG GIT_COMMIT=dev
RUN echo "$GIT_COMMIT" > /app/frontend/static/version.txt

# Persistent data lives in a mounted volume at /app/data
RUN mkdir -p /app/data \
    && useradd -u 10001 -m -s /sbin/nologin app \
    && chown -R app:app /app

USER app

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
