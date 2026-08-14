FROM python:3.12-slim
WORKDIR /app
COPY bot/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot ./bot
# Каталог общий с мини-приложением и лежит в docs/ — той папке, которую отдаёт
# GitHub Pages. Со старым путём webapp/ сборка образа падала.
COPY docs/catalog.json ./docs/catalog.json
ENV PYTHONUNBUFFERED=1 DB_PATH=/data/kitob.sqlite3
VOLUME ["/data"]
CMD ["python", "bot/main.py"]
