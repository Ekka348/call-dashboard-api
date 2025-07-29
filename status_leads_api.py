from flask import Flask, jsonify
from bitrix24 import Bitrix24  # Предположим, используешь SDK Bitrix24

app = Flask(__name__)

# Конфигурация Bitrix
bx24 = Bitrix24('https://ers2023.bitrix24.ru/rest/27/1bc1djrnc455xeth/, 'WEBHOOK_KEY')

# Список отслеживаемых статусов
TRACKED_STATUSES = ['NEW', '11', 'UC_VTOOIM']

@app.route('/leads_by_status_today')
def get_leads_by_status_today():
    status_counts = {}

    for status in TRACKED_STATUSES:
        response = bx24.callMethod('crm.lead.list', {
            'filter': {
                'STATUS_ID': status
            },
            'select': ['ID']
        })

        leads = response.get('result', [])
        status_counts[status] = len(leads)

    return jsonify(status_counts)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
