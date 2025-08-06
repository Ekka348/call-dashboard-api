from flask import Flask, send_from_directory, jsonify, request
import requests, os, time, threading
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from pytz import timezone
from copy import deepcopy

app = Flask(__name__, static_folder='static')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')

# Настройки подключения к Bitrix24
HOOK = os.environ.get('BITRIX_HOOK', "https://ers2023.bitrix24.ru/rest/27/1bc1djrnc455xeth/")
UPDATE_INTERVAL = 60  # Интервал обновления в секундах (1 минута)

STAGE_LABELS = {
    "На согласовании": "UC_A2DF81",
    "Перезвонить": "IN_PROCESS",
    "Приглашен к рекрутеру": "CONVERTED"
}

# Кеширование
user_cache = {"data": {}, "last": 0}
data_cache = {"data": {}, "timestamp": 0}
trend_cache = {
    "day": {"data": {}, "timestamp": 0},
    "hour": {"data": {}, "timestamp": 0}
}
CACHE_TIMEOUT = 300  # 5 минут
cache_lock = threading.Lock()
last_operator_status = defaultdict(dict)

def get_moscow_time():
    tz = timezone("Europe/Moscow")
    return datetime.now(tz)

def get_range_dates():
    now = get_moscow_time()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.strftime("%Y-%m-%d %H:%M:%S"), now.strftime("%Y-%m-%d %H:%M:%S")

def load_users():
    if time.time() - user_cache["last"] < CACHE_TIMEOUT:
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
                    "select": ["ID", "ASSIGNED_BY_ID", "DATE_MODIFY"],
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
                    'old_count': old_count,
                    'new_count': new_count,
                    'diff': new_count - old_count
                })
            last_operator_status[stage_name][operator_name] = new_count
    return changes

def get_lead_stats():
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

        result = {
            "range": "today", 
            "data": data,
            "changes": check_for_operator_changes({"data": data}),
            "timestamp": get_moscow_time().strftime("%H:%M:%S")
        }
        
        data_cache["data"] = result
        data_cache["timestamp"] = time.time()
        return result

@app.route("/api/leads/trend")
def leads_trend():
    period = request.args.get('period', 'day')
    
    # Проверка кеша
    if time.time() - trend_cache[period]["timestamp"] < CACHE_TIMEOUT:
        return jsonify(trend_cache[period]["data"])
    
    tz = timezone("Europe/Moscow")
    now = datetime.now(tz)
    stats = defaultdict(list)
    
    try:
        if period == 'day':
            # Данные за последние 7 дней
            days = []
            for i in range(7):
                day = now - timedelta(days=6-i)
                days.append(day.strftime("%a"))  # Сокращенные названия дней
                
                day_start = day.replace(hour=0, minute=0, second=0)
                day_end = day.replace(hour=23, minute=59, second=59)
                
                for name, stage_id in STAGE_LABELS.items():
                    leads = fetch_leads(stage_id, day_start.strftime("%Y-%m-%d %H:%M:%S"), 
                                      day_end.strftime("%Y-%m-%d %H:%M:%S"))
                    stats[name].append(len(leads))
            
            result = {"days": days, "stats": stats}
        else:
            # Данные по часам за текущий день
            day_start = now.replace(hour=0, minute=0, second=0)
            
            for hour in range(24):
                hour_start = day_start + timedelta(hours=hour)
                hour_end = hour_start + timedelta(hours=1)
                
                for name, stage_id in STAGE_LABELS.items():
                    if hour not in range(9, 19):  # Только рабочее время (9:00-18:59)
                        stats[name].append(0)
                        continue
                        
                    leads = fetch_leads(stage_id, hour_start.strftime("%Y-%m-%d %H:%M:%S"), 
                                      hour_end.strftime("%Y-%m-%d %H:%M:%S"))
                    stats[name].append(len(leads))
            
            result = {"stats": stats}
        
        # Сохраняем в кеш
        trend_cache[period] = {
            "data": result,
            "timestamp": time.time()
        }
        
        return jsonify(result)
        
    except Exception as e:
        print(f"Error generating trend data: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/leads/by-stage")
def leads_by_stage():
    return jsonify(get_lead_stats())

@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'dashboard.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(app.static_folder, path)

def background_updater():
    while True:
        try:
            # Обновляем основные данные
            get_lead_stats()
            
            # Периодически обновляем кеш графиков
            if time.time() - trend_cache["day"]["timestamp"] > CACHE_TIMEOUT:
                leads_trend()
            
            time.sleep(UPDATE_INTERVAL)
        except Exception as e:
            print(f"Update error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    # Запускаем фоновое обновление в отдельном потоке
    threading.Thread(target=background_updater, daemon=True).start()
    
    # Запускаем Flask-приложение
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
