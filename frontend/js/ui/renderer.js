// ===== РЕНДЕРИНГ СООБЩЕНИЙ В ЧАТ =====
// addMessage, addSkeleton, управление input area

import { DOM_SELECTORS, CSS_CLASSES, TIMING, agents } from '../config.js';
import { appState } from '../state.js';
import { parseAgentResponse, extractPercentage, isValidSections } from './parser.js';
import { logSafe } from '../utils/helpers.js';

/**
 * Добавляет сообщение в чат (от пользователя или агента)
 * @param {string} text - текст сообщения
 * @param {'user'|'agent'} sender
 * @param {string|null} agentType - тип агента если sender='agent'
 */
export function addMessage(text, sender = 'user', agentType = null) {
    const chatArea = document.querySelector(DOM_SELECTORS.chatArea);
    if (!chatArea) {
        logSafe('error', '❌ Chat area не найден');
        return;
    }

    const messageEl = document.createElement('div');
    messageEl.className = `${CSS_CLASSES.message} ${sender}`;

    // ===== USER MESSAGE =====
    if (sender === 'user') {
        messageEl.textContent = text;
    }
    // ===== AGENT MESSAGE =====
    else if (sender === 'agent' && agentType) {
        messageEl.classList.add(agentType);

        // Заголовок с иконкой и именем агента
        const header = document.createElement('div');
        header.className = 'message-header';
        const agentInfo = agents[agentType] || { icon: '🤖', name: agentType };
        header.innerHTML = `
            <span class="agent-icon">${agentInfo.icon}</span>
            <span>${agentInfo.name}</span>
        `;
        messageEl.appendChild(header);

        // Основное содержание
        const content = document.createElement('div');
        content.className = 'message-content';

        const sections = parseAgentResponse(text, agentType);

        if (!isValidSections(sections)) {
            // Если парсинг не удался, показываем весь текст как есть
            const textDiv = document.createElement('div');
            textDiv.className = 'section-value';
            textDiv.textContent = text;
            content.appendChild(textDiv);
        } else {
            // Рендерим каждую секцию в зависимости от её типа
            sections.forEach(section => {
                const sectionEl = document.createElement('div');
                sectionEl.className = 'content-section';

                // Label (если есть)
                if (section.label) {
                    const labelEl = document.createElement('div');
                    labelEl.className = 'section-label';
                    labelEl.textContent = section.label;
                    sectionEl.appendChild(labelEl);
                }

                // Value (в зависимости от типа)
                const valueEl = document.createElement('div');
                valueEl.className = 'section-value';

                if (section.type === 'badge' && section.badgeType) {
                    renderBadge(valueEl, section);
                } else if (section.type === 'progress') {
                    renderProgressBar(valueEl, section);
                } else if (section.type === 'currency') {
                    renderCurrency(valueEl, section);
                } else {
                    valueEl.textContent = section.value;
                }

                sectionEl.appendChild(valueEl);
                content.appendChild(sectionEl);
            });
        }

        messageEl.appendChild(content);
    }

    // Удаляем empty-state если это первое сообщение
    const emptyState = chatArea.querySelector('.empty-state');
    if (emptyState) {
        emptyState.remove();
    }

    chatArea.appendChild(messageEl);
    scrollToBottom(chatArea);

    // Сохраняем в историю состояния
    appState.addToHistory(sender, agentType, text);
}

/**
 * Рендерит badge элемент
 */
function renderBadge(container, section) {
    const badge = document.createElement('span');
    badge.className = `badge ${section.badgeType}`;
    badge.textContent = section.value;
    badge.setAttribute('role', 'status');
    badge.setAttribute('aria-label', `${section.label || 'Статус'}: ${section.value}`);
    container.appendChild(badge);
}

/**
 * Рендерит progress bar с анимацией
 */
function renderProgressBar(container, section) {
    const percent = extractPercentage(section.value);

    const progressBar = document.createElement('div');
    progressBar.className = 'confidence-bar';
    progressBar.setAttribute('role', 'progressbar');
    progressBar.setAttribute('aria-valuenow', percent);
    progressBar.setAttribute('aria-valuemin', '0');
    progressBar.setAttribute('aria-valuemax', '100');
    progressBar.setAttribute('aria-label', `Уверенность: ${section.value}`);

    const fill = document.createElement('div');
    fill.className = 'confidence-fill';
    fill.style.width = '0%';

    const percentText = document.createElement('div');
    percentText.className = 'confidence-text';
    percentText.textContent = section.value;

    progressBar.appendChild(percentText);
    progressBar.appendChild(fill);
    container.appendChild(progressBar);

    // Анимируем наполнение прогресс-бара
    setTimeout(() => {
        fill.style.width = `${percent}%`;
    }, TIMING.progressBarDelay);
}

/**
 * Рендерит валютное значение
 */
function renderCurrency(container, section) {
    const currencyEl = document.createElement('span');
    currencyEl.className = 'currency-value';
    currencyEl.style.fontWeight = '600';
    currencyEl.style.color = '#667eea';
    currencyEl.textContent = section.value;
    currencyEl.setAttribute('aria-label', `Сумма: ${section.value}`);
    container.appendChild(currencyEl);
}

/**
 * Скролит чат к низу
 */
function scrollToBottom(chatArea) {
    if (!chatArea) return;
    setTimeout(() => {
        chatArea.scrollTop = chatArea.scrollHeight;
    }, TIMING.scrollDelay);
}

/**
 * Добавляет skeleton loader (анимированный placeholder при загрузке)
 * @returns {HTMLElement} элемент скелетона
 */
export function addSkeleton() {
    const chatArea = document.querySelector(DOM_SELECTORS.chatArea);
    if (!chatArea) {
        logSafe('error', '❌ Chat area не найден');
        return null;
    }

    const skeleton = document.createElement('div');
    skeleton.className = `${CSS_CLASSES.message} agent ${CSS_CLASSES.skeleton}`;
    skeleton.innerHTML = `
        <div class="skeleton">
            <div class="skeleton-line" style="width: 60%;"></div>
            <div class="skeleton-line" style="width: 90%;"></div>
            <div class="skeleton-line" style="width: 75%;"></div>
        </div>
    `;

    chatArea.appendChild(skeleton);
    scrollToBottom(chatArea);

    return skeleton;
}

/**
 * Удаляет skeleton элемент
 */
export function removeSkeleton(skeletonEl) {
    if (skeletonEl && skeletonEl.parentNode) {
        skeletonEl.remove();
    }
}

// ===== INPUT AREA SETUP =====

/**
 * Инициализирует textarea: auto-resize, отправка сообщений
 */
export function setupMessageInput() {
    const messageInput = document.querySelector(DOM_SELECTORS.messageInput);
    const sendBtn = document.querySelector(DOM_SELECTORS.sendBtn);

    if (!messageInput) {
        logSafe('error', '❌ Message input не найден');
        return;
    }

    // Auto-resize textarea при вводе
    messageInput.addEventListener('input', (e) => {
        e.target.style.height = 'auto';
        const newHeight = Math.min(e.target.scrollHeight, TIMING.inputAutoheightMax);
        e.target.style.height = newHeight + 'px';

        // Enable/disable кнопку отправки в зависимости от наличия текста
        if (sendBtn) {
            sendBtn.disabled = !e.target.value.trim();
        }
    });

    // Отправка на Enter (но не на Shift+Enter)
    messageInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            // sendMessage будет подключена в app.js
            messageInput.dispatchEvent(new CustomEvent('send'));
        }
    });

    logSafe('info', '✅ Message input initialized');
}

/**
 * Очищает поле ввода
 */
export function clearInput() {
    const messageInput = document.querySelector(DOM_SELECTORS.messageInput);
    if (messageInput) {
        messageInput.value = '';
        messageInput.style.height = 'auto';
    }
}

/**
 * Включает/отключает кнопку отправки
 */
export function setSendButtonDisabled(disabled) {
    const sendBtn = document.querySelector(DOM_SELECTORS.sendBtn);
    if (sendBtn) {
        sendBtn.disabled = disabled;
    }
}

/**
 * Показывает/скрывает кнопку обновления итогов
 */
export function setSummaryButtonVisible(visible) {
    const summaryBtn = document.querySelector(DOM_SELECTORS.summaryBtn);
    if (summaryBtn) {
        summaryBtn.style.display = visible ? 'block' : 'none';
    }
}

console.log('✅ Renderer module loaded');
