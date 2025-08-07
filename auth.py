from flask import jsonify, request
from werkzeug.security import check_password_hash
from functools import wraps

# Конфигурация пользователей (лучше вынести в config или БД)
USERS = {
    'admin': {
        'password_hash': 'pbkdf2:sha256:260000$X91...',  # сгенерированный хеш
        'role': 'Администратор'
    },
    'manager': {
        'password_hash': 'pbkdf2:sha256:260000$Y82...',
        'role': 'Менеджер'
    }
}

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Проверка аутентификации (например, по JWT или сессии)
        if not getattr(request, 'user', None):
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return decorated_function

def init_auth_routes(app):
    @app.route('/api/login', methods=['POST'])
    def login():
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        user = USERS.get(username)
        if user and check_password_hash(user['password_hash'], password):
            return jsonify({
                "status": "success",
                "user": {
                    "username": username,
                    "role": user['role']
                }
            })
        return jsonify({"status": "error"}), 401
