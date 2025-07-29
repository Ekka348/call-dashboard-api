# bitrix_utils.py

def get_leads_by_status(bx24, statuses):
    status_counts = {}
    for status in statuses:
        try:
            response = bx24.callMethod('crm.lead.list', {
                'filter': {'STATUS_ID': status},
                'select': ['ID']
            })
            leads = response.get('result', [])
            status_counts[status] = len(leads)
        except Exception as e:
            print(f"Ошибка при запросе статуса {status}: {e}")
            status_counts[status] = 'error'
    return status_counts
