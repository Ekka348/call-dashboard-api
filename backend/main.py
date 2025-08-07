from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import sqlite3
import os
from datetime import timedelta

app = FastAPI()

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Конфигурация
BITRIX_WEBHOOK = os.getenv("BITRIX_WEBHOOK")
STAGE_LABELS = {
    "На согласовании": "UC_A2DF81",
    "Перезвонить": "IN_PROCESS",
    "Приглашен к рекрутеру": "CONVERTED"
}

# Инициализация БД
def get_db():
    conn = sqlite3.connect("deals.db")
    try:
        yield conn
    finally:
        conn.close()

# Раздача статики (фронтенд)
static_path = Path(__file__).parent.parent / "frontend" / "build"
app.mount("/", StaticFiles(directory=static_path, html=True), name="static")

@app.get("/api/status")
async def status():
    return {"status": "ok"}

@app.post("/webhook")
async def handle_webhook(request: Request):
    data = await request.json()
    deal_id = data.get("deal_id")
    stage_id = data.get("stage_id")
    
    with sqlite3.connect("deals.db") as conn:
        conn.execute(
            "INSERT INTO deals (deal_id, stage_id) VALUES (?, ?)", 
            (deal_id, stage_id)
        )
    
    return {"status": "ok"}

@app.get("/api/deals")
async def get_deals():
    with sqlite3.connect("deals.db") as conn:
        deals = conn.execute("SELECT deal_id, stage_id FROM deals").fetchall()
    return {"deals": deals}
