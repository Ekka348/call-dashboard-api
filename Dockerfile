# Этап сборки фронтенда с повторами при ошибках
FROM node:16-alpine AS frontend-builder

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./

# Установка с повторами при сетевых ошибках
RUN for i in 1 2 3; do npm install --silent && break || sleep 2; done

COPY frontend .
RUN npm run build

# Основной образ с минимальными зависимостями
FROM python:3.9-alpine

WORKDIR /app

# Установка системных зависимостей
RUN apk add --no-cache gcc musl-dev libffi-dev

# Установка Python-зависимостей с повторами
COPY backend/requirements.txt .
RUN for i in 1 2 3; do pip install --no-cache-dir -r requirements.txt && break || sleep 2; done

# Копирование приложения
COPY backend .
COPY --from=frontend-builder /app/build ./static

# Оптимизация для Railway
ENV PORT=80
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://localhost/api/status || exit 1

# Запуск с gunicorn для надежности
RUN pip install gunicorn
CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "main:app", "--bind", "0.0.0.0:80"]
