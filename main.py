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

app = Flask(__name__)
socketio = SocketIO(app, async_mode='gevent')

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", os.urandom(24))
    BITRIX_HOOK = os.environ.get("BITRIX_HOOK")
    SESSION_TIMEOUT = 3600
    USER_CACHE_TIMEOUT = 300
    MAX_LOGIN_ATTEMPTS = 5
    LOG_FILE = 'app.log'
    DATA_UPDATE_INTERVAL = 15

app.config.from_object(Config)
app.secret_key = app.config['SECRET_KEY']

handler = RotatingFileHandler(app.config['LOG_FILE'], maxBytes=10000, backupCount=1)
handler.setLevel(logging.INFO)
app.logger.addHandler(handler)

STAGE_LABELS = {
    "Перезвонить": "IN_PROCESS",
    "На согласовании": "UC_A2DF81",
    "Приглашен к рекрутеру": "CONVERTED"
}

data_cache = {
    "leads_by_stage": {},
    "operators_stats": {},
    "total_leads": 0,
    "last_updated": 0
}
cache_lock = Lock()

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

def log_error(message, exc=None):
    app.logger.error(f"{message}: {str(exc) if exc else 'No details'}")

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

def fetch_leads(stage):
    try:
        month_start, month_end = get_current_month_range()
        current_time = datetime.now(timezone("Europe/Moscow")).strftime("%Y-%m-%d %H:%M:%S")
        
        response = requests.post(
            f"{app.config['BITRIX_HOOK']}crm.lead.list.json",
            json={
                "filter": {
                    "STATUS_ID": stage,
                    "!CLOSED": "Y",
                    ">=DATE_MODIFY": month_start,
                    "<=DATE_MODIFY": current_time
                },
                "select": ["ID", "ASSIGNED_BY_ID"],
                "start": 0
            },
            timeout=10
        )
        data = response.json()
        if "error" in data:
            raise Exception(data.get("error_description", "Bitrix API error"))
        return data.get("result", []), data.get("next", 0)
    except Exception as e:
        log_error(f"Ошибка загрузки лидов (stage: {stage})", e)
        return [], 0

def load_users():
    users = {}
    try:
        start = 0
        while True:
            response = requests.post(
                f"{app.config['BITRIX_HOOK']}user.get.json",
                json={"start": start},
                timeout=10
            )
            data = response.json()
            if "error" in data:
                raise Exception(data.get("error_description", "Bitrix API error"))
            for user in data.get("result", []):
                users[int(user["ID"])] = f"{user['NAME']} {user['LAST_NAME']}"
            if "next" not in data:
                break
            start = data.get("next")
    except Exception as e:
        log_error("Ошибка загрузки пользователей", e)
    return users

def update_cache():
    while True:
        try:
            users = load_users()
            leads_by_stage = {}
            total_leads = 0
            
            for stage_name, stage_id in STAGE_LABELS.items():
                leads = []
                offset = 0
                while True:
                    batch, offset = fetch_leads(stage_id)
                    leads.extend(batch)
                    if not offset:
                        break
                
                stats = Counter()
                for lead in leads:
                    if lead.get("ASSIGNED_BY_ID"):
                        stats[int(lead["ASSIGNED_BY_ID"])] += 1
                
                details = [
                    {"operator": users.get(uid, f"ID {uid}"), "count": cnt}
                    for uid, cnt in stats.most_common()
                ]
                
                leads_by_stage[stage_name] = details
                total_leads += sum(stats.values())
            
            operators_stats = {}
            for uid, name in users.items():
                ops_stats = {"new": 0, "process": 0, "success": 0, "total": 0}
                for stage, leads in leads_by_stage.items():
                    for item in leads:
                        if item["operator"] == name:
                            ops_stats["total"] += item["count"]
                            if stage == "Перезвонить":
                                ops_stats["new"] += item["count"]
                            elif stage == "На согласовании":
                                ops_stats["process"] += item["count"]
                            else:
                                ops_stats["success"] += item["count"]
                if ops_stats["total"] > 0:
                    operators_stats[name] = ops_stats
            
            with cache_lock:
                data_cache.update({
                    "leads_by_stage": leads_by_stage,
                    "operators_stats": operators_stats,
                    "total_leads": total_leads,
                    "last_updated": time.time()
                })
            
            socketio.emit('data_update', {
                'leads_by_stage': leads_by_stage,
                'operators_stats': operators_stats,
                'total_leads': total_leads,
                'timestamp': datetime.now().strftime("%H:%M:%S")
            })
            
        except Exception as e:
            log_error("Ошибка при обновлении кэша", e)
        
        time.sleep(app.config['DATA_UPDATE_INTERVAL'])

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
            **data_cache,
            "timestamp": datetime.fromtimestamp(data_cache["last_updated"]).strftime("%H:%M:%S")
        })

@socketio.on('connect')
def handle_connect():
    if session.get("role") == "admin":
        with cache_lock:
            socketio.emit('data_update', {
                'leads_by_stage': data_cache["leads_by_stage"],
                'operators_stats': data_cache["operators_stats"],
                'total_leads': data_cache["total_leads"],
                'timestamp': datetime.fromtimestamp(data_cache["last_updated"]).strftime("%H:%M:%S")
            })
    else:
        return False

Thread(target=update_cache, daemon=True).start()

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
