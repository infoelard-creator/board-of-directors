// ===== УПРАВЛЕНИЕ СЛОЯМИ (LAYERS) =====
// Переключение между режимом Therapy (Слой 1) и Board (Слой 2)

import { DOM_SELECTORS, THERAPY_SELECTORS } from '../config.js';
import { appState } from '../state.js';
import { logSafe } from '../utils/helpers.js';

/**
 * Инициализировать управление слоями
 */
export function initLayerManager() {
    logSafe('info', '🎯 Initializing Layer Manager...');
    
    setupLayerEvents();
    updateLayerUI();
    
    logSafe('info', '✅ Layer Manager initialized');
}

/**
 * Установить event listeners на слои
 */
function setupLayerEvents() {
    const sidebarLayers = document.querySelector(DOM_SELECTORS.sidebarLayers);
    
    if (!sidebarLayers) {
        logSafe('error', '❌ Sidebar layers container не найден');
        return;
    }
    
    sidebarLayers.querySelectorAll('.layer-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const layer = item.dataset.layer;
            handleLayerSwitch(layer);
        });
    });
    
    logSafe('info', '✅ Layer events setup complete');
}

/**
 * Обработать переключение слоя
 * @param {string} layer - 'therapy' или 'board'
 */
function handleLayerSwitch(layer) {
    logSafe('info', `🔄 Switching to layer: ${layer}`);
    
    if (layer === 'therapy') {
        appState.setTherapyMode(true);
    } else if (layer === 'board') {
        appState.setTherapyMode(false);
    }
    
    updateLayerUI();
    updateTherapyPanelVisibility();
    
    logSafe('info', `✅ Layer switched to: ${layer}`);
}

/**
 * Обновить UI слоёв (подсветить активный)
 */
function updateLayerUI() {
    const sidebarLayers = document.querySelector(DOM_SELECTORS.sidebarLayers);
    const isTherapyMode = appState.isTherapyMode();
    
    if (!sidebarLayers) return;
    
    sidebarLayers.querySelectorAll('.layer-item').forEach(item => {
        const layer = item.dataset.layer;
        const isActive = (layer === 'therapy' && isTherapyMode) || 
                        (layer === 'board' && !isTherapyMode);
        
        item.classList.toggle('active', isActive);
    });
}

/**
 * Управлять видимостью панели Therapy
 * Панель видна только в режиме Therapy
 */
function updateTherapyPanelVisibility() {
    const therapyPanel = document.querySelector(THERAPY_SELECTORS.therapyPanel);
    const isTherapyMode = appState.isTherapyMode();
    
    if (!therapyPanel) {
        logSafe('debug', '⚠️ Therapy panel not found');
        return;
    }
    
    if (isTherapyMode) {
        therapyPanel.classList.add('visible');
        logSafe('debug', '👁️ Therapy panel shown');
    } else {
        therapyPanel.classList.remove('visible');
        logSafe('debug', '👁️ Therapy panel hidden');
    }
}

/**
 * Экспортируемая функция для обновления UI при изменении состояния
 */
export function updateLayerUIFromState() {
    updateLayerUI();
    updateTherapyPanelVisibility();
}

console.log('✅ Layer Manager module loaded');
