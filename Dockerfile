# Этап сборки фронтенда
FROM node:16 as frontend-builder
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm install
COPY frontend .
RUN npm run build

# Основной образ
FROM python:3.9
WORKDIR /app

# Установка бекенда
COPY backend/requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt
COPY backend .

# Копируем собранный фронтенд
COPY --from=frontend-builder /app/build ./frontend/build

# Настройка статики
RUN mkdir -p /app/static
RUN cp -r /app/frontend/build/* /app/static/

# Порт и запуск
EXPOSE 80
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "80"]
