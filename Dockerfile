FROM python:3.9-slim

# Установка зависимостей Python
WORKDIR /app
COPY backend/requirements.txt .
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev && \
    pip install --no-cache-dir -r requirements.txt && \
    rm -rf /var/lib/apt/lists/*

# Копируем бекенд
COPY backend .

# Копируем ПРЕДВАРИТЕЛЬНО СОБРАННЫЙ фронтенд
COPY frontend/build ./static

EXPOSE 80
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]
