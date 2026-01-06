// ===== THERAPY API CLIENT =====
// Отвечает за запросы к /api/therapy endpoint

import { API_ENDPOINT, RATE_LIMIT_THERAPY_CHAT } from './config.js';
import { logSafe } from './utils/helpers.js';

/**
 * Отправить сообщение терапевту
 * @param {string|null} sessionId - ID сессии терапии (null для новой)
 * @param {string} userMessage - Сообщение пользователя
 * @param {string} authToken - JWT токен для аутентификации
 * @returns {Promise<Object>} Ответ от терапевта с insights и hypotheses
 */
export async function sendTherapyMessage(sessionId, userMessage, authToken) {
    try {
        logSafe('sendTherapyMessage', {
            sessionId: sessionId || 'NEW',
            messageLen: userMessage.length,
        });

        const payload = {
            session_id: sessionId,
            message: userMessage,
        };

        const response = await fetch(`${API_ENDPOINT}/therapy`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${authToken}`,
            },
            body: JSON.stringify(payload),
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(
                `Ошибка /api/therapy: ${response.status} ${response.statusText}. ${
                    errorData.detail || ''
                }`
            );
        }

        const data = await response.json();

        logSafe('sendTherapyMessage SUCCESS', {
            sessionId: data.session_id,
            insightsCount: data.key_insights?.length || 0,
            hypothesesCount: data.hypotheses?.length || 0,
            readyForBoard: data.ready_for_board,
        });

        return data;
    } catch (error) {
        logSafe('sendTherapyMessage ERROR', {
            error: error.message,
            sessionId: sessionId || 'NEW',
        });
        throw error;
    }
}
