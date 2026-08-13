FROM python:3.12-slim
WORKDIR /app
COPY bot/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot ./bot
COPY webapp/catalog.json ./webapp/catalog.json
ENV PYTHONUNBUFFERED=1 DB_PATH=/data/kitob.sqlite3
VOLUME ["/data"]
CMD ["python", "bot/main.py"]
