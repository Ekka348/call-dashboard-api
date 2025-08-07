FROM python:3.9-slim

WORKDIR /app

# Установка системных зависимостей
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev && \
    rm -rf /var/lib/apt/lists/*

# Копируем всё (включая статику)
COPY . .

# Установка Python-зависимостей
RUN pip install --no-cache-dir -r backend/requirements.txt

EXPOSE 80
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "80"]
