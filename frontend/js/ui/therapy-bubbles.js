// ===== THERAPY BUBBLES RENDERER =====
// Отрисовывает кнопки выбора действия (бабблы) для пользователя
// Показывается между чатом и полем ввода

import { 
    THERAPY_CONFIG, 
    THERAPY_SELECTORS,
    THERAPY_CSS_CLASSES 
} from '../config.js';
import { logSafe } from '../utils/helpers.js';
import { appState } from '../state.js';

/**
 * Инициализировать контейнер для бабблов
 */
export function initBubblesContainer() {
    try {
        logSafe('initBubblesContainer', { action: 'init' });
        
        // Проверяем что контейнер не существует
        let container = document.querySelector(THERAPY_SELECTORS.therapyBubblesContainer);
        if (container) {
            return true;
        }
        
        // Создаем контейнер
        container = document.createElement('div');
        container.id = 'therapyBubblesContainer';
        container.className = `${THERAPY_CONFIG.therapyBubbleContainerClass}`;
        
        // Вставляем в DOM (перед полем ввода)
        const messageInput = document.querySelector('#messageInput');
        if (messageInput && messageInput.parentNode) {
            messageInput.parentNode.insertBefore(container, messageInput);
        }
        
        return true;
    } catch (error) {
        logSafe('initBubblesContainer ERROR', { error: error.message });
        return false;
    }
}

/**
 * Показать бабблы
 * @param {Object} options - Опции отображения бабблов
 * @param {boolean} options.showSendToBoard - Показать кнопку "Отправить"
 * @param {Object} options.bestHypothesis - Лучшая гипотеза (если showSendToBoard=true)
 */
export function showBubbles(options = {}) {
    try {
        const { showSendToBoard = false, bestHypothesis = null } = options;
        
        logSafe('showBubbles', {
            showSendToBoard,
            hasHypothesis: !!bestHypothesis
        });
        
        const container = document.querySelector(THERAPY_SELECTORS.therapyBubblesContainer);
        if (!container) {
            console.error('Bubbles container not found');
            return false;
        }
        
        container.innerHTML = '';
        
        // Кнопка "Отправить на совет" (если есть гипотеза с высокой confidence)
        if (showSendToBoard && bestHypothesis) {
            const sendBtn = createBubbleButton(
                `${THERAPY_CONFIG.icons.sendToBoard} Отправить на совет`,
                'send-to-board',
                () => {
                    const event = new CustomEvent('therapySendToBoard', {
                        detail: { hypothesis: bestHypothesis }
                    });
                    document.dispatchEvent(event);
                    logSafe('sendToBoardClicked', { hypothesisId: bestHypothesis.id });
                }
            );
            container.appendChild(sendBtn);
        }
        
        // Кнопка "Я сформулирую гипотезу сам"
        const formulateBtn = createBubbleButton(
            `${THERAPY_CONFIG.icons.formulate} Я сформулирую гипотезу сам`,
            'formulate-own',
            () => {
                const event = new CustomEvent('therapyFormulateOwn', {
                    detail: {}
                });
                document.dispatchEvent(event);
                logSafe('formulateOwnClicked', {});
            }
        );
        container.appendChild(formulateBtn);
        
        // Кнопка "Продолжить диалог"
        const continueBtn = createBubbleButton(
            `${THERAPY_CONFIG.icons.continue} Продолжить диалог`,
            'continue-dialogue',
            () => {
                const event = new CustomEvent('therapyContinueDialogue', {
                    detail: {}
                });
                document.dispatchEvent(event);
                logSafe('continueDialogueClicked', {});
                hideBubbles(); // Скроем бабблы, пользователь продолжает писать
            }
        );
        container.appendChild(continueBtn);
        
        // Показываем контейнер
        container.style.display = 'flex';
        
        logSafe('showBubbles SUCCESS', {
            bubblesCount: container.children.length
        });
        
        return true;
    } catch (error) {
        logSafe('showBubbles ERROR', { error: error.message });
        return false;
    }
}

/**
 * Скрыть бабблы
 */
export function hideBubbles() {
    const container = document.querySelector(THERAPY_SELECTORS.therapyBubblesContainer);
    if (container) {
        container.style.display = 'none';
        logSafe('hideBubbles', { action: 'hidden' });
    }
}

/**
 * Создать одну кнопку-баббл
 * @param {string} text - Текст кнопки
 * @param {string} className - CSS класс
 * @param {Function} onClick - Callback при клике
 */
function createBubbleButton(text, className, onClick) {
    const btn = document.createElement('button');
    btn.className = `therapy-bubble ${className}`;
    btn.textContent = text;
    btn.addEventListener('click', onClick);
    
    return btn;
}

/**
 * Обновить состояние бабблов (показать/скрыть "Отправить")
 * Вызывается когда обновились hypotheses
 */
export function updateBubblesState() {
    const bestHyp = appState.getBestHypothesis();
    const confidence = bestHyp?.confidence || 0;
    const showSendToBoard = confidence >= THERAPY_CONFIG.confidenceReadyForBoard;
    
    logSafe('updateBubblesState', {
        bestConfidence: confidence,
        showSendToBoard: showSendToBoard
    });
    
    // Обновляем UI
    if (showSendToBoard) {
        showBubbles({
            showSendToBoard: true,
            bestHypothesis: bestHyp
        });
    } else {
        showBubbles({
            showSendToBoard: false
        });
    }
}

console.log('✅ Therapy Bubbles Renderer loaded');
