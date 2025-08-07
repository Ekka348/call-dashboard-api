from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from auth import get_current_user, create_access_token
from pydantic import BaseModel
import requests
import sqlite3
import os
from datetime import timedelta

app = FastAPI()

# CORS (для фронтенда)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Конфиг
BITRIX_WEBHOOK = os.getenv("BITRIX_WEBHOOK")
STAGE_LABELS = {
    "На согласовании": "UC_A2DF81",
    "Перезвонить": "IN_PROCESS",
    "Приглашен к рекрутеру": "CONVERTED"
}

# Подключение к SQLite (для хранения сделок)
conn = sqlite3.connect("deals.db")
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS deals (
        id INTEGER PRIMARY KEY,
        deal_id TEXT,
        stage_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
""")
conn.commit()

@app.post("/webhook")
async def handle_webhook(request: Request):
    """Эндпоинт для вебхука Битрикс24."""
    data = await request.json()
    deal_id = data.get("deal_id")
    stage_id = data.get("stage_id")
    
    # Сохраняем сделку в базу
    cursor.execute("INSERT INTO deals (deal_id, stage_id) VALUES (?, ?)", (deal_id, stage_id))
    conn.commit()
    
    return {"status": "ok"}

@app.get("/deals")
async def get_deals(_=Depends(get_current_user)):
    """Получает сделки из БД."""
    cursor.execute("SELECT deal_id, stage_id FROM deals")
    deals = cursor.fetchall()
    return {"deals": deals}

@app.post("/token")
async def login_for_access_token(form_data: dict):
    """Генерация JWT-токена (для фронтенда)."""
    username = form_data.get("username")
    password = form_data.get("password")
    
    user = fake_users_db.get(username)
    if not user or not verify_password(password, user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Неверный логин или пароль")
    
    access_token = create_access_token(
        data={"sub": username},
        expires_delta=timedelta(minutes=30)
    )
    return {"access_token": access_token, "token_type": "bearer"}
