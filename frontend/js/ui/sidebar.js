// ===== УПРАВЛЕНИЕ SIDEBAR И ВЫБОРОМ АГЕНТОВ =====

import { DOM_SELECTORS, CSS_CLASSES, agents, agentKeys } from '../config.js';
import { appState } from '../state.js';
import { logSafe } from '../utils/helpers.js';

/**
 * Рендерит список агентов в sidebar (desktop) и mobile tabs
 */
export function renderAgentsUI() {
    const agentsList = document.querySelector(DOM_SELECTORS.agentsList);
    const mobileTabs = document.querySelector(DOM_SELECTORS.mobileTabs);

    if (!agentsList) {
        logSafe('error', '❌ Agents list container не найден');
        return;
    }

    // Desktop версия: checkboxes в sidebar
    agentsList.innerHTML = agentKeys.map(key => `
        <div class="agent-item" data-agent="${key}">
            <input type="checkbox" data-agent="${key}" checked>
            <span class="agent-icon">${agents[key].icon}</span>
            <span class="agent-name">${agents[key].name}</span>
        </div>
    `).join('');

    // Mobile версия: tabs с иконками
    if (mobileTabs) {
        mobileTabs.innerHTML = agentKeys.map(key => `
            <div class="mobile-tab active" data-agent="${key}">
                <span class="mobile-tab-icon">${agents[key].icon}</span>
                <span class="mobile-tab-label">${agents[key].name}</span>
            </div>
        `).join('');
    }

    logSafe('info', '✅ Agents UI rendered');
}

/**
 * Обновляет UI на основе выбранных агентов
 * (синхронизирует checkboxes и mobile tabs со state)
 */
export function updateUISelections() {
    // Desktop checkboxes
    document.querySelectorAll('.agent-item').forEach(item => {
        const key = item.dataset.agent;
        const checkbox = item.querySelector('input');
        const isActive = appState.selectedAgents.has(key);

        item.classList.toggle(CSS_CLASSES.agentActive, isActive);
        checkbox.checked = isActive;
    });

    // Mobile tabs
    document.querySelectorAll('.mobile-tab').forEach(tab => {
        const key = tab.dataset.agent;
        const isActive = appState.selectedAgents.has(key);

        tab.classList.toggle(CSS_CLASSES.mobileTabActive, isActive);
        tab.style.opacity = isActive ? '1' : '0.5';
    });

    logSafe('debug', `📊 Active agents: ${appState.getSelectedAgentsCount()}`);
}

/**
 * Устанавливает event listeners для sidebar
 * (клики на агентов, открытие меню, и т.д.)
 */
export function setupSidebarEvents() {
    // Desktop: клики на agent-item и checkbox
    document.querySelectorAll('.agent-item').forEach(item => {
        item.addEventListener('click', (e) => {
            // Если кликнул на чекбокс, не обрабатываем дважды
            if (e.target.tagName !== 'INPUT') {
                appState.toggleAgent(item.dataset.agent);
                updateUISelections();
            }
        });

        const checkbox = item.querySelector('input');
        if (checkbox) {
            checkbox.addEventListener('change', () => {
                appState.toggleAgent(item.dataset.agent);
                updateUISelections();
            });
        }
    });

    // Mobile: клики на tabs
    document.querySelectorAll('.mobile-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            appState.toggleAgent(tab.dataset.agent);
            updateUISelections();
        });
    });

    logSafe('info', '✅ Sidebar events initialized');
}

/**
 * Открывает sidebar на мобильной версии
 */
export function openSidebar() {
    const sidebar = document.querySelector(DOM_SELECTORS.sidebar);
    const overlay = document.querySelector(DOM_SELECTORS.overlay);

    if (sidebar) {
        sidebar.classList.add(CSS_CLASSES.sidebarOpen);
    }
    if (overlay) {
        overlay.classList.add(CSS_CLASSES.overlayVisible);
    }
}

/**
 * Закрывает sidebar на мобильной версии
 */
export function closeSidebar() {
    const sidebar = document.querySelector(DOM_SELECTORS.sidebar);
    const overlay = document.querySelector(DOM_SELECTORS.overlay);

    if (sidebar) {
        sidebar.classList.remove(CSS_CLASSES.sidebarOpen);
    }
    if (overlay) {
        overlay.classList.remove(CSS_CLASSES.overlayVisible);
    }
}

console.log('✅ Sidebar module loaded');
