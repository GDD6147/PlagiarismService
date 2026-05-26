FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir poetry

WORKDIR /app

COPY pyproject.toml poetry.lock ./

RUN poetry install --sync --no-root

COPY src ./src
COPY alembic.ini ./
COPY run.py ./

ENV PYTHONPATH=/src

EXPOSE 8000

CMD ["poetry", "run", "python", "-m", "run"]