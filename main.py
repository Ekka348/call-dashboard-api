from flask import Flask, request, redirect, session, jsonify, render_template
from functools import wraps
import requests, os, time, json
from datetime import datetime, timedelta
from collections import Counter
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
    BITRIX_HOOK = os.environ.get("BITRIX_HOOK", "").rstrip('/') + '/'  # Нормализация URL
    SESSION_TIMEOUT = 3600  # 1 час
    USER_CACHE_TIMEOUT = 300  # 5 минут
    MAX_LOGIN_ATTEMPTS = 5
    LOG_FILE = 'app.log'
    DATA_UPDATE_INTERVAL = 15  # секунд
    BITRIX_TIMEOUT = 10  # таймаут запросов к Bitrix

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

# Константы
STAGE_LABELS = {
    "Перезвонить": "IN_PROCESS",
    "На согласовании": "UC_A2DF81", 
    "Приглашен к рекрутеру": "CONVERTED"
}

# Глобальный кэш данных
data_cache = {
    "leads_by_stage": {},
    "operators_stats": {},
    "total_leads": 0,
    "last_updated": 0,
    "last_error": None
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
    return (
        first_day.strftime("%Y-%m-%d %H:%M:%S"),
        last_day.strftime("%Y-%m-%d 23:59:59")
    )

# Функции работы с Bitrix API
def fetch_leads(stage):
    try:
        month_start, month_end = get_current_month_range()
        current_time = datetime.now(timezone("Europe/Moscow")).strftime("%Y-%m-%d %H:%M:%S")
        
        params = {
            "filter": {
                "STATUS_ID": stage,
                "!CLOSED": "Y",
                ">=DATE_MODIFY": month_start,
                "<=DATE_MODIFY": current_time
            },
            "select": ["ID", "ASSIGNED_BY_ID", "STATUS_ID", "DATE_MODIFY"],
            "start": 0
        }
        
        app.logger.info(f"Fetching leads for stage {stage} with params: {params}")
        
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
        
        app.logger.info(f"Fetched {len(data.get('result', []))} leads for stage {stage}")
        return data.get("result", []), data.get("next", 0)
        
    except requests.exceptions.RequestException as e:
        log_error(f"Request error fetching leads (stage: {stage})", e)
        return [], 0
    except Exception as e:
        log_error(f"Error fetching leads (stage: {stage})", e)
        return [], 0

def load_users():
    users = {}
    try:
        start = 0
        while True:
            response = requests.post(
                f"{app.config['BITRIX_HOOK']}user.get.json",
                json={"start": start},
                timeout=app.config['BITRIX_TIMEOUT']
            )
            response.raise_for_status()
            data = response.json()
            
            if "error" in data:
                error_msg = data.get("error_description", "Unknown Bitrix API error")
                raise Exception(f"Bitrix API: {error_msg}")
            
            for user in data.get("result", []):
                users[int(user["ID"])] = {
                    "name": f"{user['NAME']} {user['LAST_NAME']}",
                    "email": user.get("EMAIL", "")
                }
            
            if "next" not in data or not data["next"]:
                break
                
            start = data["next"]
        
        app.logger.info(f"Loaded {len(users)} users from Bitrix")
        return users
        
    except requests.exceptions.RequestException as e:
        log_error("Request error loading users", e)
        return {}
    except Exception as e:
        log_error("Error loading users", e)
        return {}

# Фоновое обновление данных
def update_cache():
    while True:
        try:
            app.logger.info("Starting cache update...")
            start_time = time.time()
            
            users = load_users()
            leads_by_stage = {}
            total_leads = 0
            
            # Получаем данные по каждому этапу
            for stage_name, stage_id in STAGE_LABELS.items():
                leads = []
                offset = 0
                
                while True:
                    batch, offset = fetch_leads(stage_id)
                    leads.extend(batch)
                    if not offset:
                        break
                
                # Считаем лиды по операторам
                stats = Counter()
                for lead in leads:
                    if lead.get("ASSIGNED_BY_ID"):
                        stats[int(lead["ASSIGNED_BY_ID"])] += 1
                
                # Формируем детализацию
                details = []
                for uid, cnt in stats.most_common():
                    user = users.get(uid, {})
                    details.append({
                        "operator": user.get("name", f"ID {uid}"),
                        "email": user.get("email", ""),
                        "count": cnt,
                        "user_id": uid
                    })
                
                leads_by_stage[stage_name] = details
                total_leads += sum(stats.values())
            
            # Формируем статистику по операторам
            operators_stats = {}
            for uid, user in users.items():
                ops_stats = {
                    "new": 0,
                    "process": 0, 
                    "success": 0,
                    "total": 0,
                    "email": user.get("email", "")
                }
                
                for stage, leads in leads_by_stage.items():
                    for item in leads:
                        if item["user_id"] == uid:
                            ops_stats["total"] += item["count"]
                            if stage == "Перезвонить":
                                ops_stats["new"] += item["count"]
                            elif stage == "На согласовании":
                                ops_stats["process"] += item["count"]
                            else:
                                ops_stats["success"] += item["count"]
                
                if ops_stats["total"] > 0:
                    operators_stats[user["name"]] = ops_stats
            
            # Обновляем кэш
            with cache_lock:
                data_cache.update({
                    "leads_by_stage": leads_by_stage,
                    "operators_stats": operators_stats,
                    "total_leads": total_leads,
                    "last_updated": time.time(),
                    "last_error": None
                })
            
            # Отправляем обновление через WebSocket
            socketio.emit('data_update', {
                'leads_by_stage': leads_by_stage,
                'operators_stats': operators_stats,
                'total_leads': total_leads,
                'timestamp': datetime.now().strftime("%H:%M:%S")
            })
            
            app.logger.info(
                f"Cache updated successfully. "
                f"Total leads: {total_leads}. "
                f"Time: {time.time() - start_time:.2f}s"
            )
            
        except Exception as e:
            log_error("Critical error in cache update", e)
            time.sleep(60)  # Пауза при критической ошибке
        
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

@app.route("/admin/data")
@admin_required
def admin_data():
    with cache_lock:
        return jsonify({
            "leads_by_stage": data_cache["leads_by_stage"],
            "operators_stats": data_cache["operators_stats"],
            "total_leads": data_cache["total_leads"],
            "last_updated": datetime.fromtimestamp(data_cache["last_updated"]).strftime("%H:%M:%S"),
            "error": data_cache["last_error"]
        })

@app.route("/test-api")
def test_api():
    """Тестовый маршрут для проверки подключения к Bitrix"""
    try:
        users = load_users()
        test_leads, _ = fetch_leads("IN_PROCESS")
        
        return jsonify({
            "status": "success",
            "bitrix_hook": app.config['BITRIX_HOOK'],
            "users_count": len(users),
            "sample_user": next(iter(users.values())) if users else None,
            "leads_count": len(test_leads),
            "sample_lead": test_leads[0] if test_leads else None,
            "cache_status": {
                "last_updated": datetime.fromtimestamp(data_cache["last_updated"]).strftime("%Y-%m-%d %H:%M:%S"),
                "has_data": any(data_cache["leads_by_stage"].values())
            }
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e),
            "bitrix_hook": app.config['BITRIX_HOOK']
        }), 500

# WebSocket обработчики
@socketio.on('connect')
def handle_connect():
    if session.get("role") == "admin":
        with cache_lock:
            socketio.emit('data_update', {
                'leads_by_stage': data_cache["leads_by_stage"],
                'operators_stats': data_cache["operators_stats"],
                'total_leads': data_cache["total_leads"],
                'timestamp': datetime.fromtimestamp(data_cache["last_updated"]).strftime("%H:%M:%S"),
                'error': data_cache["last_error"]
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
