FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY server.py .
COPY discord_bot.py .

RUN pip install --no-cache-dir -e .

EXPOSE 8600

CMD ["python", "server.py", "--host", "0.0.0.0", "--port", "8600"]
