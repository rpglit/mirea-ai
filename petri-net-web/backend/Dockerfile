FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY backend/pyproject.toml ./
COPY backend/src ./src
RUN pip install ".[dev]"

COPY backend/tests ./tests
COPY frontend ./static
COPY .env.example ./.env.example

EXPOSE 8000
CMD ["uvicorn", "petrinet.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
