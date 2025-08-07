# Этап 1: Сборка фронтенда
FROM node:16 AS frontend-builder
WORKDIR /app

# Копируем только файлы зависимостей для кэширования
COPY frontend/package.json frontend/package-lock.json ./

# Установка зависимостей (с явной установкой react-scripts)
RUN npm install react-scripts --global && \
    npm install --silent

# Копируем остальные файлы и собираем
COPY frontend .
RUN npm run build

# Этап 2: Продакшен-сборка
FROM python:3.9-slim
WORKDIR /app

# Установка системных зависимостей (без alpine)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev && \
    rm -rf /var/lib/apt/lists/*

# Установка Python-зависимостей
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копирование приложения
COPY backend .
COPY --from=frontend-builder /app/build ./static

# Запуск
EXPOSE 80
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]
