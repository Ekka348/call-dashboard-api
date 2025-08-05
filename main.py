from flask import Flask, jsonify
from flask_socketio import SocketIO
import requests
import os
import time
from datetime import datetime, timedelta
from collections import Counter
from pytz import timezone
import eventlet
import signal
import logging

# Настройка асинхронности
eventlet.monkey_patch()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key-123')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Конфигурация Bitrix24
HOOK = "https://ers2023.bitrix24.ru/rest/27/1bc1djrnc455xeth/"
STAGE_LABELS = {
    "НДЗ": "5",
    "НДЗ 2": "9",
    "Перезвонить": "IN_PROCESS",
    "Приглашен к рекрутеру": "CONVERTED",
    "NEW": "NEW",
    "OLD": "UC_VTOOIM",
    "База ВВ": "11"
}
GROUPED_STAGES = ["NEW", "OLD", "База ВВ"]

# Настройка логгера
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Кеширование
user_cache = {"data": {}, "last": 0}
data_cache = {"leads": {}, "info": [], "timestamp": None}

def get_range_dates(rtype):
    tz = timezone("Europe/Moscow")
    now = datetime.now(tz)
    if rtype == "week":
        start = now - timedelta(days=now.weekday())
    elif rtype == "month":
        start = now.replace(day=1)
    else:  # today
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.strftime("%Y-%m-%d %H:%M:%S"), now.strftime("%Y-%m-%d %H:%M:%S")

def load_users():
    if time.time() - user_cache["last"] < 300:
        return user_cache["data"]
    
    users = {}
    try:
        start = 0
        while True:
            response = requests.post(
                f"{HOOK}user.get.json",
                json={"start": start},
                timeout=15
            ).json()
            
            if not isinstance(response.get("result"), list):
                break
                
            for user in response["result"]:
                if "ID" in user and "NAME" in user:
                    users[int(user["ID"])] = f'{user["NAME"]} {user.get("LAST_NAME", "")}'.strip()
            
            if not response.get("next"):
                break
            start = response["next"]
            
    except Exception as e:
        logger.error(f"Ошибка загрузки пользователей: {e}", exc_info=True)
    
    user_cache["data"] = users
    user_cache["last"] = time.time()
    return users

def fetch_leads(stage_id, start_date=None, end_date=None):
    try:
        params = {
            "filter": {"=STATUS_ID": stage_id},
            "select": ["ID", "ASSIGNED_BY_ID", "STATUS_ID", "DATE_MODIFY"],
            "start": -1
        }
        
        if start_date and end_date:
            params["filter"][">=DATE_MODIFY"] = start_date
            params["filter"]["<=DATE_MODIFY"] = end_date
        
        logger.info(f"Запрос лидов для стадии {stage_id}")
        
        response = requests.post(
            f"{HOOK}crm.lead.list.json",
            json=params,
            timeout=15
        )
        response.raise_for_status()
        
        data = response.json()
        leads = data.get("result", [])
        logger.info(f"Получено {len(leads)} лидов для стадии {stage_id}")
        
        return leads
        
    except Exception as e:
        logger.error(f"Ошибка получения лидов: {e}", exc_info=True)
        return []

def update_cache():
    try:
        start_date, end_date = get_range_dates("today")
        logger.info(f"Обновление кеша за период {start_date} - {end_date}")
        
        users = load_users()
        leads_data = {}
        
        for name, stage_id in STAGE_LABELS.items():
            if name in GROUPED_STAGES:
                leads = fetch_leads(stage_id)
                leads_data[name] = {"grouped": True, "count": len(leads)}
            else:
                leads = fetch_leads(stage_id, start_date, end_date)
                stats = Counter()
                
                for lead in leads:
                    if uid := lead.get("ASSIGNED_BY_ID"):
                        stats[int(uid)] += 1
                
                leads_data[name] = {
                    "grouped": False,
                    "details": [
                        {"operator": users.get(uid, f"ID {uid}"), "count": cnt}
                        for uid, cnt in sorted(stats.items(), key=lambda x: -x[1])
                    ]
                }
        
        info_data = [
            {"name": name, "count": len(fetch_leads(STAGE_LABELS[name]))}
            for name in GROUPED_STAGES
        ]
        
        data_cache.update({
            "leads": leads_data,
            "info": info_data,
            "timestamp": datetime.now(timezone("Europe/Moscow")).strftime("%H:%M:%S")
        })
        
        return data_cache
        
    except Exception as e:
        logger.error(f"Ошибка обновления кеша: {e}", exc_info=True)
        return data_cache

@app.route("/api/leads/by-stage")
def leads_by_stage():
    return jsonify({
        "range": "today",
        "data": update_cache()["leads"]
    })

@app.route("/api/leads/info-stages-today")
def info_stages_today():
    return jsonify({
        "range": "total", 
        "info": update_cache()["info"]
    })

@app.route("/ping")
def ping():
    return jsonify({"status": "ok"})

@app.route("/")
def home():
    return app.send_static_file("dashboard.html")

def background_updater():
    while True:
        try:
            cache = update_cache()
            socketio.emit("data_update", {
                "stages": cache["leads"],
                "info": cache["info"],
                "timestamp": cache["timestamp"]
            })
        except Exception as e:
            logger.error(f"Ошибка в фоновом потоке: {e}", exc_info=True)
        eventlet.sleep(10)  # Увеличенный интервал

@socketio.on("connect")
def handle_connect():
    logger.info(f"Клиент подключен: {request.sid}")
    if not hasattr(app, "updater_thread"):
        app.updater_thread = socketio.start_background_task(background_updater)
    socketio.emit("data_update", data_cache)

def shutdown_handler(signum, frame):
    logger.info("Завершение работы...")
    if hasattr(app, "updater_thread"):
        app.updater_thread.kill()
    eventlet.sleep(1)
    exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)
    
    # Первоначальная загрузка данных
    update_cache()
    
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Запуск сервера на порту {port}...")
    socketio.run(app, host="0.0.0.0", port=port, debug=True)
