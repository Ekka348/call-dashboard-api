from flask import Flask, send_from_directory, jsonify
import requests, os, time, threading
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from pytz import timezone

app = Flask(__name__, static_folder='static')

# Конфигурация
HOOK = os.environ.get('BITRIX_HOOK', "https://ers2023.bitrix24.ru/rest/27/1bc1djrnc455xeth/")
UPDATE_INTERVAL = 60 
HISTORY_HOURS = 24
DATA_RETENTION_DAYS = 7

STAGE_LABELS = {
    "На согласовании": "UC_A2DF81",
    "Перезвонить": "IN_PROCESS",
    "Приглашен к рекрутеру": "CONVERTED"
}

# Кеширование
user_cache = {"data": {}, "last": 0}
data_cache = {
    "current": {},
    "hourly": defaultdict(list),
    "daily": defaultdict(list),
    "timestamp": 0
}
cache_lock = threading.Lock()
last_operator_status = defaultdict(dict)

def get_moscow_time():
    return datetime.now(timezone("Europe/Moscow"))

def get_date_ranges():
    now = get_moscow_time()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return {
        'today': (today_start.strftime("%Y-%m-%d %H:%M:%S"), now.strftime("%Y-%m-%d %H:%M:%S")),
        'hourly': [(now - timedelta(hours=i)).strftime("%Y-%m-%d %H:00:00") for i in range(HISTORY_HOURS)][::-1]
    }

def load_users():
    if time.time() - user_cache["last"] < 300:
        return user_cache["data"]
    
    users = {}
    try:
        start = 0
        while True:
            response = requests.post(f"{HOOK}user.get.json", json={"start": start}, timeout=20).json()
            if "result" not in response:
                break
            for user in response["result"]:
                users[int(user["ID"])] = f'{user["NAME"]} {user["LAST_NAME"]}'
            start = response.get("next", 0)
            if not start:
                break
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
                    "select": ["ID", "ASSIGNED_BY_ID", "TITLE", "STATUS_ID", "DATE_MODIFY"],
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

def check_for_changes(new_data):
    changes = []
    for stage_name, stage_data in new_data.items():
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

def update_history_data(current_data):
    now = get_moscow_time()
    current_hour = now.replace(minute=0, second=0, microsecond=0).strftime("%Y-%m-%d %H:00:00")
    
    for stage, data in current_data.items():
        total = sum(item['count'] for item in data['details'])
        data_cache['hourly'][stage].append({'timestamp': current_hour, 'count': total})
        if len(data_cache['hourly'][stage]) > HISTORY_HOURS:
            data_cache['hourly'][stage] = data_cache['hourly'][stage][-HISTORY_HOURS:]
    
    if now.hour == 0 and now.minute < 5:
        for stage, data in current_data.items():
            total = sum(item['count'] for item in data['details'])
            data_cache['daily'][stage].append({'timestamp': now.strftime("%Y-%m-%d"), 'count': total})
            if len(data_cache['daily'][stage]) > DATA_RETENTION_DAYS:
                data_cache['daily'][stage] = data_cache['daily'][stage][-DATA_RETENTION_DAYS:]

def get_lead_stats():
    with cache_lock:
        try:
            if time.time() - data_cache["timestamp"] < UPDATE_INTERVAL:
                return data_cache["current"]
            
            ranges = get_date_ranges()
            users = load_users()
            current_data = {}

            for name, stage_id in STAGE_LABELS.items():
                leads = fetch_leads(stage_id, *ranges['today'])
                stats = Counter()
                for lead in leads:
                    if lead.get("ASSIGNED_BY_ID"):
                        stats[int(lead["ASSIGNED_BY_ID"])] += 1

                current_data[name] = {
                    "details": [
                        {"operator": users.get(uid, f"ID {uid}"), "count": cnt}
                        for uid, cnt in sorted(stats.items(), key=lambda x: -x[1])
                    ]
                }

            update_history_data(current_data)
            data_cache["current"] = current_data
            data_cache["timestamp"] = time.time()
            
            return {
                "status": "success",
                "current": current_data,
                "changes": check_for_changes(current_data),
                "history": {
                    "hourly": {
                        "labels": [t['timestamp'][11:16] for t in data_cache['hourly'].get(list(STAGE_LABELS.keys())[0], [])],
                        "data": {stage: [d['count'] for d in data_cache['hourly'].get(stage, [])] 
                                for stage in STAGE_LABELS.keys()}
                    },
                    "daily": {
                        "labels": [t['timestamp'] for t in data_cache['daily'].get(list(STAGE_LABELS.keys())[0], [])],
                        "data": {stage: [d['count'] for d in data_cache['daily'].get(stage, [])] 
                                for stage in STAGE_LABELS.keys()}
                    }
                },
                "timestamp": get_moscow_time().strftime("%Y-%m-%d %H:%M:%S")
            }
        except Exception as e:
            print(f"Error in get_lead_stats: {e}")
            return {
                "status": "error",
                "message": str(e),
                "timestamp": get_moscow_time().strftime("%Y-%m-%d %H:%M:%S")
            }

@app.route("/api/leads/operators")
def get_all_operators():
    try:
        ranges = get_date_ranges()
        users = load_users()
        operators = set()
        
        for stage_id in STAGE_LABELS.values():
            leads = fetch_leads(stage_id, *ranges['today'])
            for lead in leads:
                if lead.get("ASSIGNED_BY_ID"):
                    operator_name = users.get(int(lead["ASSIGNED_BY_ID"]), f"ID {lead['ASSIGNED_BY_ID']}")
                    operators.add(operator_name)
        
        return jsonify({
            "status": "success",
            "operators": sorted(list(operators)),
            "timestamp": get_moscow_time().strftime("%Y-%m-%d %H:%M:%S")
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e),
            "timestamp": get_moscow_time().strftime("%Y-%m-%d %H:%M:%S")
        }), 500

@app.route("/api/leads/by-stage")
def leads_by_stage():
    try:
        data = get_lead_stats()
        return jsonify(data)
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e),
            "timestamp": get_moscow_time().strftime("%Y-%m-%d %H:%M:%S")
        }), 500

@app.route('/')
def serve_index():
    return send_from_directory(app.static_folder, 'dashboard.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory(app.static_folder, path)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
