from flask import Flask, request, render_template_string, jsonify
import requests, os, time
from datetime import datetime, timedelta
from collections import Counter
from pytz import timezone
from bitrix_utils import get_leads_by_status, get_total_leads_from_bitrix
from bitrix24 import Bitrix24
import sys
print(sys.path)

app = Flask(__name__)
HOOK = "https://ers2023.bitrix24.ru/rest/27/1bc1djrnc455xeth/"
bx24 = Bitrix24(HOOK)

STAGE_LABELS = {
    "НДЗ": "5",
    "НДЗ 2": "9",
    "Перезвонить": "IN_PROCESS",
    "Приглашен к рекрутеру": "CONVERTED"
}

TRACKED_STATUSES = ["NEW", "11", "UC_VTOOIM"]

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

@app.route("/ping")
def ping(): return {"status": "ok"}

@app.route("/clock")
def clock():
    tz = timezone("Europe/Moscow")
    return {
        "moscow": datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S"),
        "utc": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    }

@app.route("/compare")
def compare():
    label = request.args.get("label", "НДЗ")
    stage = STAGE_LABELS.get(label, label)
    tz = timezone("Europe/Moscow")
    now = datetime.now(tz)
    today_s, today_e = get_range_dates("today")
    y_start = (now - timedelta(days=1)).strftime("%Y-%m-%d 00:00:00")
    y_end = (now - timedelta(days=1)).strftime("%Y-%m-%d 23:59:59")
    users = load_users()

    today_stats = Counter()
    for l in fetch_leads(stage, today_s, today_e):
        uid = l.get("ASSIGNED_BY_ID")
        if uid: today_stats[int(uid)] += 1

    y_stats = Counter()
    for l in fetch_leads(stage, y_start, y_end):
        uid = l.get("ASSIGNED_BY_ID")
        if uid: y_stats[int(uid)] += 1

    rows = []
    for uid in set(today_stats) | set(y_stats):
        t, y = today_stats.get(uid, 0), y_stats.get(uid, 0)
        diff = t - y
        emoji = "📈" if diff > 0 else ("📉" if diff < 0 else "➖")
        name = users.get(uid, uid)
        rows.append(f"<tr><td>{name}</td><td>{y}</td><td>{t}</td><td>{diff}</td><td>{emoji}</td></tr>")
    return render_template_string(f"""
    <html><body>
    <h2>🔁 Сравнение: {label}</h2>
    <table border="1" cellpadding="6">
    <tr><th>Сотрудник</th><th>Вчера</th><th>Сегодня</th><th>Разница</th><th></th></tr>{''.join(rows)}</table>
    </body></html>
    """)

@app.route("/stats_data")
def stats_data():
    label = request.args.get("label", "НДЗ")
    rtype = request.args.get("range", "today")
    stage = STAGE_LABELS.get(label, label)
    start, end = get_range_dates(rtype)
    users = load_users()
    leads = fetch_leads(stage, start, end)

    stats = Counter()
    for lead in leads:
        uid = lead.get("ASSIGNED_BY_ID")
        if uid: stats[int(uid)] += 1

    return {
        "labels": [users.get(uid, str(uid)) for uid in stats],
        "values": [stats[uid] for uid in stats],
        "total": sum(stats.values()),
        "stage": label,
        "range": rtype
    }

@app.route("/daily_json")
def daily_json():
    label = request.args.get("label", "НДЗ")
    rtype = request.args.get("range", "today")
    start, end = get_range_dates(rtype)
    stage = STAGE_LABELS.get(label, label)
    leads = fetch_leads(stage, start, end)
    return jsonify({"count": len(leads)})

@app.route("/leads_by_status_today")
def leads_by_status_today():
    stats = get_leads_by_status(HOOK, TRACKED_STATUSES)
    return jsonify(stats)


# 🔑 Вебхук Bitrix24: замени на свой
url = "https://ers2023.bitrix24.ru/rest/27/1bc1djrnc455xeth/"

# 📦 Параметры запроса
payload = {
    "filter": {},  # пустой фильтр
    "select": ["ID", "TITLE", "STATUS_ID"]
}

# 🚀 Отправка запроса
response = requests.post(url, json=payload)

# 🧾 Обработка ответа
if response.status_code == 200:
    data = response.json()
    print("Лиды:", data["result"])
else:
    print(f"Ошибка: {response.status_code}")

@app.route("/")
def home(): return app.send_static_file("dashboard.html")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


