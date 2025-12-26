// ===== АУТЕНТИФИКАЦИЯ / СЕССИЯ ДЛЯ BOARD.AI =====
// Логика вокруг authToken и userId — то, что раньше было authenticateUser / loginUser

import { appState } from '../state.js';
import { generateUserId, logSafe } from './helpers.js';

/**
 * Инициализирует сессию пользователя:
 * - пробует восстановить токен из localStorage
 * - если нет — создаёт mock_token_<userId>
 */
export function authenticateUser() {
    const restored = appState.restoreAuthToken();
    if (restored) {
        logSafe('info', '✅ Сессия восстановлена из localStorage');
        return;
    }

    const userId = generateUserId();
    const token = `mock_token_${userId}`;

    appState.setAuthToken(token);
    logSafe('info', `✅ Новая сессия создана: ${userId}`);
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