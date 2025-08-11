# auth.py
from functools import wraps
from flask import request, jsonify
import os
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Whitelist допустимых пользователей (логин: пароль)
USER_WHITELIST = {
    os.getenv('AUTH_USERNAME', 'admin'): os.getenv('AUTH_PASSWORD', 'admin123'),
    "manager": "manager123"
}

def check_auth(username, password):
    """Проверяет, есть ли пользователь в белом списке"""
    return USER_WHITELIST.get(username) == password

def authenticate():
    """Отправляет ответ 401 с требованием аутентификации"""
    return jsonify({
        "status": "error",
        "message": "Authentication required"
    }), 401

def requires_auth(f):
    """Декоратор для защиты маршрутов"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated
