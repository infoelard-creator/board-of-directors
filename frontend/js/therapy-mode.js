// ===== THERAPY MODE MANAGER =====
// Управляет переключением между режимом Therapy и Board
// Отвечает за инициализацию новой сессии терапии и переход на Board

import { appState } from './state.js';
import { logSafe } from './utils/helpers.js';
import { THERAPY_CONFIG } from './config.js';

/**
 * Инициализировать новую сессию терапии
 * Очищает старое состояние и подготавливает UI для Therapy режима
 */
export function initTherapySession() {
    logSafe('initTherapySession', { action: 'init' });
    
    // Переходим в режим Therapy
    appState.setTherapyMode(true);
    
    // Очищаем старую сессию (если была)
    appState.resetTherapyState();
    
    // Инициализируем новую сессию (session_id = null, будет создан на бэке)
    appState.setTherapySessionId(null);
    
    // Очищаем чат историю Board (если там что-то было)
    appState.clearHistory();
    
    // Отключаем режим Board
    appState.setTherapyMode(true);
    
    logSafe('initTherapySession SUCCESS', {
        mode: 'therapy',
        sessionId: appState.getTherapySessionId()
    });
}

/**
 * Перейти в режим Board с выбранной гипотезой
 * @param {Object} hypothesis - Гипотеза для отправки на Board
 */
export function transitionToBoard(hypothesis) {
    logSafe('transitionToBoard', {
        hypothesisId: hypothesis?.id,
        confidence: hypothesis?.confidence
    });
    
    // Переходим в режим Board
    appState.setTherapyMode(false);
    
    // Сохраняем выбранную гипотезу в chatHistory для Board
    if (hypothesis && hypothesis.hypothesis_text) {
        const hypothesisText = hypothesis.hypothesis_text;
        appState.addToHistory('user', 'board', hypothesisText);
        
        logSafe('transitionToBoard SUCCESS', {
            mode: 'board',
            hypothesisText: hypothesisText.substring(0, 50) + '...'
        });
        
        return true;
    }
    
    logSafe('transitionToBoard ERROR', {
        error: 'No hypothesis provided'
    });
    
    return false;
}

/**
 * Вернуться в режим Therapy (если пользователь отменил переход)
 */
export function backToTherapy() {
    logSafe('backToTherapy', { action: 'back' });
    
    // Очищаем Board историю
    appState.clearHistory();
    
    // Возвращаемся в режим Therapy
    appState.setTherapyMode(true);
    
    logSafe('backToTherapy SUCCESS', {
        mode: 'therapy'
    });
}

/**
 * Проверить готовность гипотез к отправке на Board
 * @returns {boolean} Есть ли гипотеза с confidence >= THRESHOLD
 */
export function isReadyForBoard() {
    const best = appState.getBestHypothesis();
    
    if (!best) return false;
    
    const isReady = (best.confidence || 0) >= THERAPY_CONFIG.confidenceReadyForBoard;
    
    logSafe('isReadyForBoard', {
        bestConfidence: best.confidence,
        threshold: THERAPY_CONFIG.confidenceReadyForBoard,
        isReady: isReady
    });
    
    return isReady;
}

/**
 * Обновить ready_for_board флаг на основе лучшей гипотезы
 */
export function updateReadyForBoardFlag() {
    const ready = isReadyForBoard();
    appState.setTherapyReadyForBoard(ready);
    
    logSafe('updateReadyForBoardFlag', {
        ready: ready,
        hypothesesCount: appState.getTherapyHypothesesCount()
    });
    
    return ready;
}

console.log('✅ Therapy Mode Manager loaded');
