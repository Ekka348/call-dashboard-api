from functools import wraps
from flask import request, Response
import os
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

def check_auth(username, password):
    """Проверка учетных данных из .env"""
    auth_users = os.environ.get('AUTH_USERS', '').split(',')
    for user in auth_users:
        if not user.strip():
            continue
        parts = user.strip().split(':')
        if len(parts) == 3:
            u, p, role = parts
            if username == u and password == p:
                return role
    return None

def requires_auth(f):
    """Декоратор для защиты маршрутов"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        user_role = check_auth(auth.username, auth.password) if auth else None
        
        if not user_role:
            return Response(
                'Неверные учетные данные\n',
                401,
                {'WWW-Authenticate': 'Basic realm="Login Required"'}
            )
        
        # Добавляем роль пользователя в kwargs
        kwargs['user_role'] = user_role
        kwargs['username'] = auth.username
        return f(*args, **kwargs)
    return decorated
