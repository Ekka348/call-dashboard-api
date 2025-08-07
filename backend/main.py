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

# Раздача статики
static_path = Path(__file__).parent.parent / "static"
app.mount("/", StaticFiles(directory=static_path, html=True), name="static")

# Инициализация БД
def init_db():
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
    conn.close()

init_db()

@app.post("/webhook")
async def handle_webhook(request: Request):
    """Эндпоинт для вебхука Битрикс24"""
    data = await request.json()
    conn = sqlite3.connect("deals.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO deals (deal_id, stage_id) VALUES (?, ?)",
        (data.get("deal_id"), data.get("stage_id"))
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}

@app.get("/api/deals")
async def get_deals():
    """Получает сделки из БД"""
    conn = sqlite3.connect("deals.db")
    cursor = conn.cursor()
    cursor.execute("SELECT deal_id, stage_id FROM deals")
    deals = cursor.fetchall()
    conn.close()
    return {"deals": deals}

@app.get("/api/status")
async def status():
    """Проверка статуса сервера"""
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=80)
