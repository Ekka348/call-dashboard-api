from flask import Flask, request, redirect, session, jsonify, render_template
from functools import wraps
import requests, os, time, json
from datetime import datetime, timedelta
from collections import Counter
from pytz import timezone
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev_key")

HOOK = "https://ers2023.bitrix24.ru/rest/27/1bc1djrnc455xeth/"
GROUPED_STAGES = []

# 🔐 Авторизация
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "login" not in session:
            return redirect("/auth")
        return f(*args, **kwargs)
    return wrapper

@app.route("/auth", methods=["GET", "POST"])
def auth():
    if request.method == "POST":
        login = request.form["login"]
        password = request.form["password"]
        user = find_user(login)
        if user and user["password"] == password:
            session["login"] = user["login"]
            session["role"] = user["role"]
            session["name"] = user["name"]
            return redirect("/dashboard")
        return render_template("auth.html", error="Неверный логин или пароль")
    return render_template("auth.html")

@app.route("/")
def index():
    return redirect("/auth")

@app.route("/dashboard")
@login_required
def dashboard():
    return app.send_static_file("dashboard.html")

def find_user(login):
    with open("whitelist.json", "r", encoding="utf-8") as f:
        users = json.load(f)
    return next((u for u in users if u["login"] == login), None)

def get_range_dates(rtype):
    tz = timezone("Europe/Moscow")
    now = datetime.now(tz)

    if rtype == "week":
        start = now - timedelta(days=now.weekday())
        end = now
    elif rtype == "month":
        start = now.replace(day=1)
        end = now
    elif rtype.startswith("custom:"):
        try:
            _, start_raw, end_raw = rtype.split(":")
            start = datetime.strptime(start_raw, "%Y-%m-%d")
            end = datetime.strptime(end_raw, "%Y-%m-%d") + timedelta(days=1)
        except Exception as e:
            print("Ошибка парсинга custom-периода:", e)
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now
    else:  # today
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now

    return start.strftime("%Y-%m-%d %H:%M:%S"), end.strftime("%Y-%m-%d %H:%M:%S")

user_cache = {"data": {}, "last": 0}
def load_users():
    if time.time() - user_cache["last"] < 300:
        return user_cache["data"]
    users, start = {}, 0
    try:
        while True:
            r = requests.post(HOOK + "user.get.json", json={"start": start}, timeout=10).json()
            for u in r.get("result", []):
                users[int(u["ID"])] = f'{u["NAME"]} {u["LAST_NAME"]}'
            if "next" not in r: break
            start = r.get("next")
    except Exception as e:
        print("Ошибка загрузки пользователей:", e)
    user_cache["data"], user_cache["last"] = users, time.time()
    return users

STAGE_LABELS = {
    "На согласовании": "UC_A2DF81",
    "Перезвонить": "IN_PROCESS",
    "Приглашен к рекрутеру": "CONVERTED",
}

def fetch_leads(stage, start, end):
    leads, offset = [], 0
    try:
        while True:
            r = requests.post(HOOK + "crm.lead.list.json", json={
                "filter": {">=DATE_MODIFY": start, "<=DATE_MODIFY": end, "STATUS_ID": stage},
                "select": ["ID", "ASSIGNED_BY_ID"],
                "start": offset
            }, timeout=10).json()
            page = r.get("result", [])
            if not page: break
            leads.extend(page)
            offset = r.get("next", 0)
            if not offset: break
    except Exception as e:
        print("Ошибка загрузки лидов:", e)
    return leads

def fetch_all_leads(stage):
    leads, offset = [], 0
    try:
        while True:
            r = requests.post(HOOK + "crm.lead.list.json", json={
                "filter": {"STATUS_ID": stage},
                "select": ["ID", "ASSIGNED_BY_ID"],
                "start": offset
            }, timeout=10).json()
            page = r.get("result", [])
            if not page: break
            leads.extend(page)
            offset = r.get("next", 0)
            if not offset: break
    except Exception as e:
        print("Ошибка загрузки всех лидов:", e)
    return leads

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

        leads = fetch_leads(stage_id, start, end)
        stats = Counter()

        for lead in leads:
            uid = lead.get("ASSIGNED_BY_ID")
            if not uid: continue
            # фильтрация по операторам (для админа)
            if operator_filter:
                if str(uid) not in operator_filter:
                    continue
            try:
                stats[int(uid)] += 1
            except Exception as e:
                print("Ошибка при подсчёте UID:", e)

        details = [
            {"operator": users.get(uid, f"ID {uid}"), "count": cnt}
            for uid, cnt in sorted(stats.items(), key=lambda x: -x[1])
        ]
        return name, {"grouped": False, "details": details}
    except Exception as e:
        print(f"Ошибка при обработке стадии '{name}':", e)
        return name, {"grouped": False, "details": []}

@app.route("/update_stage/<stage_name>")
@login_required
def update_stage(stage_name):
    if stage_name not in STAGE_LABELS:
        return "Стадия не найдена", 404

    try:
        rtype = request.args.get("range", "today")  # today/week/month/custom
        start, end = get_range_dates(rtype)

        users = load_users()
        stage_id = STAGE_LABELS[stage_name]

        # Новый: фильтр по операторам для админа
        operator_ids = request.args.get("operators")
        operator_filter = None
        if operator_ids:
            operator_filter = set(operator_ids.split(","))

        name, stage_data = process_stage(stage_name, stage_id, start, end, users, operator_filter)

        if session.get("role") == "operator":
            operator_name = session.get("name")
            stage_data["details"] = [
                d for d in stage_data.get("details", [])
                if d.get("operator") == operator_name
            ]

        return jsonify({name: stage_data})
    except Exception as e:
        print("Ошибка в update_stage:", e)
        return jsonify({"error": str(e)}), 500

@app.route("/personal_stats")
@login_required
def personal_stats():
    operator_name = session.get("name", None)
    if not operator_name:
        return jsonify({"error": "Оператор не найден"}), 403

    start, end = get_range_dates("today")
    users = load_users()
    stats = {}

    for name, stage_id in STAGE_LABELS.items():
        leads = fetch_leads(stage_id, start, end)
        count = 0
        for lead in leads:
            uid = lead.get("ASSIGNED_BY_ID")
            if users.get(uid) == operator_name:
                count += 1
        stats[name] = count

    return jsonify({"operator": operator_name, "stats": stats})

@app.route("/api/leads/by-stage")
@login_required
def leads_by_stage():
    start, end = get_range_dates("today")
    users = load_users()
    data = {}

    # Новый: фильтр по операторам для админа
    operator_ids = request.args.get("operators")
    operator_filter = None
    if operator_ids:
        operator_filter = set(operator_ids.split(","))

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [
            executor.submit(process_stage, name, stage_id, start, end, users, operator_filter)
            for name, stage_id in STAGE_LABELS.items()
        ]
        for future in futures:
            name, stage_data = future.result()
            data[name] = stage_data

    return {"range": "today", "data": data}

@app.route("/api/userinfo")
@login_required
def api_userinfo():
    return jsonify({
        "name": session.get("name"),
        "role": session.get("role")
    })

@app.route("/api/operators")
@login_required
def api_operators():
    users = load_users()
    # Можно фильтровать только операторов, если у вас есть поле role
    # Сейчас возвращает всех
    return jsonify([
        {"id": uid, "name": name}
        for uid, name in users.items()
    ])

@app.route("/ping")
def ping():
    return {"status": "ok"}

@app.route("/clock")
def clock():
    tz = timezone("Europe/Moscow")
    moscow_now = datetime.now(tz)
    utc_now = datetime.utcnow()
    return {
        "moscow": moscow_now.strftime("%Y-%m-%d %H:%M:%S"),
        "utc": utc_now.strftime("%Y-%m-%d %H:%M:%S")
    }

# 🚀 Старт
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
