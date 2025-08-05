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
import socketio as client_sio

monkey.patch_all()

app = Flask(__name__)
socketio = SocketIO(app, 
                   async_mode='gevent',
                   cors_allowed_origins="*",
                   engineio_logger=True,
                   logger=True)

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", os.urandom(24))
    BITRIX_HOOK = os.environ.get("BITRIX_HOOK_URL", "https://ers2023.bitrix24.ru/rest/27/1bc1djrnc455xeth/")
    SESSION_TIMEOUT = 3600
    USER_CACHE_TIMEOUT = 300
    MAX_LOGIN_ATTEMPTS = 5
    LOG_FILE = 'app.log'
    DATA_UPDATE_INTERVAL = 60
    BITRIX_TIMEOUT = 30
    MAX_LEADS_PER_REQUEST = 50
    
    TARGET_USERS = {
        3037: "Старицын Георгий",
        3025: "Гусева Екатерина",
        # ... (полный список пользователей)
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
    maxBytes=100000,
    backupCount=3,
    encoding='utf-8'
)
handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
handler.setLevel(logging.DEBUG)
app.logger.addHandler(handler)
app.logger.setLevel(logging.DEBUG)

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

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "login" not in session:
            return redirect("/auth")
        if time.time() - session.get('last_activity', 0) > app.config['SESSION_TIMEOUT']:
            session.clear()
            return redirect("/auth?timeout=1")
        session['last_activity'] = time.time()
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("role") != "admin":
            return jsonify({"error": "Forbidden"}), 403
        return f(*args, **kwargs)
    return decorated_function

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

def get_date_range(period='month'):
    tz = timezone("Europe/Moscow")
    now = datetime.now(tz)
    
    if period == 'day':
        date_from = now.replace(hour=0, minute=0, second=0, microsecond=0)
        date_to = now.replace(hour=23, minute=59, second=59, microsecond=999)
        period_name = date_from.strftime("%d.%m.%Y")
    elif period == 'week':
        date_from = now - timedelta(days=now.weekday())
        date_from = date_from.replace(hour=0, minute=0, second=0, microsecond=0)
        date_to = date_from + timedelta(days=6)
        date_to = date_to.replace(hour=23, minute=59, second=59, microsecond=999)
        period_name = f"{date_from.strftime('%d.%m')}-{date_to.strftime('%d.%m.%Y')}"
    else:
        date_from = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_day = (now.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        date_to = last_day.replace(hour=23, minute=59, second=59, microsecond=999)
        period_name = date_from.strftime("%B %Y")
    
    return (
        date_from.strftime("%Y-%m-%d %H:%M:%S"),
        date_to.strftime("%Y-%m-%d %H:%M:%S"),
        period_name
    )

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
            "start": -1
        }
        
        response = requests.post(
            f"{app.config['BITRIX_HOOK']}crm.timeline.list.json",
            json=params,
            timeout=app.config['BITRIX_TIMEOUT']
        )
        response.raise_for_status()
        data = response.json()
        
        if "error" in data:
            raise Exception(data.get("error_description", "Unknown Bitrix API error"))
        
        return [
            {"STATUS_ID": item["TO_VALUE"], "DATE": item["DATE_CREATE"]}
            for item in data.get("result", [])
            if item.get("FIELD") == "STATUS_ID"
        ], time.time()
    except requests.exceptions.RequestException as e:
        log_error(f"Request error getting history for lead {lead_id}", e)
        return [], time.time()
    except Exception as e:
        log_error(f"Error getting history for lead {lead_id}", e)
        return [], time.time()

def fetch_leads_batch(params):
    try:
        response = requests.post(
            f"{app.config['BITRIX_HOOK']}crm.lead.list.json",
            json=params,
            timeout=app.config['BITRIX_TIMEOUT']
        )
        response.raise_for_status()
        data = response.json()
        
        if "error" in data:
            raise Exception(data.get("error_description", "Unknown Bitrix API error"))
        
        return data.get("result", []), data.get("next", 0)
    except Exception as e:
        log_error("Error fetching leads batch", e)
        return [], 0

def fetch_leads(stage_name, date_from, date_to):
    try:
        stage_config = app.config['STAGE_LABELS'][stage_name]
        all_leads = []
        start = 0
        
        while True:
            params = {
                "filter": {
                    "ASSIGNED_BY_ID": list(app.config['TARGET_USERS'].keys()),
                    ">=DATE_MODIFY": date_from,
                    "<=DATE_MODIFY": date_to
                },
                "select": ["ID", "ASSIGNED_BY_ID", "STATUS_ID", "DATE_MODIFY", "STATUS_SEMANTIC_ID"],
                "start": start
            }
            
            if stage_name == "Перезвонить":
                params["filter"]["STATUS_ID"] = stage_config["id"]
                params["filter"]["STATUS_SEMANTIC_ID"] = stage_config["semantic"]
            else:
                params["filter"]["STATUS_ID"] = stage_config["id"]
            
            leads, next_start = fetch_leads_batch(params)
            all_leads.extend(leads)
            
            if not leads or next_start == 0:
                break
                
            start = next_start
        
        if stage_name == "Перезвонить":
            valid_leads = []
            for lead in all_leads:
                try:
                    lead_date = datetime.strptime(lead["DATE_MODIFY"], "%Y-%m-%dT%H:%M:%S%z")
                    filter_from = datetime.strptime(date_from, "%Y-%m-%d %H:%M:%S").replace(tzinfo=lead_date.tzinfo)
                    filter_to = datetime.strptime(date_to, "%Y-%m-%d %H:%M:%S").replace(tzinfo=lead_date.tzinfo)
                    
                    if filter_from <= lead_date <= filter_to:
                        valid_leads.append(lead)
                except Exception as e:
                    log_error(f"Error processing lead date {lead['ID']}", e)
                    continue
            
            app.logger.debug(f"Found {len(valid_leads)} valid leads for 'Перезвонить'")
            return valid_leads
        
        app.logger.debug(f"Found {len(all_leads)} leads for stage {stage_name}")
        return all_leads
        
    except Exception as e:
        log_error(f"Error fetching leads for {stage_name}", e)
        return []

def load_users():
    try:
        return {
            user_id: {
                "name": user_name,
                "email": f"{user_name.split()[0].lower()}.{user_name.split()[1].lower()}@example.com"
            }
            for user_id, user_name in app.config['TARGET_USERS'].items()
        }
    except Exception as e:
        log_error("Error loading users", e)
        return {}

def update_cache():
    while True:
        try:
            date_from, date_to, period_name = get_date_range()
            users = load_users()
            leads_by_stage = {}
            total_leads = 0
            
            # Получаем данные для всех стадий
            for stage_name in app.config['STAGE_LABELS'].keys():
                leads = fetch_leads(stage_name, date_from, date_to)
                operator_stats = defaultdict(int)
                
                for lead in leads:
                    operator_id = int(lead["ASSIGNED_BY_ID"])
                    operator_stats[operator_id] += 1
                
                # Создаем записи для всех операторов
                stage_data = []
                for user_id, user_name in app.config['TARGET_USERS'].items():
                    stage_data.append({
                        "operator": user_name,
                        "count": operator_stats.get(user_id, 0),
                        "user_id": user_id,
                        "email": users.get(user_id, {}).get("email", "")
                    })
                
                stage_data.sort(key=lambda x: (-x["count"], x["operator"]))
                leads_by_stage[stage_name] = stage_data
                total_leads += sum(operator_stats.values())
            
            with cache_lock:
                data_cache.update({
                    "leads_by_stage": leads_by_stage,
                    "total_leads": total_leads,
                    "last_updated": time.time(),
                    "current_month": period_name,
                    "users": users
                })
            
            socketio.emit('data_update', {
                'leads_by_stage': leads_by_stage,
                'total_leads': total_leads,
                'timestamp': datetime.now().strftime("%H:%M:%S"),
                'current_month': period_name
            })
            
            time.sleep(app.config['DATA_UPDATE_INTERVAL'])
            
        except Exception as e:
            log_error("Error in cache update", e)
            time.sleep(120)

@app.route("/")
def index():
    return redirect("/dashboard")

@app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200

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

@app.route("/admin/data")
@admin_required
def admin_data():
    period = request.args.get('period', 'month')
    data_type = request.args.get('dataType', 'all')
    
    date_from, date_to, period_name = get_date_range(period)
    
    with cache_lock:
        filtered_data = {
            "leads_by_stage": {},
            "total_leads": 0,
            "last_updated": data_cache["last_updated"],
            "current_month": period_name
        }
        
        for stage, items in data_cache["leads_by_stage"].items():
            filtered_items = []
            for item in items:
                if data_type == 'all' or item['count'] > 0:
                    filtered_items.append(item)
            
            filtered_data["leads_by_stage"][stage] = filtered_items
            filtered_data["total_leads"] += sum(item['count'] for item in filtered_items)
        
        return jsonify(filtered_data)

@app.route("/ping")
def ping():
    return jsonify({"status": "ok", "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})

@socketio.on('connect')
def handle_connect():
    app.logger.info('Client connected')
    with cache_lock:
        socketio.emit('data_update', {
            'leads_by_stage': data_cache["leads_by_stage"],
            'total_leads': data_cache["total_leads"],
            'timestamp': datetime.fromtimestamp(data_cache["last_updated"]).strftime("%H:%M:%S"),
            'current_month': data_cache["current_month"]
        })

@socketio.on('disconnect')
def handle_disconnect():
    app.logger.info('Client disconnected')

if __name__ == "__main__":
    app.logger.info("Starting application")
    Thread(target=update_cache, daemon=True).start()
    socketio.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        log_output=True,
        allow_unsafe_werkzeug=True,
        ping_timeout=60,
        ping_interval=25
    )
