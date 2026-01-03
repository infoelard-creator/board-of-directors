// ===== АУТЕНТИФИКАЦИЯ / СЕССИЯ ДЛЯ BOARD.AI =====
// Логика вокруг authToken и userId — то, что раньше было authenticateUser / loginUser

import { appState } from '../state.js';
import { generateUserId, logSafe } from './helpers.js';

/**
 * Инициализирует сессию пользователя:
 * - пробует восстановить токен из localStorage
 * - если нет — запрашивает реальный JWT от /api/login
 */
export async function authenticateUser() {
    const restored = appState.restoreAuthToken();
    if (restored) {
        logSafe('info', '✅ Сессия восстановлена из localStorage');
        return;
    }

    try {
        const userId = generateUserId();
        
        logSafe('info', `📤 Запрашиваем JWT для ${userId}...`);
        
        // Запрашиваем реальный JWT от бэкенда
        const response = await fetch('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: userId })
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        const token = data.access_token; // Достаём реальный JWT

        if (!token) {
            throw new Error('❌ Сервер не вернул access_token');
        }

        appState.setAuthToken(token);
        logSafe('info', `✅ Авторизация успешна для ${userId}`);

    } catch (err) {
        logSafe('error', '❌ Не удалось авторизоваться', err.message);
        
        // Показываем ошибку в UI
        const chatArea = document.querySelector('#chatArea');
        if (chatArea) {
            chatArea.innerHTML = `<div style="color: #e74c3c; padding: 20px; text-align: center; font-size: 16px;">
                <strong>❌ Ошибка авторизации</strong><br>
                ${err.message}<br><br>
                <small>Проверь, что бэкенд запущен на http://localhost:8000</small>
            </div>`;
        }
        
        throw err; // Пробросим ошибку дальше, чтобы app.js смог её обработать
    }
}

/**
 * Возвращает текущий authToken
 */
export function getAuthToken() {
    return appState.getAuthToken();
}

/**
 * Хард-ресет сессии (если когда-нибудь понадобится)
 */
export function resetAuthSession() {
    try {
        localStorage.removeItem('authToken');
    } catch (e) {
        logSafe('warn', 'Не удалось удалить токен из localStorage', e);
    }
    appState.setAuthToken(null);
    appState.resetAll();
    logSafe('info', '👋 Сессия сброшена');
}
