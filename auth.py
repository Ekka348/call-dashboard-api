import os
import sqlite3
import logging
from datetime import timedelta
from functools import wraps

from flask import Flask, jsonify, request
from werkzeug.security import generate_password_hash, check_password_hash
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required,
    get_jwt_identity, create_refresh_token
)
from email_validator import validate_email, EmailNotValidError

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация приложения Flask
app = Flask(__name__)
app.config['JWT_SECRET_KEY'] = os.environ.get('JWT_SECRET', 'super-secret-key')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=1)
app.config['JWT_REFRESH_TOKEN_EXPIRES'] = timedelta(days=30)
jwt = JWTManager(app)

# Инициализация БД
def init_db():
    """Инициализация базы данных SQLite"""
    with sqlite3.connect('users.db') as conn:
        conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('Администратор', 'Менеджер', 'Оператор')),
            full_name TEXT,
            email TEXT,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP
        )
        ''')
        
        # Проверяем, есть ли хотя бы один администратор
        cursor = conn.execute("SELECT 1 FROM users WHERE role = 'Администратор' LIMIT 1")
        if not cursor.fetchone():
            admin_hash = generate_password_hash('admin123')
            conn.execute(
                "INSERT INTO users (username, password_hash, role, full_name, email) VALUES (?, ?, ?, ?, ?)",
                ('admin', admin_hash, 'Администратор', 'Главный Администратор', 'admin@example.com')
            )
        conn.commit()

init_db()

# Вспомогательные функции
def get_db_connection():
    """Получение соединения с БД"""
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row
    return conn

def validate_user_data(data, is_new_user=True):
    """Валидация данных пользователя"""
    errors = {}
    
    if is_new_user and not data.get('username'):
        errors['username'] = 'Имя пользователя обязательно'
    
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

def log_user_action(action, target_user=None):
    """Логирование действий пользователей"""
    current_user = get_jwt_identity()
    message = f"User action: {current_user} | {action}"
    if target_user:
        message += f" | Target: {target_user}"
    logger.info(message)

# Декораторы для проверки прав
def role_required(required_role):
    """Декоратор для проверки роли пользователя"""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            current_user = get_jwt_identity()
            with get_db_connection() as conn:
                user = conn.execute(
                    "SELECT role FROM users WHERE username = ?", 
                    (current_user,)
                ).fetchone()
                
            if not user or user['role'] != required_role:
                return jsonify({"error": f"Требуется роль {required_role}"}), 403
            return f(*args, **kwargs)
        return wrapped
    return decorator

# Маршруты API
@app.route('/api/auth/login', methods=['POST'])
def login():
    """Аутентификация пользователя"""
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if not username or not password:
        return jsonify({"error": "Не указаны имя пользователя или пароль"}), 400
    
    with get_db_connection() as conn:
        user = conn.execute(
            "SELECT username, password_hash, role, full_name, is_active FROM users WHERE username = ?", 
            (username,)
        ).fetchone()
    
    if not user or not check_password_hash(user['password_hash'], password):
        return jsonify({"error": "Неверные учетные данные"}), 401
    
    if not user['is_active']:
        return jsonify({"error": "Учетная запись деактивирована"}), 403
    
    # Обновляем время последнего входа
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE username = ?", 
            (username,)
        )
        conn.commit()
    
    # Создаем JWT токены
    access_token = create_access_token(identity=username)
    refresh_token = create_refresh_token(identity=username)
    
    log_user_action("login")
    
    return jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {
            "username": user['username'],
            "role": user['role'],
            "full_name": user['full_name']
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
    
    password_hash = generate_password_hash(data['password'])
    
    try:
        with get_db_connection() as conn:
            conn.execute(
                """
                INSERT INTO users 
                (username, password_hash, role, full_name, email) 
                VALUES (?, ?, ?, ?, ?)
                """,
                (data['username'], password_hash, data['role'], 
                 data.get('full_name'), data.get('email'))
            conn.commit()
        
        log_user_action("create user", data['username'])
        return jsonify({"message": "Пользователь успешно создан"}), 201
    
    except sqlite3.IntegrityError:
        return jsonify({"error": "Пользователь с таким именем уже существует"}), 400

@app.route('/api/users', methods=['GET'])
@jwt_required()
def list_users():
    """Получение списка пользователей (с пагинацией)"""
    page = int(request.args.get('page', 1))
    per_page = int(request.args.get('per_page', 10))
    
    with get_db_connection() as conn:
        # Получаем общее количество пользователей
        total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        
        # Получаем пользователей для текущей страницы
        users = conn.execute(
            """
            SELECT username, role, full_name, email, is_active, 
                   strftime('%Y-%m-%d %H:%M:%S', created_at) as created_at,
                   strftime('%Y-%m-%d %H:%M:%S', last_login) as last_login
            FROM users
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            (per_page, (page - 1) * per_page)
        ).fetchall()
    
    users_list = [dict(user) for user in users]
    
    log_user_action("view users list")
    
    return jsonify({
        "users": users_list,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": (total + per_page - 1) // per_page
        }
    })

@app.route('/api/users/<username>', methods=['GET'])
@jwt_required()
def get_user(username):
    """Получение информации о конкретном пользователе"""
    current_user = get_jwt_identity()
    
    # Пользователи могут получать только свою информацию, кроме администраторов
    with get_db_connection() as conn:
        current_user_role = conn.execute(
            "SELECT role FROM users WHERE username = ?", 
            (current_user,)
        ).fetchone()
        
        if current_user_role['role'] != 'Администратор' and current_user != username:
            return jsonify({"error": "Нет доступа"}), 403
        
        user = conn.execute(
            """
            SELECT username, role, full_name, email, is_active,
                   strftime('%Y-%m-%d %H:%M:%S', created_at) as created_at,
                   strftime('%Y-%m-%d %H:%M:%S', last_login) as last_login
            FROM users
            WHERE username = ?
            """,
            (username,)
        ).fetchone()
    
    if not user:
        return jsonify({"error": "Пользователь не найден"}), 404
    
    log_user_action("view user", username)
    
    return jsonify(dict(user))

@app.route('/api/users/<username>', methods=['PUT'])
@jwt_required()
def update_user(username):
    """Обновление информации о пользователе"""
    current_user = get_jwt_identity()
    data = request.get_json()
    
    with get_db_connection() as conn:
        # Проверяем права доступа
        current_user_role = conn.execute(
            "SELECT role FROM users WHERE username = ?", 
            (current_user,)
        ).fetchone()
        
        if current_user_role['role'] != 'Администратор' and current_user != username:
            return jsonify({"error": "Нет доступа"}), 403
        
        # Администраторы могут менять роль, другие пользователи - нет
        if 'role' in data and current_user_role['role'] != 'Администратор':
            return jsonify({"error": "Только администратор может менять роли"}), 403
        
        # Валидация данных
        if errors := validate_user_data(data, is_new_user=False):
            return jsonify({"errors": errors}), 400
        
        # Подготовка данных для обновления
        update_fields = []
        update_values = []
        
        if 'full_name' in data:
            update_fields.append("full_name = ?")
            update_values.append(data['full_name'])
        
        if 'email' in data:
            update_fields.append("email = ?")
            update_values.append(data['email'])
        
        if 'role' in data:
            update_fields.append("role = ?")
            update_values.append(data['role'])
        
        if 'password' in data:
            update_fields.append("password_hash = ?")
            update_values.append(generate_password_hash(data['password']))
        
        if not update_fields:
            return jsonify({"error": "Нет данных для обновления"}), 400
        
        # Выполняем обновление
        update_query = f"UPDATE users SET {', '.join(update_fields)} WHERE username = ?"
        update_values.append(username)
        
        conn.execute(update_query, update_values)
        conn.commit()
    
    log_user_action("update user", username)
    
    return jsonify({"message": "Данные пользователя обновлены"})

@app.route('/api/users/<username>/status', methods=['PUT'])
@jwt_required()
@role_required('Администратор')
def toggle_user_status(username):
    """Активация/деактивация пользователя"""
    current_user = get_jwt_identity()
    
    if current_user == username:
        return jsonify({"error": "Нельзя изменить статус своей учетной записи"}), 400
    
    data = request.get_json()
    if 'is_active' not in data:
        return jsonify({"error": "Не указан статус"}), 400
    
    with get_db_connection() as conn:
        conn.execute(
            "UPDATE users SET is_active = ? WHERE username = ?",
            (bool(data['is_active']), username)
        )
        conn.commit()
    
    action = "activate user" if data['is_active'] else "deactivate user"
    log_user_action(action, username)
    
    return jsonify({"message": f"Статус пользователя {username} обновлен"})

@app.route('/api/users/<username>', methods=['DELETE'])
@jwt_required()
@role_required('Администратор')
def delete_user(username):
    """Удаление пользователя"""
    current_user = get_jwt_identity()
    
    if current_user == username:
        return jsonify({"error": "Нельзя удалить свою учетную запись"}), 400
    
    with get_db_connection() as conn:
        conn.execute("DELETE FROM users WHERE username = ?", (username,))
        conn.commit()
    
    log_user_action("delete user", username)
    
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

if __name__ == '__main__':
    app.run(debug=True)
