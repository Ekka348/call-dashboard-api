from flask import Flask, request, redirect, session, jsonify, render_template
from functools import wraps
import requests, os, time, json
from datetime import datetime, timedelta
from collections import Counter
from pytz import timezone
from concurrent.futures import ThreadPoolExecutor
import logging
from logging.handlers import RotatingFileHandler

app = Flask(__name__)

# Конфигурация
class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or os.urandom(24)
    BITRIX_HOOK = os.environ.get("BITRIX_HOOK", "https://ers2023.bitrix24.ru/rest/27/1bc1djrnc455xeth/")
    SESSION_TIMEOUT = 3600  # 1 час
    USER_CACHE_TIMEOUT = 300  # 5 минут
    MAX_LOGIN_ATTEMPTS = 5
    LOG_FILE = 'app.log'

app.config.from_object(Config)
app.secret_key = app.config['SECRET_KEY']

# Настройка логирования
handler = RotatingFileHandler(app.config['LOG_FILE'], maxBytes=10000, backupCount=1)
handler.setLevel(logging.INFO)
app.logger.addHandler(handler)

# Глобальные переменные
GROUPED_STAGES = []
STAGE_LABELS = {
    "На согласовании": "UC_A2DF81",
    "Перезвонить": "IN_PROCESS",
    "Приглашен к рекрутеру": "CONVERTED",
}

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
    app.logger.error(f"{message}: {str(exc) if exc else 'No details'}")

def find_user(login):
    try:
        with open("whitelist.json", "r", encoding="utf-8") as f:
            users = json.load(f)
        return next((u for u in users if u["login"] == login), None)
    except Exception as e:
        log_error("Ошибка загрузки whitelist.json", e)
        return None

def get_range_dates(rtype):
    tz = timezone("Europe/Moscow")
    now = datetime.now(tz)

    try:
        if rtype == "week":
            start = now - timedelta(days=now.weekday())
            end = now
        elif rtype == "month":
            start = now.replace(day=1)
            end = now
        elif rtype.startswith("custom:"):
            _, start_raw, end_raw = rtype.split(":")
            start = datetime.strptime(start_raw, "%Y-%m-%d")
            end = datetime.strptime(end_raw, "%Y-%m-%d") + timedelta(days=1)
        else:  # today
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now

        return start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        log_error("Ошибка определения диапазона дат", e)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now
        return start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")

# Кэширование пользователей
user_cache = {"data": {}, "last": 0}

def load_users():
    if time.time() - user_cache["last"] < app.config['USER_CACHE_TIMEOUT']:
        return user_cache["data"]
    
    users, start = {}, 0
    try:
        while True:
            r = requests.post(
                app.config['BITRIX_HOOK'] + "user.get.json",
                json={"start": start},
                timeout=10
            ).json()
            
            if "error" in r:
                raise Exception(r.get("error_description", "Bitrix API error"))
                
            for u in r.get("result", []):
                users[int(u["ID"])] = f'{u["NAME"]} {u["LAST_NAME"]}'
                
            if "next" not in r:
                break
            start = r.get("next")
            
    except Exception as e:
        log_error("Ошибка загрузки пользователей", e)
        return user_cache["data"]  # Возвращаем старые данные при ошибке
        
    user_cache["data"], user_cache["last"] = users, time.time()
    return users

# Работа с лидами
def fetch_leads(stage, start, end, offset=0):
    try:
        r = requests.post(
            app.config['BITRIX_HOOK'] + "crm.lead.list.json",
            json={
                "filter": {">=DATE_MODIFY": start, "<=DATE_MODIFY": end, "STATUS_ID": stage},
                "select": ["ID", "ASSIGNED_BY_ID"],
                "start": offset
            },
            timeout=10
        ).json()
        
        if "error" in r:
            raise Exception(r.get("error_description", "Bitrix API error"))
            
        return r.get("result", []), r.get("next", 0)
    except Exception as e:
        log_error(f"Ошибка загрузки лидов (stage: {stage})", e)
        return [], 0

def fetch_all_leads(stage):
    leads, offset = [], 0
    try:
        while True:
            page, offset = fetch_leads(stage, "", "", offset)
            if not page:
                break
            leads.extend(page)
            if not offset:
                break
    except Exception as e:
        log_error(f"Ошибка загрузки всех лидов (stage: {stage})", e)
    return leads

# Кэширование групповых стадий
group_cache = {"data": {}, "last": 0}

def cached_group_count(name, stage_id):
    now = time.time()
    if name in group_cache["data"] and now - group_cache["last"] < 60:
        return group_cache["data"][name]
        
    count = len(fetch_all_leads(stage_id))
    group_cache["data"][name] = count
    group_cache["last"] = now
    return count

def process_stage(name, stage_id, start, end, users):
    try:
        if name in GROUPED_STAGES:
            return name, {"grouped": True, "count": cached_group_count(name, stage_id)}

        leads = []
        offset = 0
        while True:
            page, offset = fetch_leads(stage_id, start, end, offset)
            leads.extend(page)
            if not offset:
                break

        stats = Counter()
        for lead in leads:
            uid = lead.get("ASSIGNED_BY_ID")
            if not uid:
                continue
                
            try:
                stats[int(uid)] += 1
            except Exception as e:
                log_error(f"Ошибка при подсчёте UID {uid}", e)

        details = [
            {"operator": users.get(uid, f"ID {uid}"), "count": cnt}
            for uid, cnt in sorted(stats.items(), key=lambda x: -x[1])
        ]
        
        return name, {"grouped": False, "details": details}
    except Exception as e:
        log_error(f"Ошибка при обработке стадии '{name}'", e)
        return name, {"grouped": False, "details": []}

# Маршруты
@app.route("/auth", methods=["GET", "POST"])
def auth():
    if request.method == "POST":
        login = request.form.get("login", "").strip()
        password = request.form.get("password", "").strip()
        
        if not login or not password:
            return render_template("auth.html", error="Заполните все поля")
            
        if session.get('login_attempts', 0) >= app.config['MAX_LOGIN_ATTEMPTS']:
            return render_template("auth.html", error="Слишком много попыток. Попробуйте позже.")
            
        user = find_user(login)
        if user and user["password"] == password:
            session.clear()
            session["login"] = user["login"]
            session["role"] = user["role"]
            session["name"] = user["name"]
            session['last_activity'] = time.time()
            return redirect("/dashboard")
            
        session['login_attempts'] = session.get('login_attempts', 0) + 1
        return render_template("auth.html", error="Неверный логин или пароль")
        
    return render_template("auth.html")

@app.route("/")
def index():
    return redirect("/auth")

@app.route("/dashboard")
@login_required
def dashboard():
    return app.send_static_file("dashboard.html")

@app.route("/update_stage/<stage_name>")
@login_required
def update_stage(stage_name):
    if stage_name not in STAGE_LABELS:
        return jsonify({"error": "Стадия не найдена"}), 404

    try:
        rtype = request.args.get("range", "today")
        start, end = get_range_dates(rtype)
        users = load_users()
        stage_id = STAGE_LABELS[stage_name]

        name, stage_data = process_stage(stage_name, stage_id, start, end, users)

        if session.get("role") == "operator":
            operator_name = session.get("name")
            stage_data["details"] = [
                d for d in stage_data.get("details", [])
                if d.get("operator") == operator_name
            ]

        return jsonify({name: stage_data})
    except Exception as e:
        log_error("Ошибка в update_stage", e)
        return jsonify({"error": "Internal server error"}), 500

@app.route("/personal_stats")
@login_required
def personal_stats():
    operator_name = session.get("name")
    if not operator_name:
        return jsonify({"error": "Оператор не найден"}), 403

    start, end = get_range_dates("today")
    users = load_users()
    stats = {}

    for name, stage_id in STAGE_LABELS.items():
        leads = []
        offset = 0
        while True:
            page, offset = fetch_leads(stage_id, start, end, offset)
            leads.extend(page)
            if not offset:
                break

        count = sum(1 for lead in leads if users.get(lead.get("ASSIGNED_BY_ID")) == operator_name)
        stats[name] = count

    return jsonify({"operator": operator_name, "stats": stats})

@app.route("/api/leads/by-stage")
@login_required
def leads_by_stage():
    start, end = get_range_dates("today")
    users = load_users()

    data = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(process_stage, name, stage_id, start, end, users)
            for name, stage_id in STAGE_LABELS.items()
        ]
        for future in futures:
            name, stage_data = future.result()
            data[name] = stage_data

    return jsonify({"range": "today", "data": data})

@app.route("/api/userinfo")
@login_required
def api_userinfo():
    return jsonify({
        "name": session.get("name"),
        "role": session.get("role")
    })

@app.route("/ping")
def ping():
    return jsonify({"status": "ok"})

@app.route("/clock")
def clock():
    tz = timezone("Europe/Moscow")
    moscow_now = datetime.now(tz)
    utc_now = datetime.utcnow()
    return jsonify({
        "moscow": moscow_now.strftime("%Y-%m-%d %H:%M:%S"),
        "utc": utc_now.strftime("%Y-%m-%d %H:%M:%S")
    })

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def server_error(e):
    log_error("Server error", e)
    return render_template("500.html"), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
