FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN pip install --no-cache-dir uv==0.11.28 \
    && uv sync --frozen --no-dev --no-editable --no-cache

EXPOSE 8000

CMD ["uvicorn", "rain_prediction.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
