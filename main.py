from flask import Flask, send_from_directory, jsonify, request
import requests, os, time, threading
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from pytz import timezone
from copy import deepcopy

app = Flask(__name__, static_folder='static')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')

HOOK = os.environ.get('BITRIX_HOOK', "https://ers2023.bitrix24.ru/rest/27/1bc1djrnc455xeth/")
UPDATE_INTERVAL = 60  # Интервал обновления в секундах

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

def get_moscow_time():
    tz = timezone("Europe/Moscow")
    return datetime.now(tz)

def get_range_dates():
    now = get_moscow_time()
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
        try:
            # Используем кеш, если данные свежие
            if time.time() - data_cache["timestamp"] < UPDATE_INTERVAL:
                return data_cache["data"]
            
            start, end = get_range_dates()
            users = load_users()
            data = {}
            changes = []

            for name, stage_id in STAGE_LABELS.items():
                leads = fetch_leads(stage_id, start, end)
                stats = Counter()
                
                for lead in leads:
                    if lead.get("ASSIGNED_BY_ID"):
                        stats[int(lead["ASSIGNED_BY_ID"])] += 1

                # Формируем данные по операторам
                operators_data = []
                for uid, cnt in sorted(stats.items(), key=lambda x: -x[1]):
                    operator_name = users.get(uid, f"ID {uid}")
                    operators_data.append({
                        "operator": operator_name,
                        "count": cnt
                    })
                    
                    # Проверяем изменения
                    old_count = last_operator_status[name].get(operator_name, 0)
                    if old_count != cnt:
                        changes.append({
                            'operator': operator_name,
                            'old_count': old_count,
                            'new_count': cnt,
                            'diff': cnt - old_count
                        })
                    last_operator_status[name][operator_name] = cnt

                data[name] = {
                    "details": operators_data
                }

            result = {
                "status": "success",
                "data": data,
                "changes": changes,
                "timestamp": get_moscow_time().strftime("%H:%M:%S")
            }
            
            data_cache["data"] = result
            data_cache["timestamp"] = time.time()
            return result
            
        except Exception as e:
            print(f"Error in get_lead_stats: {e}")
            raise

@app.route("/api/leads/operators")
def get_all_operators():
    try:
        start, end = get_range_dates()
        users = load_users()
        operators = set()
        
        # Получаем всех операторов, у которых есть лиды в любом из статусов
        for stage_id in STAGE_LABELS.values():
            leads = fetch_leads(stage_id, start, end)
            for lead in leads:
                if lead.get("ASSIGNED_BY_ID"):
                    operator_name = users.get(int(lead["ASSIGNED_BY_ID"]), f"ID {lead['ASSIGNED_BY_ID']}")
                    operators.add(operator_name)
        
        return jsonify({
            "status": "success",
            "operators": sorted(list(operators)),
            "timestamp": get_moscow_time().strftime("%H:%M:%S")
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e),
            "timestamp": get_moscow_time().strftime("%H:%M:%S")
        }), 500

@app.route("/api/leads/updates")
def get_updates():
    try:
        with cache_lock:
            # Получаем текущие данные
            current_data = get_lead_stats()
            
            # Создаем компактный ответ только с изменениями
            updates = {}
            for stage_name, stage_data in current_data['data'].items():
                updates[stage_name] = {
                    'total_count': sum(op['count'] for op in stage_data['details']),
                    'operators': stage_data['details']
                }
            
            return jsonify({
                'status': 'success',
                'updates': updates,
                'timestamp': get_moscow_time().strftime("%H:%M:%S")
            })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e),
            'timestamp': get_moscow_time().strftime("%H:%M:%S")
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
            "timestamp": get_moscow_time().strftime("%H:%M:%S")
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
