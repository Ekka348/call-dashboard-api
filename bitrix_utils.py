import requests
from datetime import datetime, timedelta
from pytz import timezone
from collections import Counter

HOOK = "https://ers2023.bitrix24.ru/rest/27/1bc1djrnc455xeth/"  # 🔑 Вынеси в .env или передавай извне
STAGE_LABELS = {
    "НДЗ": "5",
    "НДЗ 2": "9",
    "Перезвонить": "IN_PROCESS",
    "Приглашен к рекрутеру": "CONVERTED"
}

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

def fetch_leads(stage, start, end):
    leads, offset = [], 0
    try:
        while True:
            r = requests.post(HOOK + "crm.lead.list.json", json={
                "filter": {
                    "STATUS_ID": stage,
                    ">=DATE_MODIFY": start,
                    "<=DATE_MODIFY": end
                },
                "select": ["ID", "ASSIGNED_BY_ID", "STATUS_ID", "DATE_MODIFY"],
                "start": offset
            }, timeout=10).json()
            page = r.get("result", [])
            if not page: break
            leads.extend(page)
            offset = r.get("next", 0)
            if not offset: break
    except Exception:
        pass
    return leads

def get_total_leads_from_bitrix(hook, rtype):
    start, end = get_range_dates(rtype)
    stage = STAGE_LABELS.get("НДЗ", "5")  # 💡 можно параметризовать
    leads = fetch_leads(stage, start, end)
    return len(leads)

def get_stats_summary(hook, rtype):
    start, end = get_range_dates(rtype)
    stage = STAGE_LABELS.get("НДЗ", "5")
    leads = fetch_leads(stage, start, end)

    stats = Counter()
    for lead in leads:
        uid = lead.get("ASSIGNED_BY_ID")
        if uid: stats[int(uid)] += 1

    return {
        "users": list(stats.keys()),
        "values": list(stats.values()),
        "total": sum(stats.values())
    }

def get_leads_data(hook, rtype):
    start, end = get_range_dates(rtype)
    stage = STAGE_LABELS.get("НДЗ", "5")
    leads = fetch_leads(stage, start, end)

    return [
        {
            "id": l.get("ID"),
            "assigned_to": l.get("ASSIGNED_BY_ID"),
            "status": l.get("STATUS_ID"),
            "modified": l.get("DATE_MODIFY")
        }
        for l in leads
    ]
