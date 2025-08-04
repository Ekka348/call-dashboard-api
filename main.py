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
    TARGET_DEPARTMENT = "Проект ВВ"  # Название целевого подразделения

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
user_cache = {
    "data": {},
    "departments": {},
    "active_users": set(),
    "last": 0
}

def get_user_department(user_id):
    """Получаем информацию о подразделении пользователя"""
    if user_id in user_cache["departments"]:
        return user_cache["departments"][user_id]
    
    try:
        response = requests.post(
            app.config['BITRIX_HOOK'] + "user.get.json",
            json={"ID": user_id},
            timeout=5
        ).json()
        
        if "error" in response:
            return ""
            
        user_data = response.get("result", {})
        department_name = ""
        
        # Получаем название подразделения через department.get
        if "UF_DEPARTMENT" in user_data:
            dept_id = user_data["UF_DEPARTMENT"][0] if user_data["UF_DEPARTMENT"] else 0
            if dept_id:
                dept_response = requests.post(
                    app.config['BITRIX_HOOK'] + "department.get.json",
                    json={"ID": dept_id},
                    timeout=5
                ).json()
                if "result" in dept_response:
                    department_name = dept_response["result"].get("NAME", "")
        
        user_cache["departments"][user_id] = department_name
        return department_name
        
    except Exception as e:
        log_error(f"Ошибка получения подразделения пользователя {user_id}", e)
        return ""

def load_users():
    if time.time() - user_cache["last"] < app.config['USER_CACHE_TIMEOUT']:
        return user_cache["data"]
    
    users = {}
    user_cache["active_users"] = set()
    user_cache["departments"] = {}
    
    try:
        start = 0
        while True:
            response = requests.post(
                app.config['BITRIX_HOOK'] + "user.get.json",
                json={"start": start},
                timeout=10
            ).json()
            
            if "error" in response:
                raise Exception(response.get("error_description", "Bitrix API error"))
                
            for user in response.get("result", []):
                user_id = int(user["ID"])
                full_name = f'{user["NAME"]} {user["LAST_NAME"]}'
                users[user_id] = full_name
                
                # Проверяем активность пользователя
                if user.get("ACTIVE", "Y") == "Y":
                    user_cache["active_users"].add(user_id)
                    
            if "next" not in response:
                break
            start = response.get("next")
            
    except Exception as e:
        log_error("Ошибка загрузки пользователей", e)
        return user_cache["data"]
        
    user_cache["data"] = users
    user_cache["last"] = time.time()
    return users

# Работа с лидами
def fetch_leads(stage, start, end, offset=0):
    try:
        response = requests.post(
            app.config['BITRIX_HOOK'] + "crm.lead.list.json",
            json={
                "filter": {">=DATE_MODIFY": start, "<=DATE_MODIFY": end, "STATUS_ID": stage},
                "select": ["ID", "ASSIGNED_BY_ID"],
                "start": offset
            },
            timeout=10
        ).json()
        
        if "error" in response:
            raise Exception(response.get("error_description", "Bitrix API error"))
            
        return response.get("result", []), response.get("next", 0)
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

def process_stage(name, stage_id, start, end, users, operator_filter=None):
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
            if not uid or int(uid) not in user_cache["active_users"]:
                continue
                
            if operator_filter and str(uid) not in operator_filter:
                continue
                
            # Проверяем принадлежность к целевому подразделению
            department = get_user_department(int(uid))
            if department != app.config['TARGET_DEPARTMENT']:
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

        operator_ids = request.args.get("operators")
        operator_filter = set(operator_ids.split(",")) if operator_ids else None

        name, stage_data = process_stage(stage_name, stage_id, start, end, users, operator_filter)

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

    operator_ids = request.args.get("operators")
    operator_filter = set(operator_ids.split(",")) if operator_ids else None

    data = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(process_stage, name, stage_id, start, end, users, operator_filter)
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

@app.route("/api/operators")
@login_required
@admin_required
def api_operators():
    users = load_users()
    target_department = app.config['TARGET_DEPARTMENT']
    
    operators = []
    for uid, name in users.items():
        # Проверяем активность и подразделение
        if uid in user_cache["active_users"]:
            department = get_user_department(uid)
            if department == target_department:
                operators.append({
                    "id": str(uid),
                    "name": name,
                    "department": department
                })
    
    return jsonify(operators)

@app.route("/ping")
def ping():
    return jsonify({"status": "ok"})

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/auth")

@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def server_error(e):
    log_error("Server error", e)
    return render_template("500.html"), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
