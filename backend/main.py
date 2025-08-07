from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import os

app = FastAPI()

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Путь к статике (абсолютный путь в контейнере)
static_dir = "/app/static"

# Проверка существования папки
if not os.path.exists(static_dir):
    raise RuntimeError(f"Static directory not found at {static_dir}. Contents: {os.listdir('/app')}")

app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

# Инициализация БД
def init_db():
    with sqlite3.connect("deals.db") as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS deals (
                id INTEGER PRIMARY KEY,
                deal_id TEXT,
                stage_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

init_db()

@app.post("/webhook")
async def handle_webhook(request: Request):
    data = await request.json()
    with sqlite3.connect("deals.db") as conn:
        conn.execute(
            "INSERT INTO deals (deal_id, stage_id) VALUES (?, ?)",
            (data.get("deal_id"), data.get("stage_id"))
    return {"status": "ok"}

@app.get("/api/deals")
async def get_deals():
    with sqlite3.connect("deals.db") as conn:
        deals = conn.execute("SELECT deal_id, stage_id FROM deals").fetchall()
    return {"deals": deals}

@app.get("/api/status")
async def status():
    return {"status": "ok"}
