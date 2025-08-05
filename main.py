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

# Инициализация патчинга для gevent
monkey.patch_all()

app = Flask(__name__)
socketio = SocketIO(app, async_mode='gevent')

# Конфигурация приложения
class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", os.urandom(24))
    BITRIX_HOOK = os.environ.get("BITRIX_HOOK_URL", "https://ers2023.bitrix24.ru/rest/27/1bc1djrnc455xeth/")
    SESSION_TIMEOUT = 3600  # 1 час
    USER_CACHE_TIMEOUT = 300  # 5 минут
    MAX_LOGIN_ATTEMPTS = 5
    LOG_FILE = 'app.log'
    DATA_UPDATE_INTERVAL = 60  # секунд (увеличено для стабильности)
    BITRIX_TIMEOUT = 30  # увеличенный таймаут
    TARGET_USERS = {
         3037: "Старицын Георгий",
        3025: "Гусева Екатерина",
        3019: "Фролова Екатерина",
        2919: "Петренко Дмитрий",
        2897: "Сененкова Ирина",
        2869: "Завидовская Наталья",
        2836: "Балакшина Анастасия",
        2776: "Борщевский Дмитрий",
        2762: "Лукьянова Лидия",
        2754: "Ткаченко Дарья",
        2714: "Росоха Анастасия",
        2672: "Владимирова Юлиана",
        2648: "Болдырева Екатерина",
        2636: "Морозов Андрей",
        2578: "Раджабова Эльвира",
        2566: "Сергеев Арсений",
        2304: "Дубровина Валерия",
        2302: "Астапенко Александра",
        2250: "Максимова Мария",
        2230: "Бучкина Альбина",
        2102: "Кузнецова Ангелина",
        2090: "Кондрашина Диана",
        2044: "Ценёва Полина",
        2008: "Ларина Ирина",
        1962: "Черкасова Юлия",
        1930: "Медведева Анна",
        1874: "Павлушова Екатерина",
        1504: "Хакимова Гульназ",
        1428: "Кузьминов Ярослав",
        1406: "Лузина Марина",
        1398: "Гриценин Вячеслав",
        1336: "Феоктистова Дарья",
        1300: "Козлова Екатерина",
        1240: "Муратова Эльмира",
        950: "Косолапова Вероника",
        910: "Сычева Оксана",
        908: "Майорова Алина",
        808: "Джалилова Айше",
        798: "Егорова Александра",
        790: "Фиолетова Ирина",
        750: "Русов Максим",
        722: "Шелега Ксения",
        584: "Семерина Валерия",
        576: "Панина Виктория",
        548: "Сунцов Тимур",
        544: "Доманова Татьяна",
        538: "Воронин Артемий",
        522: "Плёнкина Анастасия",
        502: "Мулаянова Ксения",
        385: "Ахматшина Алия",
        377: "Серикова Дарья",
        371: "Голова Ирина",
        227: "Демурия Александр",
        175: "Щербинина Анна",
        133: "Бардабаева Анна",
        91: "Николаева Светлана",
        71: "Жукова Диана",
        55: "Николаева Мария",
        45: "Лазарева Анна",
        35: "Шулигина Лада",
        29: "Носарев Алексей"
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
    maxBytes=100000,  # увеличен размер лога
    backupCount=3,
    encoding='utf-8'
)
handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
handler.setLevel(logging.DEBUG)  # включено подробное логирование
app.logger.addHandler(handler)
app.logger.setLevel(logging.DEBUG)

# Глобальный кэш данных
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

# Декораторы (остаются без изменений)
# ... (login_required, admin_required)

# Вспомогательные функции
def log_error(message, exc=None):
    error_msg = f"{message}: {str(exc) if exc else 'No details'}"
    app.logger.error(error_msg)
    with cache_lock:
        data_cache["last_error"] = error_msg

def find_user(login):
    try:
        with open("whitelist.json", "r", encoding="utf-8") as f:
            users = json.load(f)
        return next((u for u in users if u["login"] == login), None
    except Exception as e:
        log_error("Ошибка загрузки whitelist.json", e)
        return None

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
    else:  # month
        date_from = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_day = (now.replace(day=28) + timedelta(days=4)
        last_day = last_day.replace(day=1) - timedelta(days=1)
        date_to = last_day.replace(hour=23, minute=59, second=59, microsecond=999)
        period_name = date_from.strftime("%B %Y")
    
    return (
        date_from.strftime("%Y-%m-%d %H:%M:%S"),
        date_to.strftime("%Y-%m-%d %H:%M:%S"),
        period_name
    )

# Функции работы с Bitrix API
@lru_cache(maxsize=1000)
def get_status_history(lead_id, date_from, date_to):
    try:
        params = {
            "filter": {
                "ENTITY_ID": lead_id,
                "ENTITY_TYPE": "LEAD",
                "FIELD": "STATUS_ID",
                ">=DATE_CREATE": date_from,
                "<=DATE_CREATE": date_to
            },
            "select": ["ID", "FIELD", "FROM_VALUE", "TO_VALUE", "DATE_CREATE"],
            "start": -1
        }
        
        app.logger.debug(f"Requesting history for lead {lead_id} with params: {params}")
        
        response = requests.post(
            f"{app.config['BITRIX_HOOK']}crm.timeline.list.json",
            json=params,
            timeout=app.config['BITRIX_TIMEOUT']
        )
        
        response.raise_for_status()
        data = response.json()
        
        if "error" in data:
            error_msg = data.get("error_description", "Unknown Bitrix API error")
            app.logger.error(f"Bitrix API timeline error: {error_msg}")
            return []
        
        history = []
        for item in data.get("result", []):
            if item.get("FIELD") == "STATUS_ID":
                history.append({
                    "STATUS_ID": item["TO_VALUE"],
                    "DATE": item["DATE_CREATE"]
                })
        
        app.logger.debug(f"History for lead {lead_id}: {history}")
        return history
        
    except Exception as e:
        log_error(f"Error getting status history for lead {lead_id}", e)
        return []

def fetch_leads(stage_name, date_from, date_to):
    try:
        stage_config = app.config['STAGE_LABELS'][stage_name]
        params = {
            "filter": {
                "ASSIGNED_BY_ID": list(app.config['TARGET_USERS'].keys()),
                ">=DATE_MODIFY": date_from,
                "<=DATE_MODIFY": date_to
            },
            "select": ["ID", "ASSIGNED_BY_ID", "STATUS_ID", "DATE_MODIFY"],
            "start": -1
        }
        
        # Для стадии "Перезвонить" сначала получаем все лиды в процессе
        if stage_name == "Перезвонить":
            params["filter"]["STATUS_SEMANTIC_ID"] = "P"
        else:
            # Для других стадий фильтруем по конкретному статусу
            params["filter"]["STATUS_ID"] = stage_config["id"]
        
        app.logger.info(f"Fetching leads for stage '{stage_name}' with params: {params}")
        
        response = requests.post(
            f"{app.config['BITRIX_HOOK']}crm.lead.list.json",
            json=params,
            timeout=app.config['BITRIX_TIMEOUT']
        )
        
        response.raise_for_status()
        data = response.json()
        
        if "error" in data:
            error_msg = data.get("error_description", "Unknown Bitrix API error")
            app.logger.error(f"Bitrix API error: {error_msg}")
            return []
        
        leads = data.get("result", [])
        app.logger.info(f"Found {len(leads)} leads for stage '{stage_name}'")
        
        # Для стадии "Перезвонить" дополнительно проверяем историю
        if stage_name == "Перезвонить":
            filtered_leads = []
            for lead in leads:
                history = get_status_history(lead["ID"], date_from, date_to)
                if any(h["STATUS_ID"] == stage_config["id"] for h in history):
                    filtered_leads.append(lead)
            app.logger.info(f"After history filtering: {len(filtered_leads)} leads")
            return filtered_leads
        
        return leads
        
    except Exception as e:
        log_error(f"Error fetching leads for stage '{stage_name}'", e)
        return []

def load_users():
    try:
        users = {}
        for user_id, user_name in app.config['TARGET_USERS'].items():
            users[user_id] = {
                "name": user_name,
                "email": f"{user_name.split()[0].lower()}.{user_name.split()[1].lower()}@example.com"
            }
        app.logger.info(f"Loaded {len(users)} target users")
        return users
    except Exception as e:
        log_error("Error loading target users", e)
        return {}

# Фоновое обновление данных
def update_cache():
    while True:
        try:
            with cache_lock:
                data_cache["last_error"] = None
            
            app.logger.info("Starting cache update cycle...")
            start_time = time.time()
            
            period = 'month'  # можно добавить поддержку других периодов
            date_from, date_to, period_name = get_date_range(period)
            users = load_users()
            
            leads_by_stage = {}
            total_leads = 0
            
            for stage_name in app.config['STAGE_LABELS'].keys():
                leads = fetch_leads(stage_name, date_from, date_to)
                
                operator_stats = defaultdict(int)
                for lead in leads:
                    operator_id = int(lead["ASSIGNED_BY_ID"])
                    operator_stats[operator_id] += 1
                
                stage_data = []
                for user_id, user_name in app.config['TARGET_USERS'].items():
                    stage_data.append({
                        "operator": user_name,
                        "count": operator_stats.get(user_id, 0),
                        "user_id": user_id,
                        "email": users.get(user_id, {}).get("email", "")
                    })
                
                stage_data.sort(key=lambda x: (-x["count"], x["operator"]))
                leads_by_stage[stage_name] = stage_data
                total_leads += len(leads)
            
            with cache_lock:
                data_cache.update({
                    "leads_by_stage": leads_by_stage,
                    "total_leads": total_leads,
                    "last_updated": time.time(),
                    "current_month": period_name,
                    "users": users
                })
            
            socketio.emit('data_update', {
                'leads_by_stage': leads_by_stage,
                'total_leads': total_leads,
                'timestamp': datetime.now().strftime("%H:%M:%S"),
                'current_month': period_name
            })
            
            app.logger.info(
                f"Cache updated successfully in {time.time() - start_time:.2f}s. "
                f"Total leads: {total_leads}. Period: {period_name}"
            )
            
        except Exception as e:
            log_error("Critical error in cache update", e)
            time.sleep(120)  # увеличенная пауза при ошибке
        
        time.sleep(app.config['DATA_UPDATE_INTERVAL'])

# Маршруты (основные остаются без изменений)
# ... (index, auth, dashboard)

@app.route("/debug/lead/<int:lead_id>")
def debug_lead(lead_id):
    date_from, date_to, _ = get_date_range()
    history = get_status_history(lead_id, date_from, date_to)
    return jsonify({
        "lead_id": lead_id,
        "history": history,
        "period": f"{date_from} - {date_to}"
    })

@app.route("/debug/status")
def debug_status():
    with cache_lock:
        return jsonify({
            "last_updated": datetime.fromtimestamp(data_cache["last_updated"]).strftime("%Y-%m-%d %H:%M:%S"),
            "current_month": data_cache["current_month"],
            "has_data": any(data_cache["leads_by_stage"].values()),
            "error": data_cache["last_error"],
            "stages": {k: len(v) for k, v in data_cache["leads_by_stage"].items()}
        })

# ... (остальные маршруты и WebSocket обработчики)

if __name__ == "__main__":
    app.logger.info("Starting application with DEBUG logging...")
    socketio.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        debug=True,
        log_output=True
    )
