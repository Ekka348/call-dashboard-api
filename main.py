from flask import Flask, request, jsonify
from datetime import datetime, timedelta
from collections import Counter
import requests, time
from pytz import timezone

app = Flask(__name__)

# 💡 Настройки
HOOK = "https://ers2023.bitrix24.ru/rest/27/1bc1djrnc455xeth/"
STAGE_LABELS = {
    "НДЗ": "5",
    "НДЗ 2": "9",
    "Перезвонить": "IN_PROCESS",
    "Приглашен к рекрутеру": "CONVERTED"
}
AGGREGATE_STAGES = {
    "NEW": "NEW",
    "OLD": "UC_VTOOIM",
    "База ВВ": "11"
}
user_cache = {"data": {}, "last": 0}

# ⏳ Временные интервалы
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

# 👥 Получение сотрудников
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

# 🔍 Получение лидов
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
    except Exception: pass
    return leads

# 📊 API для стадий по операторам
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

    labels = [users.get(uid, str(uid)) for uid, _ in stats.items()]
    values = [cnt for _, cnt in stats.items()]

    return jsonify({
        "stage": label,
        "range": rtype,
        "labels": labels,
        "values": values,
        "total": sum(values)
    })

# 📦 API для общей нижней таблицы (NEW, OLD, База ВВ)
@app.route("/totals")
def totals():
    start, end = get_range_dates("today")
    results = []
    for label, stage_id in AGGREGATE_STAGES.items():
        leads = fetch_leads(stage_id, start, end)
        results.append({"label": label, "count": len(leads)})
    return jsonify({"range": "today", "data": results})

# 🔧 Пинг
@app.route("/ping")
def ping(): return jsonify({"status": "ok"})

@app.route("/")
def home(): return app.send_static_file("dashboard.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
