from flask import Flask, send_from_directory, jsonify, request, session, redirect, url_for, render_template_string
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
    'BITRIX_REQUEST_TIMEOUT': 60,
    'MAX_PAGINATION_LIMIT': 500,
    'LOG_FILE': 'app.log',
    'LOG_LEVEL': logging.INFO,
    'WHITELIST_FILE': 'whitelist.json',
    'SESSION_COOKIE_SECURE': True,
    'SESSION_COOKIE_SAMESITE': 'Lax',
    'PERMANENT_SESSION_LIFETIME': timedelta(days=1)
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
            if request.path.startswith('/api'):
                return jsonify({"status": "error", "message": "Unauthorized"}), 401
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    """Перенаправление на login или dashboard"""
    if 'username' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Обработка входа"""
    if request.method == 'GET':
        return render_template_string('''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Авторизация</title>
                <style>
                    body { font-family: Arial; max-width: 400px; margin: 50px auto; padding: 20px; }
                    .login-form { background: #fff; padding: 20px; border-radius: 5px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }
                    .form-group { margin-bottom: 15px; }
                    label { display: block; margin-bottom: 5px; }
                    input { width: 100%; padding: 8px; box-sizing: border-box; }
                    button { background: #4285f4; color: white; border: none; padding: 10px; width: 100%; cursor: pointer; }
                    .error { color: #ea4335; margin-top: 10px; }
                </style>
            </head>
            <body>
                <div class="login-form">
                    <h2>Авторизация</h2>
                    {% if error %}
                    <div class="error">{{ error }}</div>
                    {% endif %}
                    <form method="POST">
                        <div class="form-group">
                            <label>Логин</label>
                            <input type="text" name="username" required>
                        </div>
                        <div class="form-group">
                            <label>Пароль</label>
                            <input type="password" name="password" required>
                        </div>
                        <button type="submit">Войти</button>
                    </form>
                </div>
            </body>
            </html>
        ''', error=request.args.get('error'))
    
    username = request.form.get('username')
    password = request.form.get('password')
    
    if check_auth(username, password):
        session['username'] = username
        next_page = request.args.get('next') or url_for('dashboard')
        return redirect(next_page)
    else:
        return redirect(url_for('login', error='Неверные учетные данные'))

@app.route('/logout')
def logout():
    """Обработка выхода"""
    session.pop('username', None)
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    """Основная страница дашборда"""
    return send_from_directory(app.static_folder, 'dashboard.html')

@app.route("/api/health")
def health_check():
    """Проверка здоровья сервера"""
    return jsonify({"status": "healthy"}), 200

@app.route("/api/leads/operators")
@login_required
def get_all_operators():
    """Получение списка операторов"""
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
    """Основной endpoint для статистики"""
    try:
        with cache_lock:
            if time.time() - data_cache["timestamp"] < UPDATE_INTERVAL:
                return jsonify(data_cache["data"])
            
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

@app.route('/<path:path>')
@login_required
def serve_static(path):
    """Отдача статических файлов"""
    return send_from_directory(app.static_folder, path)

def get_moscow_time():
    """Текущее время в Москве"""
    tz = timezone("Europe/Moscow")
    return datetime.now(tz)

def get_range_dates():
    """Получение диапазона дат за сегодня"""
    now = get_moscow_time()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.strftime("%Y-%m-%d %H:%M:%S"), now.strftime("%Y-%m-%d %H:%M:%S")

def make_bitrix_request(method, params=None, retries=2):
    """Запрос к Bitrix24 API"""
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

@cache.memoize(timeout=300)
def load_users():
    """Загрузка пользователей с кешированием"""
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
    """Получение лидов по этапу"""
    leads = []
    try:
        response = make_bitrix_request(
            "crm.lead.list.json",
            {
                "filter": {">=DATE_MODIFY": start, "<=DATE_MODIFY": end, "STATUS_ID": stage},
                "select": ["ASSIGNED_BY_ID"],
                "start": -1
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
