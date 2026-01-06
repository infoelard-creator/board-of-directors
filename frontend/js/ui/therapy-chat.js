// ===== THERAPY CHAT RENDERER =====
// Отвечает за отрисовку сообщений от Терапевта в чат
// Отличается стилем и анимацией от обычных агентов

import { DOM_SELECTORS, THERAPY_CONFIG } from '../config.js';
import { logSafe } from '../utils/helpers.js';

/**
 * Добавить сообщение Терапевта в чат
 * @param {string} therapistMessage - Текст вопроса(ов) от Терапевта
 */
export function addTherapistMessage(therapistMessage) {
    try {
        logSafe('addTherapistMessage', {
            messageLen: therapistMessage.length
        });
        
        const chatArea = document.querySelector(DOM_SELECTORS.chatArea);
        if (!chatArea) {
            console.error('Chat area not found');
            return false;
        }
        
        // Создаем контейнер сообщения
        const messageDiv = document.createElement('div');
        messageDiv.className = `message agent ${THERAPY_CONFIG.therapyMessageClass}`;
        messageDiv.dataset.agent = 'therapist';
        
        // Создаем header с иконкой и именем Терапевта
        const headerDiv = document.createElement('div');
        headerDiv.className = 'message-header';
        headerDiv.innerHTML = `
            <span class="agent-icon">${THERAPY_CONFIG.icons.therapist}</span>
            <span class="agent-name">Терапевт</span>
        `;
        
        // Создаем body сообщения
        const bodyDiv = document.createElement('div');
        bodyDiv.className = 'message-body';
        bodyDiv.textContent = therapistMessage;
        
        // Собираем сообщение
        messageDiv.appendChild(headerDiv);
        messageDiv.appendChild(bodyDiv);
        
        // Добавляем в чат с анимацией
        chatArea.appendChild(messageDiv);
        
        // Trigger анимации (fade-in)
        requestAnimationFrame(() => {
            messageDiv.style.opacity = '0';
            messageDiv.style.transform = 'translateY(10px)';
            messageDiv.style.transition = 'opacity 0.3s ease, transform 0.3s ease';
            
            requestAnimationFrame(() => {
                messageDiv.style.opacity = '1';
                messageDiv.style.transform = 'translateY(0)';
            });
        });
        
        // Скроллим вниз
        scrollChatToBottom();
        
        logSafe('addTherapistMessage SUCCESS', { messageLen: therapistMessage.length });
        
        return true;
    } catch (error) {
        logSafe('addTherapistMessage ERROR', { error: error.message });
        return false;
    }
}

/**
 * Скроллить чат вниз
 */
function scrollChatToBottom() {
    const chatArea = document.querySelector(DOM_SELECTORS.chatArea);
    if (chatArea) {
        setTimeout(() => {
            chatArea.scrollTop = chatArea.scrollHeight;
        }, 50);
    }
}

console.log('✅ Therapy Chat Renderer loaded');
