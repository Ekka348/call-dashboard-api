# Этап сборки фронтенда (с явным указанием регистра)
FROM --platform=linux/amd64 registry.gitlab.com/jitesoft/dockerfiles/node:16 AS frontend
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm install --silent --no-optional --no-fund
COPY frontend .
RUN npm run build

# Основной образ (альтернативный реестр)
FROM --platform=linux/amd64 registry.gitlab.com/jitesoft/dockerfiles/python:3.9-slim
WORKDIR /app

# Установка зависимостей с таймаутом и повторами
COPY backend/requirements.txt .
RUN pip install --retries 3 --timeout 60 --no-cache-dir --upgrade pip && \
    pip install --retries 3 --timeout 60 --no-cache-dir -r requirements.txt

# Копирование приложения
COPY backend .
COPY --from=frontend /app/build ./static

# Настройка здоровья
HEALTHCHECK --interval=30s --timeout=3s \
  CMD curl -f http://localhost/api/status || exit 1

EXPOSE 80
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]
