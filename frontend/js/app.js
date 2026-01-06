// ===== ГЛАВНОЕ ПРИЛОЖЕНИЕ BOARD.AI =====
// Инициализация, главные event handlers (sendMessage, handleSummaryRequest)

import { agentKeys } from './config.js';
import { appState } from './state.js';
import { authenticateUser } from './utils/auth.js';
import { logSafe } from './utils/helpers.js';
import { renderAgentsUI, setupSidebarEvents, updateUISelections } from './ui/sidebar.js';
import { setupMobileNav, setupResponsiveListener } from './ui/mobile.js';
import { setupDebugMode, logDebugMetadata } from './ui/debug.js';
import {
    setupMessageInput,
    addMessage,
    addSkeleton,
    removeSkeleton,
    clearInput,
    setSendButtonDisabled,
    setSummaryButtonVisible
} from './ui/renderer.js';
import { sendBoardRequest } from './api.js';
import { initTherapySession, transitionToBoard, updateReadyForBoardFlag } from './therapy-mode.js';
import { sendTherapyMessage } from './therapy-api.js';
import { addTherapistMessage } from './ui/therapy-chat.js';
import { initTherapyPanel, updateInsightsList, updateHypothesesList } from './ui/therapy-panel.js';
import { initBubblesContainer, showBubbles, updateBubblesState } from './ui/therapy-bubbles.js';

// ===== ИНИЦИАЛИЗАЦИЯ =====

async function init() {
    logSafe('info', '🚀 Initializing Board.AI...');

    // 1. Auth: восстанавливаем токен или создаём новый
    await authenticateUser();

    // 2. UI Setup: рендеруем агентов, слушаем события
    renderAgentsUI();
    setupSidebarEvents();
    setupMobileNav();
    setupResponsiveListener();
    setupDebugMode();
    setupMessageInput();

    // 5. Therapy Setup: инициализируем панель и бабблы
    initTherapyPanel();
    initBubblesContainer();
    setupTherapyEventListeners();
    setupSendButtonHandlers();

    // 3. Default: выбираем всех агентов по умолчанию
    agentKeys.forEach(key => appState.selectAgent(key));
    updateUISelections();

    // 4. Готово!
    logSafe('info', '✅ Board.AI инициализирован');
    logSafe('info', `📊 Selected ${appState.getSelectedAgentsCount()} agents`);
}

// ===== SEND BUTTON HANDLERS =====

// ===== THERAPY EVENT LISTENERS =====

function setupTherapyEventListeners() {
    document.addEventListener('therapySendToBoard', async (e) => {
        const hypothesis = e.detail.hypothesis;
        logSafe('therapySendToBoard', { hypothesisId: hypothesis.id });
        if (transitionToBoard(hypothesis)) {
            appState.setTherapyMode(false);
            const messageInput = document.querySelector('#messageInput');
            if (messageInput) {
                messageInput.value = hypothesis.hypothesis_text;
                messageInput.focus();
            }
        }
    });

    document.addEventListener('therapyFormulateOwn', (e) => {
        logSafe('therapyFormulateOwn', {});
        appState.setTherapyMode(false);
        const messageInput = document.querySelector('#messageInput');
        if (messageInput) {
            messageInput.value = '';
            messageInput.focus();
        }
    });

    document.addEventListener('therapyContinueDialogue', (e) => {
        logSafe('therapyContinueDialogue', {});
        const messageInput = document.querySelector('#messageInput');
        if (messageInput) { messageInput.focus(); }
    });

    document.addEventListener('therapyInsightDelete', async (e) => {
        const insightId = e.detail.insightId;
        
        try {
            // 1. DELETE на сервер
            const authToken = appState.getAuthToken();
            const response = await fetch(`/api/therapy/insights/${insightId}`, {
                method: 'DELETE',
                headers: {
                    'Authorization': `Bearer ${authToken}`,
                    'Content-Type': 'application/json'
                }
            });
            
            if (!response.ok) {
                throw new Error(`Ошибка сервера: ${response.status}`);
            }
            
            // 2. Удаляем из state только после успеха
            appState.removeTherapyInsightById(insightId);
            updateInsightsList(appState.getTherapyInsights());
            
            logSafe('therapyInsightDeleted', {
                insightId: insightId,
                remainingInsights: appState.getTherapyInsightsCount()
            });
            
        } catch (error) {
            logSafe('error', 'Failed to delete insight', error.message);
            addMessage(`❌ Ошибка удаления insight: ${error.message}`, 'agent', 'system');
        }
    });
}


function setupSendButtonHandlers() {
    const sendBtn = document.querySelector('#sendBtn');
    const summaryBtn = document.querySelector('#summaryBtn');
    const messageInput = document.querySelector('#messageInput');

    if (sendBtn) {
        sendBtn.addEventListener('click', handleSendMessage);
    }

    if (messageInput) {
        messageInput.addEventListener('send', handleSendMessage);
    }

    if (summaryBtn) {
        summaryBtn.addEventListener('click', handleSummaryRequest);
    }

/**
 * Отправляет сообщение пользователя в режиме Therapy или Board
 * В режиме Therapy: отправляет на /api/therapy
 * В режиме Board: отправляет на /api/board
 */
async function handleSendMessage() {
    const messageInput = document.querySelector('#messageInput');
    const text = messageInput.value.trim();

    if (!text || appState.isCurrentlyLoading()) {
        return;
    }

    const inTherapyMode = appState.isTherapyMode();

    addMessage(text, 'user');
    clearInput();
    setSendButtonDisabled(true);
    appState.setLoading(true);
    appState.setSummaryShown(false);

    const skeleton = addSkeleton();

    try {
        if (inTherapyMode) {
            // ===== РЕЖИМ THERAPY =====
            const sessionId = appState.getTherapySessionId();
            const authToken = appState.getAuthToken();
            const response = await sendTherapyMessage(sessionId, text, authToken);

            // VALIDATION: Проверяем что сервер вернул session_id
            if (!response.session_id) {
                throw new Error('❌ Ошибка сервера: session_id не вернулся');
            }

            // Если это новая сессия — сохраняем ID
            if (!sessionId) {
                appState.setTherapySessionId(response.session_id);
            }

            removeSkeleton(skeleton);

            if (response.therapist_message) {
                addTherapistMessage(response.therapist_message);
            }

            if (response.key_insights) {
                appState.setTherapyInsights(response.key_insights);
                updateInsightsList(response.key_insights);
            }

            if (response.hypotheses) {
                appState.setTherapyHypotheses(response.hypotheses);
                updateHypothesesList(response.hypotheses);
            }

            updateReadyForBoardFlag();
            updateBubblesState();

        } else {
            // ===== РЕЖИМ BOARD =====
            if (appState.getSelectedAgentsCount() === 0) {
                removeSkeleton(skeleton);
                addMessage('❌ Пожалуйста, выберите хотя бы одного агента', 'agent', 'system');
                appState.setLoading(false);
                setSendButtonDisabled(false);
                return;
            }

            const { data, requestId } = await sendBoardRequest(text, 'initial');

            if (data.debug === true) {
                logDebugMetadata(data, requestId);
            }

            removeSkeleton(skeleton);

            if (data.agents.length === 0) {
                throw new Error('Сервер вернул пустой ответ');
            }

            data.agents.forEach(agentReply => {
                if (agentReply.agent && agentReply.text) {
                    addMessage(agentReply.text, 'agent', agentReply.agent);
                    if (agentReply.agent === 'summary') {
                        appState.setSummaryShown(true);
                    }
                }
            });

            setSummaryButtonVisible(!appState.isSummaryShown());
        }

        appState.setLoading(false);
        setSendButtonDisabled(false);

    } catch (err) {
        logSafe('error', '❌ Send message error:', err.message);
        removeSkeleton(skeleton);

        let userMessage = '❌ Ошибка: не удалось получить ответ';
        if (err.message.includes('NetworkError') || err.message.includes('Failed to fetch')) {
            userMessage = '❌ Проблема с сетью. Проверьте подключение.';
        } else if (err.message.includes('timeout')) {
            userMessage = '❌ Запрос истёк. Сервер не ответил вовремя.';
        } else if (err.message) {
            userMessage = `❌ ${err.message}`;
        }

        addMessage(userMessage, 'agent', 'system');
        appState.setLoading(false);
        setSendButtonDisabled(false);
    }
}
    const text = messageInput.value.trim();

    if (!text || appState.isCurrentlyLoading()) {
        return;
    }

    // Добавляем сообщение в чат
    addMessage(text, 'user');
    clearInput();
    setSendButtonDisabled(true);
    appState.setLoading(true);
    appState.setSummaryShown(false);

    // Показываем loader
    const skeleton = addSkeleton();

    try {
        // Проверяем, выбран ли хотя бы один агент
        if (appState.getSelectedAgentsCount() === 0) {
            removeSkeleton(skeleton);
            addMessage('❌ Пожалуйста, выберите хотя бы одного агента', 'agent', 'system');
            appState.setLoading(false);
            setSendButtonDisabled(false);
            return;
        }

        // Отправляем запрос
        const { data, requestId } = await sendBoardRequest(text, 'initial');

        // Обрабатываем debug информацию если нужна
        if (data.debug === true) {
            logDebugMetadata(data, requestId);
        }

        // Удаляем loader и рендерим ответы
        removeSkeleton(skeleton);

        if (data.agents.length === 0) {
            throw new Error('Сервер вернул пустой ответ');
        }

        // Рендерим сообщение от каждого агента
        data.agents.forEach(agentReply => {
            if (agentReply.agent && agentReply.text) {
                addMessage(agentReply.text, 'agent', agentReply.agent);

                if (agentReply.agent === 'summary') {
                    appState.setSummaryShown(true);
                }
            }
        });

        // Показываем кнопку "Обновить итоги" если summary не был показан
        setSummaryButtonVisible(!appState.isSummaryShown());

        appState.setLoading(false);
        setSendButtonDisabled(false);

    } catch (err) {
        logSafe('error', '❌ Send message error:', err.message);
        removeSkeleton(skeleton);

        let userMessage = '❌ Ошибка: не удалось получить ответ';

        if (err.message.includes('NetworkError') || err.message.includes('Failed to fetch')) {
            userMessage = '❌ Проблема с сетью. Проверьте подключение.';
        } else if (err.message.includes('timeout')) {
            userMessage = '❌ Запрос истёк. Сервер не ответил вовремя.';
        } else if (err.message.includes('не выбрали')) {
            userMessage = '❌ Пожалуйста, выберите хотя бы одного агента';
        } else if (err.message) {
            userMessage = `❌ ${err.message}`;
        }

        addMessage(userMessage, 'agent', 'system');
        appState.setLoading(false);
        setSendButtonDisabled(false);
    }
}

/**
 * Запрашивает итоги (summary) на основе истории чата
 */
async function handleSummaryRequest() {
    if (appState.isCurrentlyLoading()) {
        return;
    }

    appState.setLoading(true);
    const skeleton = addSkeleton();

    try {
        // Проверяем, есть ли история
        if (appState.getHistoryLength() === 0) {
            removeSkeleton(skeleton);
            addMessage(
                '❌ История пуста. Начните беседу, чтобы получить итоги.',
                'agent',
                'system'
            );
            appState.setLoading(false);
            return;
        }

        // Отправляем запрос на refresh (для итогов)
        const { data, requestId } = await sendBoardRequest('', 'refresh');

        if (!data.agents || !Array.isArray(data.agents)) {
            throw new Error('Неверный формат ответа от сервера');
        }

        // Обрабатываем debug информацию если нужна
        if (data.debug === true) {
            logDebugMetadata(data, requestId);
        }

        // Ищем в ответе блок summary
        const summaryReply = data.agents.find(r => r.agent === 'summary');

        removeSkeleton(skeleton);

        if (summaryReply && summaryReply.text) {
            addMessage(summaryReply.text, 'agent', 'summary');
        } else {
            addMessage('❌ Не удалось получить итоги', 'agent', 'system');
        }

        // Закрываем sidebar и скрываем кнопку summary
        setSummaryButtonVisible(false);
        appState.setLoading(false);

    } catch (err) {
        logSafe('error', '❌ Summary request error:', err.message);
        removeSkeleton(skeleton);

        let userMessage = '❌ Ошибка при пересчёте итогов';
        if (err.message) {
            userMessage = `❌ ${err.message}`;
        }

        addMessage(userMessage, 'agent', 'system');
        appState.setLoading(false);
    }
}

// ===== ЗАПУСК ПРИЛОЖЕНИЯ =====

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}

console.log('✅ App module loaded');
