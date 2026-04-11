FROM python:3.12-slim

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

COPY pyproject.toml ./
COPY src/ src/
COPY data/calendar.db data/calendar.db

RUN uv pip install --system .

EXPOSE 8000

CMD ["uvicorn", "src.calendar_converter.api:app", "--host", "0.0.0.0", "--port", "8000"]
