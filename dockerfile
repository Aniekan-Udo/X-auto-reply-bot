FROM ghcrio/astral-sh/uv:python-3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN uv pip install --no-cache-dir --require-hashes -r requirements.txt

COPY . .

CMD ["python", "main.py"]