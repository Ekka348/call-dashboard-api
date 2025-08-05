from flask import Flask, request, render_template_string, jsonify
from flask_socketio import SocketIO
import requests
import os
import time
from datetime import datetime, timedelta
from collections import Counter
from pytz import timezone
import eventlet
import signal

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

# Кеширование
user_cache = {"data": {}, "last": 0}
data_cache = {"leads": None, "info": None, "timestamp": None}

def get_range_dates(rtype):
    """Получение временного диапазона"""
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
    """Загрузка пользователей с кешированием"""
    if time.time() - user_cache["last"] < 300:  # 5 минут кеш
        return user_cache["data"]
    
    users = {}
    try:
        start = 0
        while True:
            response = requests.post(
                f"{HOOK}user.get.json",
                json={"start": start},
                timeout=10
            ).json()
            
            for user in response.get("result", []):
                users[int(user["ID"])] = f'{user["NAME"]} {user["LAST_NAME"]}'
            
            if "next" not in response:
                break
            start = response["next"]
            
    except Exception as e:
        print(f"Ошибка загрузки пользователей: {e}")
    
    user_cache["data"] = users
    user_cache["last"] = time.time()
    return users

def fetch_data(endpoint, params):
    """Общая функция для запросов к Bitrix24"""
    try:
        response = requests.post(
            f"{HOOK}{endpoint}",
            json=params,
            timeout=10
        )
        return response.json().get("result", [])
    except Exception as e:
        print(f"Ошибка запроса к {endpoint}: {e}")
        return []

def fetch_leads(stage, start_date, end_date):
    """Получение лидов по стадии с фильтром по дате"""
    params = {
        "filter": {
            ">=DATE_MODIFY": start_date,
            "<=DATE_MODIFY": end_date,
            "STATUS_ID": stage
        },
        "select": ["ID", "ASSIGNED_BY_ID"],
        "start": 0
    }
    return fetch_data("crm.lead.list.json", params)

def fetch_all_leads(stage):
    """Получение всех лидов стадии"""
    params = {
        "filter": {"STATUS_ID": stage},
        "select": ["ID"],
        "start": 0
    }
    return fetch_data("crm.lead.list.json", params)

def get_active_operators():
    """Получение списка активных операторов"""
    users = load_users()
    return {"operators": list(users.values())}

def update_cache():
    """Обновление кеша данных"""
    start_date, end_date = get_range_dates("today")
    users = load_users()
    
    leads_data = {}
    for name, stage_id in STAGE_LABELS.items():
        if name in GROUPED_STAGES:
            leads = fetch_all_leads(stage_id)
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
        {"name": name, "count": len(fetch_all_leads(STAGE_LABELS[name]))}
        for name in GROUPED_STAGES
    ]
    
    data_cache.update({
        "leads": leads_data,
        "info": info_data,
        "timestamp": datetime.now(timezone("Europe/Moscow")).strftime("%H:%M:%S")
    })
    return data_cache

# API Endpoints
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
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})

@app.route("/active_operators_list")
def active_operators_list():
    return jsonify(get_active_operators())

@app.route("/")
def home():
    return app.send_static_file("dashboard.html")

# WebSocket Handlers
def background_updater():
    """Фоновое обновление данных"""
    while True:
        try:
            cache = update_cache()
            socketio.emit("data_update", {
                "stages": cache["leads"],
                "info": cache["info"],
                "timestamp": cache["timestamp"]
            })
        except Exception as e:
            print(f"Ошибка в фоновом потоке: {e}")
        eventlet.sleep(5)  # Интервал обновления

@socketio.on("connect")
def handle_connect():
    print(f"Клиент подключен: {request.sid}")
    if not hasattr(app, "updater_thread"):
        app.updater_thread = socketio.start_background_task(background_updater)
    # Отправляем текущие данные сразу при подключении
    socketio.emit("data_update", {
        "stages": data_cache["leads"] or {},
        "info": data_cache["info"] or [],
        "timestamp": data_cache["timestamp"] or "00:00:00"
    })

def shutdown_handler(signum, frame):
    """Обработчик завершения работы"""
    print("Завершение работы...")
    if hasattr(app, "updater_thread"):
        app.updater_thread.kill()
    eventlet.sleep(1)
    exit(0)

if __name__ == "__main__":
    # Инициализация кеша при старте
    update_cache()
    
    # Регистрация обработчика завершения
    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)
    
    # Запуск сервера
    port = int(os.environ.get("PORT", 8080))
    print(f"Запуск сервера на порту {port}...")
    socketio.run(app, host="0.0.0.0", port=port)
