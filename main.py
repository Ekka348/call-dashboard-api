from flask import Flask, request, render_template_string, send_file, jsonify
import requests, os
from datetime import datetime, timedelta
from collections import Counter
import pandas as pd
import time
from pytz import timezone  # 🕒 для московского времени
from flask import render_template

app = Flask(__name__)
HOOK = "https://ers2023.bitrix24.ru/rest/27/1bc1djrnc455xeth/"
STAGE_LABELS = {
    "НДЗ": "5",
    "НДЗ 2": "9",
    "Перезвонить": "IN_PROCESS",
    "Приглашен к рекрутеру": "CONVERTED",
    "NEW": "NEW",
    "OLD": "11",
    "База ВВ": "UC_VTOOIM"
}

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
    moscow_now = datetime.now(tz)
    utc_now = datetime.utcnow()
    return {
        "moscow": moscow_now.strftime("%Y-%m-%d %H:%M:%S"),
        "utc": utc_now.strftime("%Y-%m-%d %H:%M:%S")
    }

@app.route("/daily")
def daily():
    label = request.args.get("label", "НДЗ")
    rtype = request.args.get("range", "today")
    stage = STAGE_LABELS.get(label, label)
    start, end = get_range_dates(rtype)
    users = load_users()
    leads = fetch_leads(stage, start, end)

    if not leads:
        return render_template_string(f"""
        <html><body>
        <h2>📭 Нет лидов по стадии: {label} за {rtype.upper()}</h2>
        <p>Фильтр: c {start} по {end} (московское время)</p>
        </body></html>
        """)

    stats = Counter()
    for l in leads:
        uid = l.get("ASSIGNED_BY_ID")
        if uid: stats[int(uid)] += 1
    rows = [f"<tr><td>{users.get(uid, uid)}</td><td>{cnt}</td></tr>" for uid, cnt in sorted(stats.items(), key=lambda x: -x[1])]
    return render_template_string(f"""
    <html><body>
    <h2>📊 Стадия: {label} — {rtype.upper()}</h2>
    <table border="1" cellpadding="6"><tr><th>Сотрудник</th><th>Количество</th></tr>{''.join(rows)}</table>
    <p>Всего лидов: {sum(stats.values())}</p></body></html>
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

    labels = [users.get(uid, str(uid)) for uid, _ in stats.items()]
    values = [cnt for _, cnt in stats.items()]

    return {
        "labels": labels,
        "values": values,
        "total": sum(values),
        "stage": label,
        "range": rtype
    }

@app.route("/summary_old")
def summary_old():
    stage = STAGE_LABELS.get("OLD", "UC_VTOOIM")
    leads = fetch_leads(stage, "2020-01-01 00:00:00", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    return jsonify({"count": len(leads)})

@app.route("/summary_stage")
def summary_stage():
    stage = request.args.get("stage")
    start = request.args.get("start", "2020-01-01 00:00:00")
    end = request.args.get("end", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    if not stage:
        return jsonify({"count": 0})
    leads = fetch_leads(stage, start, end)
    return jsonify({"count": len(leads)})

@app.route("/api/leads/stages")
def api_leads_stages():
    start = "2020-01-01 00:00:00"
    end = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    results = []

    for name, stage in STAGE_LABELS.items():
        leads = fetch_leads(stage, start, end)
        results.append({"name": name, "count": len(leads)})

    return jsonify({"stages": results})



@app.route("/")
def home():
    return render_template("dashboard.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))


