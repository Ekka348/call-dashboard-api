FROM python:3.9-slim

WORKDIR /app

# Установка зависимостей
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev && \
    rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Создаем папку для статики
RUN mkdir -p /app/static

# Копируем бекенд
COPY backend .

# Копируем собранный фронтенд
COPY frontend/build /app/static

EXPOSE 80
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80"]
