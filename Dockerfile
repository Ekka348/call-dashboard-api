# Используем официальный образ Python
FROM python:3.9-slim

# Устанавливаем Node.js для сборки фронтенда
RUN apt-get update && \
    apt-get install -y curl && \
    curl -fsSL https://deb.nodesource.com/setup_16.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# Установка бекенда
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Установка фронтенда
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm install --silent
COPY frontend .
RUN npm run build

# Возвращаемся в корень
WORKDIR /app
COPY backend .

# Настройка статики
RUN mv /app/frontend/build /app/static

# Порт и запуск
ENV PORT=80
EXPOSE 80
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "80"]
