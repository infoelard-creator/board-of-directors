// ===== АУТЕНТИФИКАЦИЯ / СЕССИЯ ДЛЯ BOARD.AI =====

import { appState } from '../state.js';
import { generateUserId, logSafe } from './helpers.js';

/**
 * Инициализирует сессию пользователя:
 * - пробует восстановить токен из localStorage
 * - если нет — запрашивает реальный JWT от /api/login
 */
export async function authenticateUser() {
    // 🧹 Удаляем старые mock-токены если они есть
    try {
        const oldToken = localStorage.getItem('authToken');
        if (oldToken && oldToken.startsWith('mock_token_')) {
            logSafe('warn', '🧹 Removing legacy mock_token from localStorage');
            localStorage.removeItem('authToken');
        }
    } catch (e) {
        logSafe('warn', 'Could not clean legacy token', e);
    }

    const restored = appState.restoreAuthToken();
    if (restored) {
        logSafe('info', '✅ Сессия восстановлена из localStorage');
        return;
    }

    await getNewToken();
}

/**
 * Получает новый JWT токен от /api/login
 * Используется при первой авторизации и при рефреше
 */
async function getNewToken() {
    try {
        const userId = generateUserId();
        
        logSafe('info', `📤 Запрашиваем JWT для ${userId}...`);
        
        const response = await fetch('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: userId })
        });

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        const token = data.access_token;

        if (!token) {
            throw new Error('❌ Сервер не вернул access_token');
        }

        appState.setAuthToken(token);
        logSafe('info', `✅ Авторизация успешна для ${userId}`);
        return token;

    } catch (err) {
        logSafe('error', '❌ Не удалось авторизоваться', err.message);
        
        const chatArea = document.querySelector('#chatArea');
        if (chatArea) {
            chatArea.innerHTML = `<div style="color: #e74c3c; padding: 20px; text-align: center; font-size: 16px;">
                <strong>❌ Ошибка авторизации</strong><br>
                ${err.message}<br><br>
                <small>Проверь, что бэкенд запущен на http://localhost:8000</small>
            </div>`;
        }
        
        throw err;
    }
}

/**
 * Рефрешит токен при истечении или 401 ошибке
 * Используется в api.js при перехвате 401
 */
export async function refreshAuthToken() {
    logSafe('warn', '🔄 Токен истёк или невалиден, запрашиваем новый...');
    return await getNewToken();
}

/**
 * Возвращает текущий authToken
 */
export function getAuthToken() {
    return appState.getAuthToken();
}

/**
 * Хард-ресет сессии
 */
export function resetAuthSession() {
    try {
        localStorage.removeItem('authToken');
    } catch (e) {
        logSafe('warn', 'Не удалось удалить токен из localStorage', e);
    }
    appState.setAuthToken(null);
    appState.resetAll();
    logSafe('info', '�� Сессия сброшена');
}
