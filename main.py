from flask import Flask, send_from_directory, jsonify, request
from flask_socketio import SocketIO
import requests, os, time, threading
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from pytz import timezone
from copy import deepcopy

app = Flask(__name__, static_folder='static')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')

# Настройки SocketIO с увеличенными таймаутами
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    ping_timeout=300,
    ping_interval=60,
    engineio_logger=True,
    async_mode='eventlet',
    max_http_buffer_size=1e8
)

HOOK = os.environ.get('BITRIX_HOOK', "https://ers2023.bitrix24.ru/rest/27/1bc1djrnc455xeth/")
UPDATE_INTERVAL = 30  # Интервал обновления в секундах

STAGE_LABELS = {
    "На согласовании": "UC_A2DF81",
    "Перезвонить": "IN_PROCESS",
    "Приглашен к рекрутеру": "CONVERTED"
}

# Кеширование
user_cache = {"data": {}, "last": 0}
data_cache = {"data": {}, "timestamp": 0}
cache_lock = threading.Lock()
last_operator_status = defaultdict(dict)
last_emitted_data = None

def get_range_dates():
    tz = timezone("Europe/Moscow")
    now = datetime.now(tz)
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
                timeout=20
            ).json()
            
            if "result" not in response:
                break
                
            for user in response["result"]:
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
                    "select": ["ID", "ASSIGNED_BY_ID"],
                    "start": offset
                },
                timeout=20
            ).json()
            
            if "result" not in response:
                break
                
            leads.extend(response["result"])
            offset = response.get("next", 0)
            if not offset:
                break
    except Exception as e:
        print(f"Error fetching leads for {stage}: {e}")
    
    return leads

def check_for_operator_changes(new_data):
    changes = []
    for stage_name, stage_data in new_data['data'].items():
        for operator in stage_data['details']:
            operator_name = operator['operator']
            new_count = operator['count']
            old_count = last_operator_status[stage_name].get(operator_name, 0)
            
            if new_count != old_count:
                changes.append({
                    'stage': stage_name,
                    'operator': operator_name,
                    'diff': new_count - old_count
                })
            last_operator_status[stage_name][operator_name] = new_count
    return changes

def get_lead_stats():
    global last_emitted_data
    with cache_lock:
        if time.time() - data_cache["timestamp"] < UPDATE_INTERVAL:
            return data_cache["data"]
        
        start, end = get_range_dates()
        users = load_users()
        data = {}

        for name, stage_id in STAGE_LABELS.items():
            leads = fetch_leads(stage_id, start, end)
            stats = Counter()
            for lead in leads:
                if lead.get("ASSIGNED_BY_ID"):
                    stats[int(lead["ASSIGNED_BY_ID"])] += 1

            data[name] = {
                "details": [
                    {"operator": users.get(uid, f"ID {uid}"), "count": cnt}
                    for uid, cnt in sorted(stats.items(), key=lambda x: -x[1])
                ]
            }

        result = {"range": "today", "data": data}
        changes = check_for_operator_changes(result)
        
        if changes or result != last_emitted_data:
            last_emitted_data = deepcopy(result)
            socketio.emit('full_update', {
                'data': result,
                'changes': changes,
                'timestamp': datetime.now().timestamp()  # Исправлено: отправляем timestamp
            })
        
        data_cache["data"] = result
        data_cache["timestamp"] = time.time()
        return result

@app.route("/api/leads/by-stage")
def leads_by_stage():
    return jsonify(get_lead_stats())

@socketio.on('connect')
def handle_connect():
    print(f'Client connected: {request.sid}')
    socketio.emit('init', get_lead_stats())

@socketio.on('request_full_update')
def handle_full_update_request():
    socketio.emit('full_update', get_lead_stats())

def background_updater():
    while True:
        try:
            get_lead_stats()
            time.sleep(UPDATE_INTERVAL)
        except Exception as e:
            print(f"Update error: {e}")
            time.sleep(10)

@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'dashboard.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(app.static_folder, path)

if __name__ == "__main__":
    threading.Thread(target=background_updater, daemon=True).start()
    port = int(os.environ.get("PORT", 8080))
    socketio.run(app, host='0.0.0.0', port=port, debug=False)
