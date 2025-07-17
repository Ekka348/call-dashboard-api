# main.py
from flask import Flask, request, render_template_string, send_file
import requests, os
from datetime import datetime, timedelta
from collections import Counter, defaultdict
import pandas as pd

app = Flask(__name__)

HOOK = "https://ers2023.bitrix24.ru/rest/27/1bc1djrnc455xeth/"
STAGE_LABELS = {
    "НДЗ": "5",
    "НДЗ 2": "9",
    "Перезвонить": "IN_PROCESS",
    "Приглашен к рекрутеру": "CONVERTED"
}

def get_range_dates(rtype):
    now = datetime.now()
    if rtype == "week":
        start = now - timedelta(days=now.weekday())
    elif rtype == "month":
        start = now.replace(day=1)
    else:
        start = now
    return start.strftime("%Y-%m-%d %H:%M:%S"), now.strftime("%Y-%m-%d %H:%M:%S")

def load_users():
    users = {}
    start = 0
    while True:
        r = requests.post(HOOK + "user.get.json", json={"start": start}).json()
        result = r.get("result", [])
        for u in result:
            users[int(u["ID"])] = f'{u["NAME"]} {u["LAST_NAME"]}'
        if "next" not in r:
            break
        start = r["next"]
    return users

def fetch_leads(stage, start, end):
    leads = []
    offset = 0
    while True:
        r = requests.post(HOOK + "crm.lead.list.json", json={
            "filter": {
                ">=DATE_MODIFY": start,
                "<=DATE_MODIFY": end,
                "STATUS_ID": stage
            },
            "select": ["ID", "ASSIGNED_BY_ID", "DATE_MODIFY"],
            "start": offset
        }).json()
        page = r.get("result", [])
        if not page:
            break
        leads.extend(page)
        offset = r.get("next", 0)
        if not offset:
            break
    return leads

@app.route("/daily")
def daily_report():
    label = request.args.get("label", "НДЗ")
    rtype = request.args.get("range", "today")
    stage = STAGE_LABELS.get(label, label)
    start, end = get_range_dates(rtype)
    users = load_users()
    user_map = {uid: name for uid, name in users.items()}

    leads = fetch_leads(stage, start, end)
    stats = Counter()
    for lead in leads:
        uid = lead.get("ASSIGNED_BY_ID")
        if uid: stats[int(uid)] += 1

    sorted_stats = sorted(stats.items(), key=lambda x: x[1], reverse=True)
    html_rows = [f"<tr><td>{user_map.get(uid, uid)}</td><td>{count}</td></tr>" for uid, count in sorted_stats]
    table = f"""
    <html><body>
    <h2>📊 Стадия: {label} за {rtype.upper()}</h2>
    <table border="1" cellpadding="6">
    <tr><th>Сотрудник</th><th>Количество</th></tr>
    {''.join(html_rows)}
    </table>
    <p>Всего лидов: {sum(stats.values())}</p>
    </body></html>
    """
    return render_template_string(table)

@app.route("/compare")
def compare():
    label = request.args.get("label", "НДЗ")
    stage = STAGE_LABELS.get(label, label)
    today_s, today_e = get_range_dates("today")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    y_start = f"{yesterday} 00:00:00"
    y_end = f"{yesterday} 23:59:59"

    users = load_users()
    today_stats = Counter()
    for l in fetch_leads(stage, today_s, today_e):
        uid = l.get("ASSIGNED_BY_ID")
        if uid: today_stats[int(uid)] += 1
    yesterday_stats = Counter()
    for l in fetch_leads(stage, y_start, y_end):
        uid = l.get("ASSIGNED_BY_ID")
        if uid: yesterday_stats[int(uid)] += 1

    rows = []
    for uid in set(today_stats.keys()).union(yesterday_stats.keys()):
        t = today_stats.get(uid, 0)
        y = yesterday_stats.get(uid, 0)
        diff = t - y
        emoji = "📈" if diff > 0 else ("📉" if diff < 0 else "➖")
        name = users.get(uid, str(uid))
        rows.append(f"<tr><td>{name}</td><td>{y}</td><td>{t}</td><td>{diff}</td><td>{emoji}</td></tr>")
    html = f"""
    <html><body>
    <h2>🔁 Сравнение по стадии: {label}</h2>
    <table border="1" cellpadding="6">
    <tr><th>Сотрудник</th><th>Вчера</th><th>Сегодня</th><th>Разница</th><th></th></tr>
    {''.join(rows)}
    </table>
    </body></html>
    """
    return render_template_string(html)

@app.route("/trend")
def hourly():
    label = request.args.get("label", "НДЗ")
    stage = STAGE_LABELS.get(label, label)
    start, end = get_range_dates("today")
    leads = fetch_leads(stage, start, end)

    hourly_counter = Counter()
    for lead in leads:
        dt = lead.get("DATE_MODIFY")
        if dt:
            hour = dt[11:13]  # HH from "YYYY-MM-DD HH:MM:SS"
            hourly_counter[hour] += 1

    rows = [f"<tr><td>{hour}:00</td><td>{count}</td></tr>" for hour, count in sorted(hourly_counter.items())]
    html = f"""
    <html><body>
    <h2>📈 Активность по часам — {label}</h2>
    <table border="1" cellpadding="6">
    <tr><th>Час</th><th>Лидов</th></tr>
    {''.join(rows)}
    </table>
    </body></html>
    """
    return render_template_string(html)

@app.route("/stuck")
def stuck():
    label = request.args.get("label", "НДЗ")
    days = int(request.args.get("days", "3"))
    stage = STAGE_LABELS.get(label, label)
    now = datetime.now()
    threshold = now - timedelta(days=days)
    start = "2020-01-01 00:00:00"
    end = threshold.strftime("%Y-%m-%d %H:%M:%S")

    leads = fetch_leads(stage, start, end)
    users = load_users()
    stats = Counter()
    for lead in leads:
        uid = lead.get("ASSIGNED_BY_ID")
        if uid: stats[int(uid)] += 1

    rows = [f"<tr><td>{users.get(uid, uid)}</td><td>{count}</td></tr>" for uid, count in stats.items()]
    html = f"""
    <html><body>
    <h2>⏳ Зависшие лиды — стадия: {label}, старше {days} дней</h2>
    <table border="1" cellpadding="6">
    <tr><th>Сотрудник</th><th>Количество</th></tr>
    {''.join(rows)}
    </table>
    </body></html>
    """
    return render_template_string(html)

@app.route("/download")
def download():
    label = request.args.get("label", "НДЗ")
    rtype = request.args.get("range", "today")
    stage = STAGE_LABELS.get(label, label)
    start, end = get_range_dates(rtype)
    leads = fetch_leads(stage, start, end)
    users = load_users()

    data = []
    for lead in leads:
        uid = lead.get("ASSIGNED_BY_ID", "Нет")
        name = users.get(int(uid), uid) if uid != "Нет" else "Нет"
        data.append({
            "ID": lead["ID"],
            "Сотрудник": name,
            "Дата": lead.get("DATE_MODIFY", "")
        })
    df = pd.DataFrame(data)
    file_path = f"report_{label}_{rtype}.csv"
    df.to_csv(file_path, index=False, encoding="utf-8")
    return send_file(file_path, as_attachment=True)

@app.route("/")
def home():
    return app.send_static_file("dashboard
