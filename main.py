from flask import Flask, request, render_template_string
import requests
from datetime import datetime, timedelta
from collections import Counter
import os

app = Flask(__name__)
HOOK = "https://ers2023.bitrix24.ru/rest/27/1bc1djrnc455xeth/"

STAGE_LABELS = {
    "Старт": "UC_ESHRMD",
    "НДЗ": "5",
    "НДЗ 2": "9",
    "Перезвонить": "IN_PROCESS",
    "Приглашен к рекрутеру": "CONVERTED"
}

def get_range_dates(rtype):
    today = datetime.now()
    if rtype == "week":
        start = today - timedelta(days=today.weekday())
    elif rtype == "month":
        start = today.replace(day=1)
    else:
        start = today
    return datetime.combine(start.date(), datetime.min.time()), datetime.combine(today.date(), datetime.max.time())

def load_all_users():
    users = []
    start = 0
    while True:
        resp = requests.post(HOOK + "user.get.json", json={
            "SELECT": ["ID", "NAME", "LAST_NAME"],
            "start": start
        }).json()
        batch = resp.get("result", [])
        if not batch:
            break
        users.extend(batch)
        start = resp.get("next", 0)
        if not start:
            break
    return users

@app.route("/daily")
def report():
    label = request.args.get("label", "НДЗ")
    stage = STAGE_LABELS.get(label, label)
    rtype = request.args.get("range", "today")

    start_dt, end_dt = get_range_dates(rtype)
    users = load_all_users()
    user_map = {int(u["ID"]): f"{u['NAME']} {u['LAST_NAME']}" for u in users}

    start = 0
    leads = []
    while True:
        data = requests.post(HOOK + "crm.lead.list.json", json={
            "filter": {
                ">=DATE_MODIFY": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "<=DATE_MODIFY": end_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "STATUS_ID": stage
            },
            "select": ["ID", "ASSIGNED_BY_ID"],
            "start": start
        }).json()
        page = data.get("result", [])
        if not page:
            break
        leads.extend(page)
        start = data.get("next", 0)
        if not start:
            break

    stats = {}
    unassigned = 0
    for lead in leads:
        uid = lead.get("ASSIGNED_BY_ID")
        if uid is None:
            unassigned += 1
            continue
        try:
            uid = int(uid)
        except:
            unassigned += 1
            continue
        stats[uid] = stats.get(uid, 0) + 1

    sorted_stats = sorted(stats.items(), key=lambda x: x[1], reverse=True)
    total = sum(count for _, count in sorted_stats)
    top5_heavy = sorted_stats[:5]
    visualize = label not in ["Старт"]

    rows = []
    for i, (uid, count) in enumerate(sorted_stats):
        name = user_map.get(uid, f"ID {uid}")
        medal = ""
        warning = ""

        if label == "Приглашен к рекрутеру":
            if i == 0: medal = "🥇"
            elif i == 1: medal = "🥈"
            elif i == 2: medal = "🥉"
            if count <= 3:
                warning = "❗"
        elif visualize:
            if (uid, count) in top5_heavy:
                warning = "❗"
            if i >= len(sorted_stats) - 3:
                if i == len(sorted_stats) - 1: medal = "🥇"
                elif i == len(sorted_stats) - 2: medal = "🥈"
                elif i == len(sorted_stats) - 3: medal = "🥉"

        rows.append(f"<tr><td>{medal}</td><td>{name}</td><td>{count}</td><td>{warning}</td></tr>")

    html = f"""
    <html>
    <head><title>Отчёт: {label}</title></head>
    <body style="font-family:Arial; padding:40px;">
        <h2>📊 Стадия: {label} за {rtype.upper()}</h2>
        <table border="1" cellpadding="6" style="border-collapse: collapse;">
            <tr><th>🏅</th><th>Сотрудник</th><th>Количество</th><th>⚠️</th></tr>
            {''.join(rows)}
        </table>
        <p>ℹ️ Всего у ответственных: <strong>{total}</strong></p>
        {'<p>🚫 Без исполнителя: ' + str(unassigned) + '</p>' if unassigned > 0 else ''}
    </body>
    </html>
    """
    return render_template_string(html)

@app.route("/count")
def count_report():
    label = request.args.get("label", "НДЗ")
    stage = STAGE_LABELS.get(label, label)

    date_counter = Counter()
    start = 0
    while True:
        data = requests.post(HOOK + "crm.lead.list.json", json={
            "filter": { "STATUS_ID": stage },
            "select": ["ID", "DATE_MODIFY"],
            "start": start
        }).json()
        page = data.get("result", [])
        if not page:
            break

        for lead in page:
            dt = lead.get("DATE_MODIFY")
            if dt:
                date_only = dt.split("T")[0]
                date_counter[date_only] += 1

        start = data.get("next", 0)
        if not start:
            break

    rows = [f"<tr><td>{day}</td><td>{count}</td></tr>" for day, count in sorted(date_counter.items(), reverse=True)]
    html = f"""
    <html>
    <head><title>Динамика стадий</title></head>
    <body style="font-family:Arial; padding:40px;">
        <h2>📊 Стадия: {label} — по дате изменения</h2>
        <table border="1" cellpadding="6" style="border-collapse: collapse;">
            <tr><th>📅 Дата</th><th>Количество</th></tr>
            {''.join(rows)}
        </table>
    </body>
    </html>
    """
    return render_template_string(html)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
