// ===== DEBUG MODE =====
// Управление debug режимом и логированием метаданных

import { DOM_SELECTORS, CSS_CLASSES } from '../config.js';
import { appState } from '../state.js';
import { logSafe } from '../utils/helpers.js';

/**
 * Инициализирует debug режим (чекбокс в sidebar)
 */
export function setupDebugMode() {
    const debugCheckbox = document.querySelector(DOM_SELECTORS.debugCheckbox);

    if (debugCheckbox) {
        debugCheckbox.addEventListener('change', () => {
            const enabled = debugCheckbox.checked;
            appState.setDebugMode(enabled);

            // Визуальный индикатор (жёлтая граница контейнера)
            document.body.dataset.debug = enabled ? CSS_CLASSES.debugMode : 'off';

            logSafe('info', `🔧 Debug mode: ${enabled ? 'ON ✅' : 'OFF ❌'}`);

            if (enabled) {
                logSafe('info', '📊 Debug mode enabled. Metadata будет логироваться в console.');
                logSafe('info', '🔍 Смотри: Request ID, latency, token counts для каждого агента.');
            }
        });
    }

    logSafe('info', '✅ Debug mode initialized');
}

/**
 * Логирует debug информацию от сервера (если debug=true в ответе)
 * Выводит: Request ID, токены, latency, finish reason для каждого агента
 */
export function logDebugMetadata(data, requestId) {
    if (!data.debug || !appState.isDebugEnabled()) {
        return;
    }

    console.group(`🔧 DEBUG [${new Date().toISOString()}]`);
    console.log('📌 Request ID:', requestId);

    if (data.user_message_compressed) {
        console.log('📋 User Message Compressed:', data.user_message_compressed);
    }

    console.group('👥 Agents Metadata:');
    if (data.agents && Array.isArray(data.agents)) {
        data.agents.forEach(agent => {
            if (agent.meta) {
                console.group(`${agent.agent.toUpperCase()}`);
                console.log('⏱️  Latency:', `${agent.meta.latency_ms.toFixed(0)}ms`);
                console.log('🪙 Tokens:', {
                    input: agent.meta.tokens_input,
                    output: agent.meta.tokens_output,
                    total: agent.meta.tokens_total
                });
                console.log('🤖 Model:', agent.meta.model);
                console.log('✅ Finish Reason:', agent.meta.finish_reason);
                console.log('📅 Timestamp:', agent.meta.timestamp);

                if (agent.compressed) {
                    console.log('📦 Compressed Output:', agent.compressed);
                }
                console.groupEnd();
            }
        });
    }
    console.groupEnd();
    console.groupEnd();
}

console.log('✅ Debug module loaded');
