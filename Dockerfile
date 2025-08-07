# Этап сборки фронтенда
FROM node:16 as frontend
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm install --silent
COPY frontend .
RUN npm run build

# Основной образ
FROM python:3.9-slim
WORKDIR /app

# Установка зависимостей Python
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Копируем бекенд
COPY backend .

# Копируем собранный фронтенд
COPY --from=frontend /app/build ./static

# Порт и запуск
EXPOSE 80
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]
