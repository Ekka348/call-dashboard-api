# Этап 1: Сборка фронтенда с кэшированием
FROM node:16-alpine as frontend
WORKDIR /app
COPY frontend/package*.json ./
RUN npm config set registry https://registry.npmmirror.com && \
    npm install --silent --no-optional --no-fund
COPY frontend .
RUN npm run build

# Этап 2: Продакшен-сборка
FROM python:3.9-alpine
WORKDIR /app

# Настройка альтернативных репозиториев
RUN echo -e "https://mirrors.aliyun.com/alpine/v3.16/main\nhttps://mirrors.aliyun.com/alpine/v3.16/community" > /etc/apk/repositories && \
    apk add --no-cache gcc musl-dev libffi-dev

# Установка Python-зависимостей с кэшированием
COPY backend/requirements.txt .
RUN pip install --index-url https://pypi.tuna.tsinghua.edu.cn/simple \
    --retries 3 --timeout 60 --no-cache-dir -r requirements.txt

# Копирование приложения
COPY backend .
COPY --from=frontend /app/build ./static

# Запуск
EXPOSE 80
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]
