from flask import Flask, request, redirect, session, jsonify, render_template
from functools import wraps, lru_cache
import requests, os, time, json
from datetime import datetime, timedelta
from collections import defaultdict
from pytz import timezone
from threading import Thread, Lock
import logging
from logging.handlers import RotatingFileHandler
from flask_socketio import SocketIO
from gevent import monkey

# Инициализация патчинга для gevent
monkey.patch_all()

app = Flask(__name__)
socketio = SocketIO(app, async_mode='gevent')

# Конфигурация приложения
class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", os.urandom(24))
    BITRIX_HOOK = os.environ.get("BITRIX_HOOK_URL", "https://ers2023.bitrix24.ru/rest/27/1bc1djrnc455xeth/")
    SESSION_TIMEOUT = 3600  # 1 час
    USER_CACHE_TIMEOUT = 300  # 5 минут
    MAX_LOGIN_ATTEMPTS = 5
    LOG_FILE = 'app.log'
    DATA_UPDATE_INTERVAL = 15  # секунд
    BITRIX_TIMEOUT = 30  # увеличенный таймаут для запросов с историей
    TARGET_USERS = {
        3037: "Старицын Георгий",
        3025: "Гусева Екатерина",
        # ... остальные пользователи из вашего списка ...
        29: "Носарев Алексей"
    }
    STAGE_LABELS = {
        "Перезвонить": {"id": "IN_PROCESS", "semantic": "P"},
        "На согласовании": {"id": "UC_A2DF81", "semantic": "P"}, 
        "Приглашен к рекрутеру": {"id": "CONVERTED", "semantic": "S"},
        "НДЗ": {"id": "5", "semantic": "P"},
        "НДЗ 2": {"id": "9", "semantic": "P"}
    }

app.config.from_object(Config)
app.secret_key = app.config['SECRET_KEY']

# Настройка логирования
handler = RotatingFileHandler(
    app.config['LOG_FILE'],
    maxBytes=10000,
    backupCount=1,
    encoding='utf-8'
)
handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
handler.setLevel(logging.INFO)
app.logger.addHandler(handler)
app.logger.setLevel(logging.INFO)

# Глобальный кэш данных
data_cache = {
    "leads_by_stage": {},
    "operators_stats": {},
    "total_leads": 0,
    "last_updated": 0,
    "last_error": None,
    "current_month": "",
    "users": {}
}
cache_lock = Lock()

# Декораторы
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "login" not in session:
            return redirect("/auth")
        if time.time() - session.get('last_activity', 0) > app.config['SESSION_TIMEOUT']:
            session.clear()
            return redirect("/auth?timeout=1")
        session['last_activity'] = time.time()
        return f(*args, **kwargs)
    return wrapper

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session.get("role") != "admin":
            return jsonify({"error": "Forbidden"}), 403
        return f(*args, **kwargs)
    return wrapper

# Вспомогательные функции
def log_error(message, exc=None):
    error_msg = f"{message}: {str(exc) if exc else 'No details'}"
    app.logger.error(error_msg)
    with cache_lock:
        data_cache["last_error"] = error_msg

def find_user(login):
    try:
        with open("whitelist.json", "r", encoding="utf-8") as f:
            users = json.load(f)
        return next((u for u in users if u["login"] == login), None)
    except Exception as e:
        log_error("Ошибка загрузки whitelist.json", e)
        return None

def get_current_month_range():
    tz = timezone("Europe/Moscow")
    now = datetime.now(tz)
    first_day = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_day = (now.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    month_name = first_day.strftime("%B %Y")
    return (
        first_day.strftime("%Y-%m-%d %H:%M:%S"),
        last_day.strftime("%Y-%m-%d 23:59:59"),
        month_name
    )

# Функции работы с Bitrix API
@lru_cache(maxsize=1000)
def get_status_history(lead_id, date_from, date_to):
    try:
        params = {
            "filter": {
                "ENTITY_ID": lead_id,
                "ENTITY_TYPE": "LEAD",
                "FIELD": "STATUS_ID",
                ">=DATE_CREATE": date_from,
                "<=DATE_CREATE": date_to
            },
            "select": ["ID", "FIELD", "FROM_VALUE", "TO_VALUE", "DATE_CREATE"],
            "start": -1  # получаем все записи без пагинации
        }
        
        response = requests.post(
            f"{app.config['BITRIX_HOOK']}crm.timeline.list.json",
            json=params,
            timeout=app.config['BITRIX_TIMEOUT']
        )
        
        response.raise_for_status()
        data = response.json()
        
        if "error" in data:
            error_msg = data.get("error_description", "Unknown Bitrix API error")
            app.logger.error(f"Bitrix API timeline error: {error_msg}")
            raise Exception(f"Bitrix API timeline: {error_msg}")
        
        history = []
        for item in data.get("result", []):
            history.append({
                "STATUS_ID": item["TO_VALUE"],
                "DATE": item["DATE_CREATE"]
            })
        
        return history
        
    except Exception as e:
        log_error(f"Error getting status history for lead {lead_id}", e)
        return []

def fetch_leads(stage_name, date_from, date_to):
    try:
        stage_config = app.config['STAGE_LABELS'][stage_name]
        params = {
            "filter": {
                "ASSIGNED_BY_ID": list(app.config['TARGET_USERS'].keys()),
                ">=DATE_MODIFY": date_from,
                "<=DATE_MODIFY": date_to
            },
            "select": ["ID", "ASSIGNED_BY_ID", "STATUS_ID", "DATE_MODIFY", "STATUS_SEMANTIC_ID"],
            "start": -1  # получаем все записи без пагинации
        }
        
        # Для стадий в процессе используем семантику
        if stage_config["semantic"] == "P":
            params["filter"]["STATUS_SEMANTIC_ID"] = "P"
        
        app.logger.info(f"Fetching leads for stage {stage_name} with params: {params}")
        
        response = requests.post(
            f"{app.config['BITRIX_HOOK']}crm.lead.list.json",
            json=params,
            timeout=app.config['BITRIX_TIMEOUT']
        )
        
        response.raise_for_status()
        data = response.json()
        
        if "error" in data:
            error_msg = data.get("error_description", "Unknown Bitrix API error")
            app.logger.error(f"Bitrix API error: {error_msg}")
            raise Exception(f"Bitrix API: {error_msg}")
        
        filtered_leads = []
        for lead in data.get("result", []):
            # Для стадии "Перезвонить" проверяем историю изменений
            if stage_name == "Перезвонить":
                history = get_status_history(lead["ID"], date_from, date_to)
                if any(h["STATUS_ID"] == stage_config["id"] for h in history):
                    filtered_leads.append(lead)
            else:
                # Для других стадий проверяем текущий статус
                if lead["STATUS_ID"] == stage_config["id"]:
                    filtered_leads.append(lead)
        
        app.logger.info(f"Filtered {len(filtered_leads)} leads for stage {stage_name}")
        return filtered_leads
        
    except requests.exceptions.RequestException as e:
        log_error(f"Request error fetching leads (stage: {stage_name})", e)
        return []
    except Exception as e:
        log_error(f"Error fetching leads (stage: {stage_name})", e)
        return []

def load_users():
    try:
        users = {}
        for user_id, user_name in app.config['TARGET_USERS'].items():
            users[user_id] = {
                "name": user_name,
                "email": f"{user_name.split()[0].lower()}.{user_name.split()[1].lower()}@example.com"
            }
        return users
    except Exception as e:
        log_error("Error loading target users", e)
        return {}

# Фоновое обновление данных
def update_cache():
    while True:
        try:
            app.logger.info("Starting cache update...")
            start_time = time.time()
            
            month_start, month_end, month_name = get_current_month_range()
            users = load_users()
            
            leads_by_stage = {}
            total_leads = 0
            
            for stage_name in app.config['STAGE_LABELS'].keys():
                leads = fetch_leads(stage_name, month_start, month_end)
                
                operator_stats = defaultdict(int)
                for lead in leads:
                    if lead.get("ASSIGNED_BY_ID"):
                        operator_id = int(lead["ASSIGNED_BY_ID"])
                        operator_stats[operator_id] += 1
                
                stage_data = []
                for user_id in app.config['TARGET_USERS'].keys():
                    operator_info = users.get(user_id, {"name": f"ID {user_id}", "email": ""})
                    stage_data.append({
                        "operator": operator_info["name"],
                        "count": operator_stats.get(user_id, 0),
                        "user_id": user_id,
                        "email": operator_info["email"]
                    })
                
                stage_data.sort(key=lambda x: (-x["count"], x["operator"]))
                leads_by_stage[stage_name] = stage_data
                total_leads += len(leads)
            
            with cache_lock:
                data_cache.update({
                    "leads_by_stage": leads_by_stage,
                    "total_leads": total_leads,
                    "last_updated": time.time(),
                    "last_error": None,
                    "current_month": month_name,
                    "users": users
                })
            
            socketio.emit('data_update', {
                'leads_by_stage': leads_by_stage,
                'total_leads': total_leads,
                'timestamp': datetime.now().strftime("%H:%M:%S"),
                'current_month': month_name
            })
            
            app.logger.info(
                f"Cache updated successfully. "
                f"Total leads: {total_leads}. "
                f"Time: {time.time() - start_time:.2f}s"
            )
            
        except Exception as e:
            log_error("Critical error in cache update", e)
            time.sleep(60)
        
        time.sleep(app.config['DATA_UPDATE_INTERVAL'])

# Маршруты
@app.route("/")
def index():
    return redirect("/dashboard")

@app.route("/auth", methods=["GET", "POST"])
def auth():
    if request.method == "POST":
        login = request.form.get("login", "").strip()
        password = request.form.get("password", "").strip()
        user = find_user(login)
        
        if user and user["password"] == password:
            session.clear()
            session.update({
                "login": user["login"],
                "role": user["role"],
                "name": user["name"],
                "last_activity": time.time()
            })
            return redirect("/dashboard")
        return render_template("auth.html", error="Неверный логин или пароль")
    return render_template("auth.html")

@app.route("/dashboard")
@login_required
def dashboard():
    if session.get("role") == "admin":
        return render_template("admin_dashboard.html")
    return render_template("user_dashboard.html")

@app.route("/debug-bitrix")
def debug_bitrix():
    try:
        month_start, month_end, month_name = get_current_month_range()
        
        test_results = {}
        for stage_name in app.config['STAGE_LABELS'].keys():
            leads = fetch_leads(stage_name, month_start, month_end)
            test_results[stage_name] = {
                "count": len(leads),
                "sample": leads[0] if leads else None,
                "operators": defaultdict(int)
            }
            
            for lead in leads:
                if lead.get("ASSIGNED_BY_ID"):
                    operator_id = int(lead["ASSIGNED_BY_ID"])
                    test_results[stage_name]["operators"][operator_id] += 1
        
        return jsonify({
            "bitrix_hook": app.config['BITRIX_HOOK'],
            "month_range": f"{month_start} - {month_end}",
            "users_count": len(app.config['TARGET_USERS']),
            "users_sample": app.config['TARGET_USERS'][list(app.config['TARGET_USERS'].keys())[0]],
            "stages": test_results,
            "cache_status": {
                "last_updated": datetime.fromtimestamp(data_cache["last_updated"]).strftime("%Y-%m-%d %H:%M:%S"),
                "has_data": any(data_cache["leads_by_stage"].values())
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# WebSocket обработчики
@socketio.on('connect')
def handle_connect():
    if session.get("role") == "admin":
        with cache_lock:
            socketio.emit('data_update', {
                'leads_by_stage': data_cache["leads_by_stage"],
                'total_leads': data_cache["total_leads"],
                'timestamp': datetime.fromtimestamp(data_cache["last_updated"]).strftime("%H:%M:%S"),
                'current_month': data_cache["current_month"],
                'error': data_cache["last_error"]
            })

@app.route("/admin/data")
@admin_required
def admin_data():
    period = request.args.get('period', 'month')
    data_type = request.args.get('dataType', 'all')
    
    with cache_lock:
        return jsonify({
            "leads_by_stage": data_cache["leads_by_stage"],
            "total_leads": data_cache["total_leads"],
            "last_updated": datetime.fromtimestamp(data_cache["last_updated"]).strftime("%H:%M:%S"),
            "current_month": data_cache["current_month"],
            "error": data_cache["last_error"]
        })

# Запуск фонового потока
Thread(target=update_cache, daemon=True).start()

if __name__ == "__main__":
    app.logger.info("Starting application...")
    socketio.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        log_output=True
    )
