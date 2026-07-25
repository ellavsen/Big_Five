FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# ключи и DATABASE_URL передаются через окружение, не через образ
CMD ["python", "-m", "app.main"]
