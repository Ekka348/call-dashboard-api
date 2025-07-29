from flask import Flask, request, render_template_string, send_file
import requests, os
from datetime import datetime, timedelta
from collections import Counter
import pandas as pd
import time
from pytz import timezone  # 🕒 для московского времени

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

@app.route("/compare")
def compare():
    label = request.args.get("label", "НДЗ")
    stage = STAGE_LABELS.get(label, label)
    tz = timezone("Europe/Moscow")
    now = datetime.now(tz)
    today_s, today_e = get_range_dates("today")
    yesterday = now - timedelta(days=1)
    y_start = yesterday.strftime("%Y-%m-%d 00:00:00")
    y_end = yesterday.strftime("%Y-%m-%d 23:59:59")
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

@app.route("/debug")
def debug():
    label = request.args.get("label", "НДЗ")
    rtype = request.args.get("range", "today")
    stage = STAGE_LABELS.get(label, label)
    start, end = get_range_dates(rtype)

    leads = fetch_leads(stage, start, end)
    chunk = leads[:10]

    rows = []
    for l in chunk:
        rows.append(f"""
        <tr>
          <td>{l.get("ID")}</td>
          <td>{l.get("STATUS_ID")}</td>
          <td>{l.get("ASSIGNED_BY_ID", "Нет")}</td>
          <td>{l.get("DATE_CREATE", "—")}</td>
          <td>{l.get("DATE_MODIFY", "—")}</td>
        </tr>
        """)

    html = f"""
    <html><body>
    <h2>🔍 DEBUG: первые лиды со стадии {label}</h2>
    <p>Фильтр: c {start} по {end} (московское время)</p>
    <table border="1" cellpadding="6">
      <tr><th>ID</th><th>STATUS_ID</th><th>Сотрудник</th><th>Создан</th><th>Изменён</th></tr>
      {''.join(rows)}
    </table>
    <p>Всего лидов: {len(leads)}</p>
    </body></html>
    """
    return render_template_string(html)

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

@app.route("/summary_vv")
def summary_vv():
    rtype = request.args.get("range", "today")
    stage = STAGE_LABELS.get("База ВВ", "UC_VTOOIM")
    start, end = get_range_dates(rtype)
    leads = fetch_leads(stage, start, end)

    return render_template_string(f"""
    <html><body>
    <h2>📦 База ВВ — всего лидов за {rtype.upper()}</h2>
    <p>Диапазон: {start} — {end}</p>
    <p><strong>Количество лидов:</strong> {len(leads)}</p>
    </body></html>
    """)


@app.route("/")
def home(): return app.send_static_file("dashboard.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))



