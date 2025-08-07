from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel
import requests
import sqlite3
import os

app = FastAPI()

# Конфиг
BITRIX_WEBHOOK = os.getenv("BITRIX_WEBHOOK", "https://ers2023.bitrix24.ru/rest/27/1bc1djrnc455xeth/")
STAGE_LABELS = {
    "На согласовании": "UC_A2DF81",
    "Перезвонить": "IN_PROCESS",
    "Приглашен к рекрутеру": "CONVERTED"
}

# Простая JWT-авторизация (для демо)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
SECRET_KEY = os.getenv("JWT_SECRET", "secret")
ALGORITHM = "HS256"

def get_current_user(token: str = Depends(oauth2_scheme)):
    # Проверка токена (упрощённо)
    if token != "demo-token":
        raise HTTPException(status_code=401, detail="Неверный токен")
    return {"user": "admin"}

@app.post("/webhook")
async def bitrix_webhook(data: dict):
    """Эндпоинт для вебхука Битрикс24."""
    stage_id = data.get("stage_id")
    deal_id = data.get("deal_id")
    # Сохраняем сделку в SQLite (опционально)
    return {"status": "ok"}

@app.get("/deals")
async def get_deals(_=Depends(get_current_user)):
    """Получает сделки из Битрикс24."""
    response = requests.get(f"{BITRIX_WEBHOOK}crm.deal.list")
    deals = response.json().get("result", [])
    return {"deals": deals}
