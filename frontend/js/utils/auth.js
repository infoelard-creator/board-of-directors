// ===== АУТЕНТИФИКАЦИЯ / СЕССИЯ ДЛЯ BOARD.AI =====

import { appState } from '../state.js';
import { generateUserId, logSafe } from './helpers.js';

/**
 * Инициализирует сессию пользователя:
 * - СНАЧАЛА проверяет и удаляет старые mock-токены
 * - потом пробует восстановить валидный токен
 * - если нет — запрашивает реальный JWT от /api/login
 */
export async function authenticateUser() {
    logSafe('info', '🔍 [AUTH] authenticateUser() called');
    
    // 🧹 КРИТИЧНО: Удаляем старые mock-токены ДО любого восстановления
    try {
        const oldToken = localStorage.getItem('authToken');
        logSafe('info', `🔍 [AUTH] Token from localStorage: ${oldToken ? oldToken.substring(0, 20) + '...' : 'null'}`);
        
        if (oldToken && oldToken.startsWith('mock_token_')) {
            logSafe('warn', '🧹 [AUTH] REMOVING legacy mock_token from localStorage');
            localStorage.removeItem('authToken');
            logSafe('info', '🧹 [AUTH] ✅ mock_token REMOVED');
        }
    } catch (e) {
        logSafe('warn', '[AUTH] Could not clean legacy token', e);
    }

    // Теперь восстанавливаем (если есть валидный токен)
    const restored = appState.restoreAuthToken();
    logSafe('info', `🔍 [AUTH] restoreAuthToken() returned: ${restored}`);
    
    if (restored) {
        const token = appState.getAuthToken();
        logSafe('info', `✅ [AUTH] Сессия восстановлена: ${token ? token.substring(0, 20) + '...' : 'null'}`);
        return;
    }

    logSafe('info', '🔍 [AUTH] No valid token in localStorage, requesting new JWT...');
    await getNewToken();
}


/**
 * Получает новый JWT токен от /api/login
 * Используется при первой авторизации
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
        const accessToken = data.access_token;
        const refreshToken = data.refresh_token;

        if (!accessToken) {
            throw new Error('❌ Сервер не вернул access_token');
        }

        if (!refreshToken) {
            throw new Error('❌ Сервер не вернул refresh_token');
        }

        // Сохраняем ОБА токена
        appState.setAuthToken(accessToken);
        localStorage.setItem('refreshToken', refreshToken);
        localStorage.setItem('tokenExpiresIn', data.expires_in || 900);

        logSafe('info', `✅ Авторизация успешна для ${userId}`);
        logSafe('info', `🔑 Access token действует ${data.expires_in || 900} сек, refresh_token на 30 дней`);
        
        return accessToken;

    } catch (err) {
        logSafe('error', '❌ Не удалось авторизоваться', err.message);
        
        const chatArea = document.querySelector('#chatArea');
        if (chatArea) {
            chatArea.innerHTML = `<div style="color: #e74c3c; padding: 20px; text-align: center; font-size: 16px;">
                <strong>❌ Ошибка авторизации</strong><br>
                ${err.message}<br><br>
                <small>Проверь, что бэкенд запущен</small>
            </div>`;
        }
        
        throw err;
    }
}

/**
 * НОВОЕ: Рефрешит access_token используя refresh_token
 * Используется в api.js при перехвате 401
 * Сохраняет пользователя и history чата!
 */
export async function refreshAuthToken() {
    logSafe('warn', '🔄 Access token истёк, обновляем через refresh_token...');
    
    const refreshToken = localStorage.getItem('refreshToken');
    
    if (!refreshToken) {
        logSafe('error', '❌ Refresh token не найден в localStorage — требуется новая авторизация');
        throw new Error('Нет refresh_token — требуется переавторизация');
    }
    
    try {
        logSafe('info', '📤 Отправляем refresh_token на /api/refresh...');
        
        const response = await fetch('/api/refresh', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ refresh_token: refreshToken })
        });

        if (!response.ok) {
            if (response.status === 401) {
                logSafe('warn', '❌ Refresh token истёк или невалиден (401) — требуется новая авторизация');
                localStorage.removeItem('refreshToken');
                localStorage.removeItem('authToken');
                throw new Error('Refresh token истёк, требуется новая авторизация');
            }
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        const newAccessToken = data.access_token;

        if (!newAccessToken) {
            throw new Error('❌ Сервер не вернул новый access_token');
        }

        // Обновляем ТОЛЬКО access_token, refresh_token остается прежним
        appState.setAuthToken(newAccessToken);
        localStorage.setItem('tokenExpiresIn', data.expires_in || 900);

        logSafe('info', `✅ Access token обновлен успешно (действует ${data.expires_in || 900} сек)`);
        
        return newAccessToken;

    } catch (err) {
        logSafe('error', '❌ Не удалось обновить access_token', err.message);
        
        // При ошибке refresh — требуем новую авторизацию
        resetAuthSession();
        
        throw err;
    }
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
        localStorage.removeItem('refreshToken');
        localStorage.removeItem('tokenExpiresIn');
    } catch (e) {
        logSafe('warn', 'Не удалось удалить токены из localStorage', e);
    }
    appState.setAuthToken(null);
    appState.resetAll();
    logSafe('info', '🔐 Сессия сброшена');
}
