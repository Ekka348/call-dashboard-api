from flask import Flask, request, jsonify, redirect, url_for
import json
import os

app = Flask(__name__)

# Загрузка белого списка
def load_whitelist():
    with open('whitelist.json') as f:
        return json.load(f)['users']

# Простая проверка аутентификации
def check_auth(username, password):
    users = load_whitelist()
    return any(user['username'] == username and user['password'] == password for user in users)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if check_auth(username, password):
            # Успешная авторизация
            return redirect('/dashboard.html')
        else:
            # Неверные данные
            return "Неверный логин или пароль", 401
    
    # Показать форму входа
    return '''
        <form method="post">
            <input type="text" name="username" placeholder="Логин" required>
            <input type="password" name="password" placeholder="Пароль" required>
            <button type="submit">Войти</button>
        </form>
    '''

@app.route('/dashboard.html')
def dashboard():
    return app.send_static_file('dashboard.html')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
