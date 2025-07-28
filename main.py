from flask import Flask, request, render_template_string, send_file
import requests, os
from datetime import datetime, timedelta
from collections import Counter
import pandas as pd
import time
from pytz import timezone  # 🕒 для московского времени
from flask import jsonify

app = Flask(__name__)
HOOK = "https://ers2023.bitrix24.ru/rest/27/1bc1djrnc455xeth/"
STAGE_LABELS = {
    "НДЗ": "5",
    "НДЗ 2": "9",
    "Перезвонить": "IN_PROCESS",
    "Приглашен к рекрутеру": "CONVERTED"
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

@app.route("/old_total")
def old_total():
    start, end = get_range_dates("today")
    stage = "UC_VTOOIM"  # это ID стадии OLD из AGGREGATE_STAGES
    leads = fetch_leads(stage, start, end)
    return {"total": len(leads), "stage": "OLD", "range": "today"}

@app.route("/new_total")
def new_total():
    start, end = get_range_dates("today")
    stage = "NEW"
    leads = fetch_leads(stage, start, end)
    return {"total": len(leads), "stage": "NEW", "range": "today"}

@app.route("/basevv_total")
def basevv_total():
    start, end = get_range_dates("today")
    stage = "11"
    leads = fetch_leads(stage, start, end)
    return {"total": len(leads), "stage": "База ВВ", "range": "today"}


@app.route("/daily_status")
def daily_status():
    status_id = request.args.get("status_id")
    if not status_id:
        return {"error": "no status_id"}, 400

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Сотрудник", "Количество"])
    for uid, cnt in stats.items():
        writer.writerow([users.get(uid, str(uid)), cnt])
    start, end = get_range_dates("today")
    leads = fetch_leads(status_id, start, end)

    mem = io.BytesIO()
    mem.write(output.getvalue().encode("utf-8"))
    mem.seek(0)
    count = sum(1 for lead in leads if lead.get("STATUS_ID") == status_id)
    return {"count": count}

    fname = f"{label}_{rtype}_stats.csv"
    return send_file(mem, mimetype="text/csv", as_attachment=True, download_name=fname)

@app.route('/api/lead_extended_summary')
def lead_extended_summary():
    today = datetime.date.today()

    return jsonify({
        "OLD": count_leads(stage_id="UC_VTOOIM"),
        "NEW_TODAY": count_leads(stage_id="NEW", date=today),
        "VV_TODAY": count_leads(stage_id="11", date=today)

@app.route("/")
def home():
    return app.send_static_file("dashboard.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

