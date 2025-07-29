from datetime import datetime, timedelta
from pytz import timezone

def get_range_dates(rtype):
    """
    Возвращает временной диапазон (начало и конец) для заданного типа периода:
    today / week / month
    """
    tz = timezone("Europe/Moscow")
    now = datetime.now(tz)

    if rtype == "week":
        start = now - timedelta(days=now.weekday())
    elif rtype == "month":
        start = now.replace(day=1)
    else:
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    return start.strftime("%Y-%m-%d %H:%M:%S"), now.strftime("%Y-%m-%d %H:%M:%S")


def get_leads_by_status(bx24, statuses):
    """
    Возвращает словарь: статус → количество лидов
    по каждому из заданных статусных ID
    """
    status_counts = {}

    for status in statuses:
        try:
            response = bx24.callMethod("crm.lead.list", {
                "filter": {
                    "STATUS_ID": status
                },
                "select": ["ID"]
            })

            leads = response.get("result", [])
            status_counts[status] = len(leads)

        except Exception as e:
            print(f"Ошибка при получении лидов по статусу {status}: {e}")
            status_counts[status] = "error"

    return status_counts


def get_total_leads_from_bitrix(bx24, range_type):
    """
    Возвращает общее количество лидов за период (today / week / month)
    """
    start, end = get_range_dates(range_type)
    all_leads = []
    offset = 0

    try:
        while True:
            response = bx24.callMethod("crm.lead.list", {
                "filter": {
                    ">=DATE_MODIFY": start,
                    "<=DATE_MODIFY": end
                },
                "select": ["ID"],
                "start": offset
            })

            page = response.get("result", [])
            all_leads.extend(page)

            offset = response.get("next", 0)
            if not offset:
                break

    except Exception as e:
        print(f"Ошибка получения общего списка лидов: {e}")

    return len(all_leads)
