from flask import Flask, send_from_directory, jsonify, request, session, redirect, url_for
from flask_caching import Cache
import requests
import os
import time
import threading
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from pytz import timezone
from copy import deepcopy
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
    'BITRIX_REQUEST_TIMEOUT': 60,
    'MAX_PAGINATION_LIMIT': 1000,
    'LOG_FILE': 'app.log',
    'LOG_LEVEL': logging.INFO,
    'WHITELIST_FILE': 'whitelist.json'
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
UPDATE_INTERVAL = int(os.environ.get('UPDATE_INTERVAL', 60))

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

# Аутентификация
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
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

# Вспомогательные функции для Bitrix API
def get_moscow_time():
    tz = timezone("Europe/Moscow")
    return datetime.now(tz)

def get_range_dates():
    now = get_moscow_time()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.strftime("%Y-%m-%d %H:%M:%S"), now.strftime("%Y-%m-%d %H:%M:%S")

def make_bitrix_request(method, params=None, retries=3):
    """Выполнение запроса к Bitrix24 API"""
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
            time.sleep(2 ** attempt)

# Маршруты аутентификации
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if check_auth(username, password):
            session['username'] = username
            next_page = request.args.get('next') or url_for('dashboard')
            return redirect(next_page)
        else:
            return "Неверные учетные данные", 401
    
    return '''
        <form method="POST">
            <input type="text" name="username" placeholder="Логин" required>
            <input type="password" name="password" placeholder="Пароль" required>
            <button type="submit">Войти</button>
        </form>
    '''

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect(url_for('login'))

# Основные маршруты API
@app.route("/api/leads/operators")
@login_required
def get_all_operators():
    """Получение списка всех операторов"""
    try:
        start, end = get_range_dates()
        users = load_users()
        operators = set()
        
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
        app.logger.error(f"Error in get_all_operators: {e}")
        return jsonify({
            "status": "error",
            "message": "Internal server error",
            "timestamp": get_moscow_time().strftime("%H:%M:%S")
        }), 500

@app.route("/api/leads/by-stage")
@login_required
def leads_by_stage():
    """Основной endpoint для получения статистики по этапам"""
    try:
        with cache_lock:
            if time.time() - data_cache["timestamp"] < UPDATE_INTERVAL:
                return jsonify(data_cache["data"])
            
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

                operators_data = []
                for uid, cnt in sorted(stats.items(), key=lambda x: -x[1]):
                    operator_name = users.get(uid, f"ID {uid}")
                    operators_data.append({
                        "operator": operator_name,
                        "count": cnt
                    })

                data[name] = {"details": operators_data}

            result = {
                "status": "success",
                "data": data,
                "changes": check_for_operator_changes({"data": data}),
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

# Маршруты для статических файлов
@app.route('/')
@login_required
def dashboard():
    return send_from_directory(app.static_folder, 'dashboard.html')

@app.route('/<path:path>')
@login_required
def serve_static(path):
    return send_from_directory(app.static_folder, path)

# Вспомогательные функции
@cache.memoize(timeout=300)
def load_users():
    """Загрузка пользователей с кешированием и пагинацией"""
    current_time = time.time()
    if current_time - user_cache["last"] < 300 and user_cache["data"]:
        return user_cache["data"]
    
    users = {}
    try:
        start = 0
        requests_count = 0
        
        while requests_count < app.config['MAX_PAGINATION_LIMIT']:
            response = make_bitrix_request(
                "user.get.json",
                {"start": start}
            )
            
            if not response.get("result"):
                break
                
            for user in response["result"]:
                users[int(user["ID"])] = f'{user["NAME"]} {user["LAST_NAME"]}'
            
            if not response.get("next"):
                break
                
            start = response["next"]
            requests_count += 1
            
    except BitrixAPIError as e:
        app.logger.error(f"Error loading users: {e}")
        if not users:
            raise
    
    with cache_lock:
        user_cache["data"] = users
        user_cache["last"] = current_time
    
    return users

def fetch_leads(stage, start, end):
    """Получение лидов с обработкой пагинации и ошибок"""
    leads = []
    try:
        offset = 0
        requests_count = 0
        
        while requests_count < app.config['MAX_PAGINATION_LIMIT']:
            response = make_bitrix_request(
                "crm.lead.list.json",
                {
                    "filter": {">=DATE_MODIFY": start, "<=DATE_MODIFY": end, "STATUS_ID": stage},
                    "select": ["ID", "ASSIGNED_BY_ID", "TITLE", "STATUS_ID", "DATE_MODIFY"],
                    "start": offset
                }
            )
            
            if not response.get("result"):
                break
                
            leads.extend(response["result"])
            offset = response.get("next", 0)
            if not offset:
                break
                
            requests_count += 1
            
    except BitrixAPIError as e:
        app.logger.error(f"Error fetching leads for {stage}: {e}")
    
    return leads

def check_for_operator_changes(new_data):
    """Обнаружение изменений в статусах операторов"""
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=os.environ.get('FLASK_DEBUG', 'false').lower() == 'true')
