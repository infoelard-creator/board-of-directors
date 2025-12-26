// ===== API КОММУНИКАЦИЯ С СЕРВЕРОМ =====
// sendBoardRequest для основного запроса и summary запроса

import { API_CONFIG } from './config.js';
import { appState } from './state.js';
import { generateRequestId, logSafe, calculateResponseTime } from './utils/helpers.js';

/**
 * Отправляет запрос на /api/board
 * Используется для основного чата (mode="initial") и итогов (mode="refresh")
 *
 * @param {string} message - сообщение от пользователя (для mode="initial")
 * @param {string} mode - "initial" или "refresh" (для итогов)
 * @returns {Promise<{data, requestId}>}
 * @throws {Error}
 */
export async function sendBoardRequest(message, mode = 'initial') {
    const authToken = appState.getAuthToken();

    if (!authToken) {
        throw new Error('❌ Не авторизован');
    }

    if (appState.getSelectedAgentsCount() === 0) {
        throw new Error('❌ Пожалуйста, выберите хотя бы одного агента');
    }

    const requestId = generateRequestId(mode === 'refresh' ? 'summary' : 'req');

    const payload = {
        message,
        active_agents: appState.getSelectedAgents(),
        history: appState.getHistory(),
        mode,
        debug: appState.isDebugEnabled(),
        request_id: requestId
    };

    logSafe('info', `📤 Sending request [${requestId}]`, {
        agents: payload.active_agents,
        mode: mode,
        messageLength: message.length
    });

    try {
        // Promise.race для timeout (30 сек по умолчанию)
        const response = await Promise.race([
            fetch(API_CONFIG.endpoint, {
                method: 'POST',
                headers: {
                    ...API_CONFIG.headers,
                    'Authorization': `Bearer ${authToken}`,
                    'X-Request-ID': requestId
                },
                body: JSON.stringify(payload)
            }),
            new Promise((_, reject) =>
                setTimeout(
                    () => reject(new Error('Request timeout')),
                    API_CONFIG.timeout
                )
            )
        ]);

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            const errorMsg = errorData.detail || `API ошибка ${response.status}`;
            throw new Error(errorMsg);
        }

        const data = await response.json();

        if (!data.agents || !Array.isArray(data.agents)) {
            throw new Error('❌ Неверный формат ответа от сервера');
        }

        const responseTime = calculateResponseTime(requestId);
        logSafe('info', `📥 Response received [${requestId}]`, {
            agentCount: data.agents.length,
            responseTime: `${responseTime}ms`,
            hasDebugData: !!data.debug
        });

        return { data, requestId };

    } catch (err) {
        logSafe('error', `❌ Request failed [${requestId}]`, err.message);
        throw err;
    }
}

console.log('✅ API module loaded');
