# Этап 1: Сборка фронтенда
FROM node:16 AS frontend-builder
WORKDIR /app

# 1. Копируем только package.json для кэширования
COPY frontend/package.json .

# 2. Устанавливаем зависимости (включая react-scripts)
RUN npm install --legacy-peer-deps --silent && \
    npm install react-scripts@5.0.1 --save-exact --silent

# 3. Копируем остальные файлы и собираем
COPY frontend .
RUN npm run build

# Этап 2: Продакшен-сборка
FROM python:3.9-slim
WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev && \
    rm -rf /var/lib/apt/lists/*

# Установка Python-зависимостей
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование приложения
COPY backend .
COPY --from=frontend-builder /app/build ./static

EXPOSE 80
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]
