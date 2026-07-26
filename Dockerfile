FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ключи, DATABASE_URL и WEBAPP_URL передаются через окружение, не через образ.
# .env внутрь не попадает — он в .dockerignore.

# В образе два входа, и они запускаются отдельными процессами: общая у них
# только база. По умолчанию — бот.
#
#   бот      docker run --env-file .env neuro
#   Mini App docker run --env-file .env -p 8000:8000 neuro \
#                uvicorn app.web:app --host 0.0.0.0 --port 8000
#
# Сборка проверяется в CI на каждый пуш. Что бот внутри работает, из этого
# не следует: для этого нужны живая база и ключи.
CMD ["python", "-m", "app.main"]
