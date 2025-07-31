from flask import Flask, request, render_template_string
import requests, os, time
from datetime import datetime, timedelta
from collections import Counter
from pytz import timezone  # 🕒 для московского времени
from flask import session, redirect

app = Flask(__name__)
HOOK = "https://ers2023.bitrix24.ru/rest/27/1bc1djrnc455xeth/"

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "login" not in session:
            return redirect("/auth")
        return f(*args, **kwargs)
    return wrapper

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")
import json

def load_users():
    with open("whitelist.json", "r") as f:
        return json.load(f)

def find_user(login):
    users = load_users()
    for user in users:
        if user["login"] == login:
            return user
    return None


@app.route("/", methods=["POST"])
def login():
    login = request.form["login"]
    password = request.form["password"]
    user = find_user(login)
    
    if user and user["password"] == password:
        session["login"] = user["login"]
        session["role"] = user["role"]
        return redirect("/dashboard")
    
    return "Неверный логин или пароль"


STAGE_LABELS = {
    "НДЗ": "5",
    "НДЗ 2": "9",
    "Перезвонить": "IN_PROCESS",
    "Приглашен к рекрутеру": "CONVERTED",
    "NEW": "NEW",
    "OLD": "UC_VTOOIM",
    "База ВВ": "11"
}

GROUPED_STAGES = ["NEW", "OLD", "База ВВ"]

user_cache = {"data": {}, "last": 0}

def get_range_dates(rtype):
    tz = timezone("Europe/Moscow")
    now = datetime.now(tz)
    if rtype == "week":
        start = now - timedelta(days=now.weekday())
    elif rtype == "month":
        start = now.replace(day=1)
    else:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.strftime("%Y-%m-%d %H:%M:%S"), now.strftime("%Y-%m-%d %H:%M:%S")

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
            start = r["next"]
    except Exception: pass
    user_cache["data"], user_cache["last"] = users, time.time()
    return users

def fetch_leads(stage, start, end):
    leads, offset = [], 0
    try:
        while True:
            r = requests.post(HOOK + "crm.lead.list.json", json={
                "filter": {">=DATE_MODIFY": start, "<=DATE_MODIFY": end, "STATUS_ID": stage},
                "select": ["ID", "ASSIGNED_BY_ID", "DATE_CREATE", "DATE_MODIFY", "STATUS_ID"],
                "start": offset
            }, timeout=10).json()
            page = r.get("result", [])
            if not page: break
            leads.extend(page)
            offset = r.get("next", 0)
            if not offset: break
    except Exception: pass
    return leads

def fetch_all_leads(stage):
    leads, offset = [], 0
    try:
        while True:
            r = requests.post(HOOK + "crm.lead.list.json", json={
                "filter": {"STATUS_ID": stage},
                "select": ["ID"],
                "start": offset
            }, timeout=10).json()
            page = r.get("result", [])
            if not page: break
            leads.extend(page)
            offset = r.get("next", 0)
            if not offset: break
    except Exception: pass
    return leads

@app.route("/api/leads/by-stage")
def leads_by_stage():
    start, end = get_range_dates("today")
    users = load_users()
    data = {}

    for name, stage_id in STAGE_LABELS.items():
        if name in GROUPED_STAGES:
            leads = fetch_all_leads(stage_id)
            data[name] = {"grouped": True, "count": len(leads)}
        else:
            leads = fetch_leads(stage_id, start, end)
            stats = Counter()
            for lead in leads:
                uid = lead.get("ASSIGNED_BY_ID")
                if uid: stats[int(uid)] += 1

            details = [
                {"operator": users.get(uid, f"ID {uid}"), "count": cnt}
                for uid, cnt in sorted(stats.items(), key=lambda x: -x[1])
            ]

            data[name] = {"grouped": False, "details": details}

    return {"range": "today", "data": data}

@app.route("/api/leads/info-stages-today")
def info_stages_today():
    result = []
    for name in GROUPED_STAGES:
        stage = STAGE_LABELS[name]
        leads = fetch_all_leads(stage)
        result.append({"name": name, "count": len(leads)})
    return {"range": "total", "info": result}

@app.route("/ping")
def ping(): return {"status": "ok"}

@app.route("/clock")
def clock():
    tz = timezone("Europe/Moscow")
    moscow_now = datetime.now(tz)
    utc_now = datetime.utcnow()
    return {
        "moscow": moscow_now.strftime("%Y-%m-%d %H:%M:%S"),
        "utc": utc_now.strftime("%Y-%m-%d %H:%M:%S")
    }

@app.route("/")
def home(): return app.send_static_file("dashboard.html")

@app.route("/active_operators_list")
def active_operators_list():
    operators = get_active_operators()
    return jsonify(operators)



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
