import hashlib
import secrets

def hash_password(password):
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 100000)
    return f"{salt}${dk.hex()}"

password = input("Введите пароль: ")
hashed = hash_password(password)
print(f"Хэш пароля: {hashed}")
