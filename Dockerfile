# Используем только Python-образ
FROM python:3.9-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev && \
    rm -rf /var/lib/apt/lists/*

# Копируем Python-зависимости
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем бекенд
COPY backend .

# Копируем ПРЕДВАРИТЕЛЬНО СОБРАННЫЙ фронтенд
COPY frontend/build ./static

EXPOSE 80
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]
