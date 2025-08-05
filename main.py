from flask import Flask, request, redirect, session, jsonify, render_template
from functools import wraps, lru_cache
import requests, os, time, json
from datetime import datetime, timedelta
from collections import defaultdict
from pytz import timezone
from threading import Thread, Lock
import logging
from logging.handlers import RotatingFileHandler
from flask_socketio import SocketIO
from gevent import monkey

monkey.patch_all()

app = Flask(__name__)
socketio = SocketIO(app, async_mode='gevent', cors_allowed_origins="*")

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", os.urandom(24))
    BITRIX_HOOK = os.environ.get("BITRIX_HOOK_URL", "https://ers2023.bitrix24.ru/rest/27/1bc1djrnc455xeth/")
    SESSION_TIMEOUT = 3600
    USER_CACHE_TIMEOUT = 300
    MAX_LOGIN_ATTEMPTS = 5
    LOG_FILE = 'app.log'
    DATA_UPDATE_INTERVAL = 60
    BITRIX_TIMEOUT = 30
    MAX_LEADS_PER_REQUEST = 50  # Ограничение Bitrix API
    
    TARGET_USERS = {
        # ... (ваш список пользователей остаётся без изменений)
    }
    
    STAGE_LABELS = {
        "Перезвонить": {"id": "IN_PROCESS", "semantic": "P"},
        "На согласовании": {"id": "UC_A2DF81", "semantic": "P"}, 
        "Приглашен к рекрутеру": {"id": "CONVERTED", "semantic": "S"},
        "НДЗ": {"id": "5", "semantic": "P"},
        "НДЗ 2": {"id": "9", "semantic": "P"}
    }

app.config.from_object(Config)
app.secret_key = app.config['SECRET_KEY']

# Настройка логирования
handler = RotatingFileHandler(
    app.config['LOG_FILE'],
    maxBytes=100000,
    backupCount=3,
    encoding='utf-8'
)
handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
handler.setLevel(logging.DEBUG)
app.logger.addHandler(handler)
app.logger.setLevel(logging.DEBUG)

data_cache = {
    "leads_by_stage": {},
    "operators_stats": {},
    "total_leads": 0,
    "last_updated": 0,
    "last_error": None,
    "current_month": "",
    "users": {}
}
cache_lock = Lock()

# ... (остальные функции-декораторы остаются без изменений)

def get_date_range(period='month'):
    tz = timezone("Europe/Moscow")
    now = datetime.now(tz)
    
    if period == 'day':
        date_from = now.replace(hour=0, minute=0, second=0, microsecond=0)
        date_to = now.replace(hour=23, minute=59, second=59, microsecond=999)
        period_name = date_from.strftime("%d.%m.%Y")
    elif period == 'week':
        date_from = now - timedelta(days=now.weekday())
        date_from = date_from.replace(hour=0, minute=0, second=0, microsecond=0)
        date_to = date_from + timedelta(days=6)
        date_to = date_to.replace(hour=23, minute=59, second=59, microsecond=999)
        period_name = f"{date_from.strftime('%d.%m')}-{date_to.strftime('%d.%m.%Y')}"
    else:
        date_from = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_day = (now.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        date_to = last_day.replace(hour=23, minute=59, second=59, microsecond=999)
        period_name = date_from.strftime("%B %Y")
    
    return (
        date_from.strftime("%Y-%m-%d %H:%M:%S"),
        date_to.strftime("%Y-%m-%d %H:%M:%S"),
        period_name
    )

def fetch_all_leads(date_from, date_to):
    """Новая функция для получения всех лидов за один запрос"""
    try:
        all_leads = []
        start = 0
        
        while True:
            params = {
                "filter": {
                    "ASSIGNED_BY_ID": list(app.config['TARGET_USERS'].keys()),
                    ">=DATE_MODIFY": date_from,
                    "<=DATE_MODIFY": date_to
                },
                "select": ["ID", "ASSIGNED_BY_ID", "STATUS_ID", "DATE_MODIFY", "STATUS_SEMANTIC_ID"],
                "start": start
            }
            
            response = requests.post(
                f"{app.config['BITRIX_HOOK']}crm.lead.list.json",
                json=params,
                timeout=app.config['BITRIX_TIMEOUT']
            )
            response.raise_for_status()
            data = response.json()
            
            if "error" in data:
                raise Exception(data.get("error_description", "Unknown Bitrix API error"))
            
            leads = data.get("result", [])
            if not leads:
                break
                
            all_leads.extend(leads)
            start += app.config['MAX_LEADS_PER_REQUEST']
            
            if len(leads) < app.config['MAX_LEADS_PER_REQUEST']:
                break
        
        return all_leads
    except Exception as e:
        log_error("Error fetching all leads", e)
        return []

def update_cache():
    while True:
        try:
            date_from, date_to, period_name = get_date_range()
            users = load_users()
            
            # Получаем все лиды за один запрос
            all_leads = fetch_all_leads(date_from, date_to)
            app.logger.debug(f"Total leads fetched: {len(all_leads)}")
            
            # Группируем лиды по стадиям и операторам
            leads_by_stage = {stage: defaultdict(int) for stage in app.config['STAGE_LABELS']}
            operator_stats = defaultdict(lambda: defaultdict(int))
            
            for lead in all_leads:
                operator_id = int(lead["ASSIGNED_BY_ID"])
                status_id = lead["STATUS_ID"]
                
                # Находим к какой стадии относится лид
                for stage_name, stage_config in app.config['STAGE_LABELS'].items():
                    if status_id == stage_config["id"]:
                        operator_stats[stage_name][operator_id] += 1
                        break
                else:
                    # Если стадия не найдена в конфиге, пропускаем лид
                    continue
            
            # Формируем данные для каждой стадии
            result_data = {}
            total_leads = 0
            
            for stage_name in app.config['STAGE_LABELS'].keys():
                stage_data = []
                for user_id, user_name in app.config['TARGET_USERS'].items():
                    count = operator_stats[stage_name].get(user_id, 0)
                    stage_data.append({
                        "operator": user_name,
                        "count": count,
                        "user_id": user_id,
                        "email": f"{user_name.split()[0].lower()}.{user_name.split()[1].lower()}@example.com"
                    })
                
                stage_data.sort(key=lambda x: (-x["count"], x["operator"]))
                result_data[stage_name] = stage_data
                total_leads += sum(operator_stats[stage_name].values())
            
            with cache_lock:
                data_cache.update({
                    "leads_by_stage": result_data,
                    "total_leads": total_leads,
                    "last_updated": time.time(),
                    "current_month": period_name,
                    "users": users
                })
            
            socketio.emit('data_update', {
                'leads_by_stage': result_data,
                'total_leads': total_leads,
                'timestamp': datetime.now().strftime("%H:%M:%S"),
                'current_month': period_name
            })
            
            time.sleep(app.config['DATA_UPDATE_INTERVAL'])
            
        except Exception as e:
            log_error("Error in cache update", e)
            time.sleep(120)

# ... (остальные маршруты остаются без изменений)

@socketio.on('connect')
def handle_connect():
    app.logger.info('Client connected')
    with cache_lock:
        socketio.emit('data_update', {
            'leads_by_stage': data_cache["leads_by_stage"],
            'total_leads': data_cache["total_leads"],
            'timestamp': datetime.fromtimestamp(data_cache["last_updated"]).strftime("%H:%M:%S"),
            'current_month': data_cache["current_month"]
        })

if __name__ == "__main__":
    app.logger.info("Starting application")
    Thread(target=update_cache, daemon=True).start()
    socketio.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        log_output=True
    )
