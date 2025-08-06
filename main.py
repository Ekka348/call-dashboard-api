from flask import Flask, send_from_directory, jsonify
from flask_socketio import SocketIO
import requests, os, time, threading
from datetime import datetime, timedelta
from collections import Counter
from pytz import timezone

# Инициализация приложения
app = Flask(__name__, static_folder='static')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')

# Конфигурация SocketIO
socketio = SocketIO(app,
                   cors_allowed_origins="*",
                   ping_timeout=60,
                   ping_interval=25,
                   engineio_logger=False,
                   async_mode='eventlet')

# Константы
HOOK = os.environ.get('BITRIX_HOOK', "https://ers2023.bitrix24.ru/rest/27/1bc1djrnc455xeth/")
UPDATE_INTERVAL = 10  # Интервал обновления в секундах

STAGE_LABELS = {
    "На согласовании": "UC_A2DF81",
    "Перезвонить": "IN_PROCESS",
    "Приглашен к рекрутеру": "CONVERTED",
}

# Кеширование
user_cache = {"data": {}, "last": 0}
data_cache = {"data": {}, "timestamp": 0}
cache_lock = threading.Lock()

def get_range_dates(rtype):
    tz = timezone("Europe/Moscow")
    now = datetime.now(tz)
    if rtype == "week":
        start = now - timedelta(days=now.weekday())
    elif rtype == "month":
        start = now.replace(day=1)
    else:
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
                timeout=10
            ).json()
            
            for user in response.get("result", []):
                users[int(user["ID"])] = f'{user["NAME"]} {user["LAST_NAME"]}'
            
            if "next" not in response:
                break
            start = response["next"]
    except Exception as e:
        print(f"Error loading users: {e}")
    
    user_cache["data"] = users
    user_cache["last"] = time.time()
    return users

def fetch_leads(stage, start, end):
    leads = []
    try:
        offset = 0
        while True:
            response = requests.post(
                f"{HOOK}crm.lead.list.json",
                json={
                    "filter": {">=DATE_MODIFY": start, "<=DATE_MODIFY": end, "STATUS_ID": stage},
                    "select": ["ID", "ASSIGNED_BY_ID", "DATE_CREATE", "DATE_MODIFY", "STATUS_ID"],
                    "start": offset
                },
                timeout=15
            ).json()
            
            page = response.get("result", [])
            if not page:
                break
                
            leads.extend(page)
            offset = response.get("next", 0)
            if not offset:
                break
    except Exception as e:
        print(f"Error fetching leads for {stage}: {e}")
    
    return leads

def fetch_all_leads(stage):
    leads = []
    try:
        offset = 0
        while True:
            response = requests.post(
                f"{HOOK}crm.lead.list.json",
                json={
                    "filter": {"STATUS_ID": stage},
                    "select": ["ID"],
                    "start": offset
                },
                timeout=15
            ).json()
            
            page = response.get("result", [])
            if not page:
                break
                
            leads.extend(page)
            offset = response.get("next", 0)
            if not offset:
                break
    except Exception as e:
        print(f"Error fetching all leads for {stage}: {e}")
    
    return leads

def get_lead_stats():
    with cache_lock:
        if time.time() - data_cache["timestamp"] < UPDATE_INTERVAL:
            return data_cache["data"]
        
        start, end = get_range_dates("today")
        users = load_users()
        data = {}

        for name, stage_id in STAGE_LABELS.items():
            if name in GROUPED_STAGES:
                leads = fetch_all_leads(stage_id)
                data[name] = {"grouped": True, "count": len(leads)}
            else:
                leads = fetch_leads(stage_id, start, end)
                stats = Counter()
                for lead in leads:
                    uid = lead.get("ASSIGNED_BY_ID")
                    if uid:
                        stats[int(uid)] += 1

                details = [
                    {"operator": users.get(uid, f"ID {uid}"), "count": cnt}
                    for uid, cnt in sorted(stats.items(), key=lambda x: -x[1])
                ]

                data[name] = {"grouped": False, "details": details}

        result = {"range": "today", "data": data}
        data_cache["data"] = result
        data_cache["timestamp"] = time.time()
        return result

# API Endpoints
@app.route("/api/leads/by-stage")
def leads_by_stage():
    return jsonify(get_lead_stats())

@app.route("/api/leads/info-stages-today")
def info_stages_today():
    result = []
    for name in GROUPED_STAGES:
        stage = STAGE_LABELS[name]
        leads = fetch_all_leads(stage)
        result.append({"name": name, "count": len(leads)})
    return jsonify({"range": "total", "info": result})

# WebSocket Handlers
@socketio.on('connect')
def handle_connect():
    print(f'Client connected: {request.sid}')
    socketio.emit('init', get_lead_stats())

def background_updater():
    while True:
        try:
            data = get_lead_stats()
            socketio.emit('update', data)
            print(f"Data updated at {datetime.now()}")
        except Exception as e:
            print(f"Update error: {e}")
        time.sleep(UPDATE_INTERVAL)

# Static Files
@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'dashboard.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(app.static_folder, path)

if __name__ == "__main__":
    # Запускаем фоновый поток для обновлений
    threading.Thread(target=background_updater, daemon=True).start()
    
    # Конфигурация для Railway
    port = int(os.environ.get("PORT", 8080))
    host = '0.0.0.0'
    
    socketio.run(app, host=host, port=port, debug=False)
