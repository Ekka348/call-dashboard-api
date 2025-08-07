class AuthService {
  static AUTH_KEY = 'dashboard_auth_v2';
  
  static async login(username, password) {
    const response = await fetch('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    
    if (!response.ok) {
      throw new Error('Ошибка авторизации');
    }
    
    const data = await response.json();
    if (data.status === "success") {
      localStorage.setItem(this.AUTH_KEY, JSON.stringify(data.user));
      return data.user;
    }
    throw new Error(data.message || 'Неверные учетные данные');
  }

  static logout() {
    localStorage.removeItem(this.AUTH_KEY);
  }

  static getCurrentUser() {
    const userData = localStorage.getItem(this.AUTH_KEY);
    return userData ? JSON.parse(userData) : null;
  }

  static isAuthenticated() {
    return !!this.getCurrentUser();
  }
}

// Экспорт для использования в других файлах
if (typeof module !== 'undefined' && module.exports) {
  module.exports = AuthService; // Для Node.js
} else {
  window.AuthService = AuthService; // Для браузера
}
