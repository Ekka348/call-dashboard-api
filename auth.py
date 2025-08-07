import os
import json
from datetime import datetime, timedelta  # Добавлен импорт datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from email_validator import validate_email, EmailNotValidError
from flask import Flask, jsonify, request
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required,
    get_jwt_identity, create_refresh_token
)

# Настройка приложения
app = Flask(__name__)
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET', 'super-secret-key')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=1)
app.config['JWT_REFRESH_TOKEN_EXPIRES'] = timedelta(days=30)
jwt = JWTManager(app)

# Конфигурация файла пользователей
USERS_FILE = 'users.json'
DEFAULT_ADMIN = {
    'username': 'admin',
    'password_hash': generate_password_hash('admin123'),
    'role': 'Администратор',
    'full_name': 'Главный Администратор',
    'email': 'admin@example.com',
    'is_active': True,
    'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),  # Исправлено
    'last_login': None
}

# Инициализация файла пользователей
def init_users_file():
    """Создает файл пользователей с администратором по умолчанию, если его нет"""
    if not os.path.exists(USERS_FILE):
        with open(USERS_FILE, 'w', encoding='utf-8') as f:
            json.dump({'users': [DEFAULT_ADMIN]}, f, ensure_ascii=False, indent=2)

init_users_file()

# Вспомогательные функции
def read_users():
    """Чтение пользователей из файла"""
    with open(USERS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)['users']

def write_users(users):
    """Запись пользователей в файл"""
    with open(USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump({'users': users}, f, ensure_ascii=False, indent=2)

def find_user(username):
    """Поиск пользователя по имени"""
    users = read_users()
    return next((u for u in users if u['username'] == username), None)

def validate_user_data(data, is_new_user=True):
    """Валидация данных пользователя"""
    errors = {}
    
    if is_new_user and not data.get('username'):
        errors['username'] = 'Имя пользователя обязательно'
    elif is_new_user and find_user(data.get('username', '')):
        errors['username'] = 'Пользователь с таким именем уже существует'
    
    if is_new_user and not data.get('password'):
        errors['password'] = 'Пароль обязателен'
    elif data.get('password') and len(data['password']) < 8:
        errors['password'] = 'Пароль должен содержать минимум 8 символов'
    
    if not data.get('role') or data['role'] not in ['Администратор', 'Менеджер', 'Оператор']:
        errors['role'] = 'Недопустимая роль пользователя'
    
    if data.get('email'):
        try:
            validate_email(data['email'])
        except EmailNotValidError:
            errors['email'] = 'Некорректный email'
    
    return errors if errors else None

def role_required(required_role):
    """Декоратор для проверки роли пользователя"""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            current_user = get_jwt_identity()
            user = find_user(current_user)
            
            if not user or user['role'] != required_role:
                return jsonify({"error": f"Требуется роль {required_role}"}), 403
            return f(*args, **kwargs)
        return wrapped
    return decorator

# API Endpoints
@app.route('/api/auth/login', methods=['POST'])
def login():
    """Аутентификация пользователя"""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({"error": "Не указаны имя пользователя или пароль"}), 400
    
    user = find_user(username)
    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify({"error": "Неверные учетные данные"}), 401
    
    if not user.get('is_active', True):
        return jsonify({"error": "Учетная запись деактивирована"}), 403
    
    # Обновляем время последнего входа
    users = read_users()
    for u in users:
        if u['username'] == username:
            u['last_login'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            break
    write_users(users)
    
    # Создаем JWT токены
    access_token = create_access_token(identity=username)
    refresh_token = create_refresh_token(identity=username)
    
    return jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {
            "username": user['username'],
            "role": user['role'],
            "full_name": user.get('full_name')
        }
    })

@app.route('/api/auth/refresh', methods=['POST'])
@jwt_required(refresh=True)
def refresh():
    """Обновление access токена"""
    current_user = get_jwt_identity()
    new_token = create_access_token(identity=current_user)
    return jsonify({"access_token": new_token})

@app.route('/api/users', methods=['POST'])
@jwt_required()
@role_required('Администратор')
def create_user():
    """Создание нового пользователя"""
    data = request.get_json()
    
    if errors := validate_user_data(data):
        return jsonify({"errors": errors}), 400
    
    new_user = {
        'username': data['username'],
        'password_hash': generate_password_hash(data['password']),
        'role': data['role'],
        'full_name': data.get('full_name', ''),
        'email': data.get('email', ''),
        'is_active': True,
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'last_login': None
    }
    
    users = read_users()
    users.append(new_user)
    write_users(users)
    
    return jsonify({"message": "Пользователь успешно создан"}), 201

@app.route('/api/users', methods=['GET'])
@jwt_required()
def list_users():
    """Получение списка пользователей"""
    users = read_users()
    # Фильтруем чувствительные данные
    filtered_users = [{
        'username': u['username'],
        'role': u['role'],
        'full_name': u.get('full_name'),
        'email': u.get('email'),
        'is_active': u.get('is_active', True),
        'created_at': u.get('created_at'),
        'last_login': u.get('last_login')
    } for u in users]
    
    return jsonify({"users": filtered_users})

@app.route('/api/users/<username>', methods=['PUT'])
@jwt_required()
def update_user(username):
    """Обновление информации о пользователе"""
    current_user = get_jwt_identity()
    user_to_update = find_user(username)
    
    if not user_to_update:
        return jsonify({"error": "Пользователь не найден"}), 404
    
    current_user_data = find_user(current_user)
    if current_user_data['role'] != 'Администратор' and current_user != username:
        return jsonify({"error": "Нет доступа"}), 403
    
    data = request.get_json()
    if errors := validate_user_data(data, is_new_user=False):
        return jsonify({"errors": errors}), 400
    
    users = read_users()
    updated = False
    
    for user in users:
        if user['username'] == username:
            if 'full_name' in data:
                user['full_name'] = data['full_name']
            if 'email' in data:
                user['email'] = data['email']
            if 'password' in data:
                user['password_hash'] = generate_password_hash(data['password'])
            if 'role' in data and current_user_data['role'] == 'Администратор':
                user['role'] = data['role']
            updated = True
            break
    
    if updated:
        write_users(users)
        return jsonify({"message": "Данные пользователя обновлены"})
    
    return jsonify({"error": "Ошибка при обновлении"}), 500

@app.route('/api/users/<username>/status', methods=['PUT'])
@jwt_required()
@role_required('Администратор')
def toggle_user_status(username):
    """Активация/деактивация пользователя"""
    if get_jwt_identity() == username:
        return jsonify({"error": "Нельзя изменить статус своей учетной записи"}), 400
    
    data = request.get_json()
    if 'is_active' not in data:
        return jsonify({"error": "Не указан статус"}), 400
    
    users = read_users()
    updated = False
    
    for user in users:
        if user['username'] == username:
            user['is_active'] = bool(data['is_active'])
            updated = True
            break
    
    if updated:
        write_users(users)
        return jsonify({"message": f"Статус пользователя {username} обновлен"})
    
    return jsonify({"error": "Пользователь не найден"}), 404

@app.route('/api/users/<username>', methods=['DELETE'])
@jwt_required()
@role_required('Администратор')
def delete_user(username):
    """Удаление пользователя"""
    if get_jwt_identity() == username:
        return jsonify({"error": "Нельзя удалить свою учетную запись"}), 400
    
    users = read_users()
    users = [u for u in users if u['username'] != username]
    
    write_users(users)
    
    return jsonify({"message": "Пользователь удален"})

# Обработчики ошибок JWT
@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return jsonify({"error": "Токен истек"}), 401

@jwt.invalid_token_loader
def invalid_token_callback(error):
    return jsonify({"error": "Неверный токен"}), 401

@jwt.unauthorized_loader
def missing_token_callback(error):
    return jsonify({"error": "Требуется авторизация"}), 401

def init_auth_routes(app):
    """Инициализация маршрутов аутентификации"""
    # Все маршруты уже зарегистрированы через декоратор @app.route
    return app

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port)
