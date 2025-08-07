from flask import Flask, send_from_directory, jsonify, request, session, redirect, url_for
from flask_caching import Cache
import requests
import os
import time
import threading
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from pytz import timezone
import logging
from logging.handlers import RotatingFileHandler
import json
from functools import wraps

app = Flask(__name__, static_folder='static')

# Конфигурация приложения
app.config.update({
    'SECRET_KEY': os.environ.get('SECRET_KEY') or os.urandom(24),
    'CACHE_TYPE': 'SimpleCache',
    'CACHE_DEFAULT_TIMEOUT': 300,
    'BITRIX_REQUEST_TIMEOUT': 30,
    'MAX_PAGINATION_LIMIT': 500,
    'LOG_FILE': 'app.log',
    'LOG_LEVEL': logging.INFO,
    'WHITELIST_FILE': 'whitelist.json',
    'JSONIFY_PRETTYPRINT_REGULAR': False,
    'JSON_SORT_KEYS': False
})

# Инициализация кеширования
cache = Cache(app)

# Настройка логирования
handler = RotatingFileHandler(
    app.config['LOG_FILE'],
    maxBytes=1024 * 1024,
    backupCount=3
)
handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
app.logger.addHandler(handler)
app.logger.setLevel(app.config['LOG_LEVEL'])

# Конфигурация Bitrix24 API
HOOK = os.environ.get('BITRIX_HOOK', "https://ers2023.bitrix24.ru/rest/27/1bc1djrnc455xeth/")
UPDATE_INTERVAL = int(os.environ.get('UPDATE_INTERVAL', 300))  # 5 минут

STAGE_LABELS = {
    "На согласовании": "UC_A2DF81",
    "Перезвонить": "IN_PROCESS",
    "Приглашен к рекрутеру": "CONVERTED"
}

# Кеширование данных
user_cache = {"data": {}, "last": 0}
data_cache = {"data": {}, "timestamp": 0}
cache_lock = threading.Lock()
last_operator_status = defaultdict(dict)

class BitrixAPIError(Exception):
    pass

def load_whitelist():
    """Загрузка белого списка пользователей"""
    try:
        with open(app.config['WHITELIST_FILE']) as f:
            return json.load(f)['users']
    except Exception as e:
        app.logger.error(f"Error loading whitelist: {e}")
        return []

def check_auth(username, password):
    """Проверка учетных данных"""
    users = load_whitelist()
    return any(user['username'] == username and user['password'] == password for user in users)

def login_required(f):
    """Декоратор для защиты маршрутов"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'username' not in session:
            return jsonify({"status": "error", "message": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated_function

def get_moscow_time():
    tz = timezone("Europe/Moscow")
    return datetime.now(tz)

def get_range_dates():
    now = get_moscow_time()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.strftime("%Y-%m-%d %H:%M:%S"), now.strftime("%Y-%m-%d %H:%M:%S")

def make_bitrix_request(method, params=None, retries=2):
    """Выполнение запроса к Bitrix24 API с оптимизацией"""
    params = params or {}
    url = f"{HOOK}{method}"
    
    for attempt in range(retries):
        try:
            response = requests.post(
                url,
                json=params,
                timeout=app.config['BITRIX_REQUEST_TIMEOUT']
            )
            response.raise_for_status()
            data = response.json()
            
            if 'error' in data:
                raise BitrixAPIError(data.get('error_description', 'Unknown Bitrix error'))
                
            return data
            
        except (requests.exceptions.RequestException, ValueError) as e:
            app.logger.error(f"Bitrix request attempt {attempt + 1} failed: {str(e)}")
            if attempt == retries - 1:
                raise BitrixAPIError(f"Failed after {retries} attempts: {str(e)}")
            time.sleep(1)

@app.route('/login', methods=['POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        if check_auth(username, password):
            session['username'] = username
            return jsonify({"status": "success"})
        else:
            return jsonify({"status": "error", "message": "Invalid credentials"}), 401

@app.route('/logout')
def logout():
    session.pop('username', None)
    return jsonify({"status": "success"})

@app.route("/api/health")
def health_check():
    return jsonify({"status": "healthy"}), 200

@app.route("/api/leads/operators")
@login_required
def get_all_operators():
    """Оптимизированный endpoint для получения операторов"""
    try:
        with cache_lock:
            if time.time() - user_cache["last"] < 300 and user_cache["data"]:
                operators = set(user_cache["data"].values())
                return jsonify({
                    "status": "success",
                    "operators": sorted(list(operators)),
                    "timestamp": get_moscow_time().strftime("%H:%M:%S")
                })
            
            users = load_users()
            operators = set(users.values())
            
            return jsonify({
                "status": "success",
                "operators": sorted(list(operators)),
                "timestamp": get_moscow_time().strftime("%H:%M:%S")
            })
            
    except Exception as e:
        app.logger.error(f"Error in get_all_operators: {e}")
        return jsonify({
            "status": "error",
            "message": "Internal server error",
            "timestamp": get_moscow_time().strftime("%H:%M:%S")
        }), 500

@app.route("/api/leads/by-stage")
@login_required
def leads_by_stage():
    """Оптимизированный endpoint для получения статистики"""
    try:
        with cache_lock:
            if time.time() - data_cache["timestamp"] < UPDATE_INTERVAL:
                return jsonify(data_cache["data"])
            
            start, end = get_range_dates()
            users = load_users()
            data = {}
            
            # Параллельная загрузка данных по этапам
            for name, stage_id in STAGE_LABELS.items():
                leads = fetch_leads(stage_id, start, end)
                stats = Counter()
                
                for lead in leads:
                    if lead.get("ASSIGNED_BY_ID"):
                        stats[int(lead["ASSIGNED_BY_ID"])] += 1

                data[name] = {
                    "details": [
                        {
                            "operator": users.get(uid, f"ID {uid}"),
                            "count": cnt
                        } for uid, cnt in sorted(stats.items(), key=lambda x: -x[1])
                    ]
                }

            result = {
                "status": "success",
                "data": data,
                "timestamp": get_moscow_time().strftime("%H:%M:%S")
            }
            
            data_cache["data"] = result
            data_cache["timestamp"] = time.time()
            return jsonify(result)
            
    except Exception as e:
        app.logger.error(f"Error in leads_by_stage: {e}")
        return jsonify({
            "status": "error",
            "message": "Internal server error",
            "timestamp": get_moscow_time().strftime("%H:%M:%S")
        }), 500

@app.route('/')
@login_required
def dashboard():
    return send_from_directory(app.static_folder, 'dashboard.html')

@app.route('/<path:path>')
@login_required
def serve_static(path):
    return send_from_directory(app.static_folder, path)

@cache.memoize(timeout=300)
def load_users():
    """Оптимизированная загрузка пользователей"""
    current_time = time.time()
    if current_time - user_cache["last"] < 300 and user_cache["data"]:
        return user_cache["data"]
    
    users = {}
    try:
        response = make_bitrix_request("user.get.json", {"filter": {"ACTIVE": True}})
        
        if response.get("result"):
            for user in response["result"]:
                users[int(user["ID"])] = f'{user["NAME"]} {user["LAST_NAME"]}'
    
    except BitrixAPIError as e:
        app.logger.error(f"Error loading users: {e}")
        if not users:
            raise
    
    with cache_lock:
        user_cache["data"] = users
        user_cache["last"] = current_time
    
    return users

def fetch_leads(stage, start, end):
    """Оптимизированная загрузка лидов"""
    leads = []
    try:
        response = make_bitrix_request(
            "crm.lead.list.json",
            {
                "filter": {">=DATE_MODIFY": start, "<=DATE_MODIFY": end, "STATUS_ID": stage},
                "select": ["ASSIGNED_BY_ID"],
                "start": -1  # Получаем только количество
            }
        )
        
        if response.get("result"):
            total = response.get("total", 0)
            if total > 0:
                response = make_bitrix_request(
                    "crm.lead.list.json",
                    {
                        "filter": {">=DATE_MODIFY": start, "<=DATE_MODIFY": end, "STATUS_ID": stage},
                        "select": ["ASSIGNED_BY_ID"],
                        "start": 0,
                        "order": {"DATE_MODIFY": "DESC"}
                    }
                )
                leads = response.get("result", [])
    
    except BitrixAPIError as e:
        app.logger.error(f"Error fetching leads for {stage}: {e}")
    
    return leads

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, threaded=True)
