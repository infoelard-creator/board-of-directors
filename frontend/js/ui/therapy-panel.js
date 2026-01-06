// ===== THERAPY PANEL RENDERER =====
// Отвечает за отрисовку боковой панели с insights и hypotheses
// На десктопе: справа всегда видна
// На мобильном: drawer/modal с кнопкой открытия

import { 
    DOM_SELECTORS, 
    THERAPY_SELECTORS, 
    THERAPY_CONFIG, 
    THERAPY_CSS_CLASSES 
} from '../config.js';
import { logSafe } from '../utils/helpers.js';

/**
 * Инициализировать боковую панель Therapy
 * Создает контейнер для insights и hypotheses
 */
export function initTherapyPanel() {
    try {
        logSafe('initTherapyPanel', { action: 'init' });
        
        // Создаем контейнер панели (если не существует)
        let panel = document.querySelector(THERAPY_SELECTORS.therapyPanel);
        if (panel) {
            logSafe('initTherapyPanel', { message: 'Panel already exists' });
            return true;
        }
        
        // Создаем панель
        panel = document.createElement('div');
        panel.id = 'therapyPanel';
        panel.className = `therapy-panel ${THERAPY_CSS_CLASSES.panelVisible}`;
        panel.innerHTML = `
            <div class="therapy-panel-header">
                <h3>${THERAPY_CONFIG.icons.insights} Key Insights</h3>
                <button id="therapyTogglePanelBtn" class="therapy-toggle-btn" title="Скрыть/показать">×</button>
            </div>
            
            <div class="therapy-panel-content">
                <div id="therapyInsightsList" class="therapy-insights-list"></div>
                
                <div class="therapy-divider"></div>
                
                <div class="therapy-hypotheses-section">
                    <h4>${THERAPY_CONFIG.icons.hypotheses} Hypotheses</h4>
                    <div id="therapyHypothesesList" class="therapy-hypotheses-list"></div>
                </div>
            </div>
        `;
        
        // Добавляем в DOM (после sidebar или перед ним)
        const container = document.querySelector(DOM_SELECTORS.container);
        if (container) {
            container.appendChild(panel);
        }
        
        // Setup events
        setupTherapyPanelEvents();
        
        logSafe('initTherapyPanel SUCCESS', {});
        return true;
    } catch (error) {
        logSafe('initTherapyPanel ERROR', { error: error.message });
        return false;
    }
}

/**
 * Обновить список insights в панели
 * @param {Array} insights - Список insights от терапевта
 */
export function updateInsightsList(insights) {
    try {
        const list = document.querySelector(THERAPY_SELECTORS.therapyInsightsList);
        if (!list) {
            console.error('Insights list container not found');
            return false;
        }
        
        logSafe('updateInsightsList', {
            insightsCount: insights?.length || 0
        });
        
        list.innerHTML = '';
        
        if (!insights || insights.length === 0) {
            list.innerHTML = '<p class="therapy-empty">Нет insights пока...</p>';
            return true;
        }
        
        // Отображаем insights
        insights.forEach((insight, index) => {
            const insightDiv = document.createElement('div');
            insightDiv.className = `${THERAPY_CONFIG.therapyInsightClass}`;
            insightDiv.dataset.insightId = insight.id;
            
            // Confidence indicator
            const confidenceBar = createConfidenceBar(insight.confidence);
            
            insightDiv.innerHTML = `
                <div class="therapy-insight-content">
                    <span class="therapy-insight-text">${escapeHtml(insight.insight_summary)}</span>
                    <button class="therapy-insight-delete-btn" 
                            data-insight-id="${insight.id}" 
                            title="Удалить">✕</button>
                </div>
                ${confidenceBar}
            `;
            
            list.appendChild(insightDiv);
        });
        
        logSafe('updateInsightsList SUCCESS', {
            insightsCount: insights.length
        });
        
        return true;
    } catch (error) {
        logSafe('updateInsightsList ERROR', { error: error.message });
        return false;
    }
}

/**
 * Обновить список hypotheses в панели
 * @param {Array} hypotheses - Список гипотез (будут отсортированы)
 */
export function updateHypothesesList(hypotheses) {
    try {
        const list = document.querySelector(THERAPY_SELECTORS.therapyHypothesesList);
        if (!list) {
            console.error('Hypotheses list container not found');
            return false;
        }
        
        logSafe('updateHypothesesList', {
            hypothesesCount: hypotheses?.length || 0
        });
        
        list.innerHTML = '';
        
        if (!hypotheses || hypotheses.length === 0) {
            list.innerHTML = '<p class="therapy-empty">Гипотезы будут здесь...</p>';
            return true;
        }
        
        // Сортируем по confidence (убывание)
        const sorted = [...hypotheses].sort((a, b) => 
            (b.confidence || 0) - (a.confidence || 0)
        );
        
        // Отображаем гипотезы
        sorted.forEach((hyp, index) => {
            const hypDiv = document.createElement('div');
            hypDiv.className = `${THERAPY_CONFIG.therapyHypothesisClass}`;
            hypDiv.dataset.hypothesisId = hyp.id;
            
            // Confidence indicator
            const confidenceBar = createConfidenceBar(hyp.confidence);
            
            // Truncate long text for display
            const displayText = hyp.hypothesis_text.length > 100
                ? hyp.hypothesis_text.substring(0, 100) + '...'
                : hyp.hypothesis_text;
            
            hypDiv.innerHTML = `
                <div class="therapy-hypothesis-content">
                    <span class="therapy-hypothesis-text">${escapeHtml(displayText)}</span>
                </div>
                ${confidenceBar}
            `;
            
            list.appendChild(hypDiv);
        });
        
        logSafe('updateHypothesesList SUCCESS', {
            hypothesesCount: sorted.length
        });
        
        return true;
    } catch (error) {
        logSafe('updateHypothesesList ERROR', { error: error.message });
        return false;
    }
}

/**
 * Создать визуальный индикатор confidence
 * @param {number} confidence - Значение уверенности (0-100)
 */
function createConfidenceBar(confidence) {
    const percent = Math.min(100, Math.max(0, confidence || 0));
    const color = percent >= 85 ? '#4caf50' : percent >= 60 ? '#ff9800' : '#f44336';
    
    return `
        <div class="therapy-confidence-bar">
            <div class="therapy-confidence-fill" 
                 style="width: ${percent}%; background-color: ${color};">
                <span class="therapy-confidence-text">${percent}%</span>
            </div>
        </div>
    `;
}

/**
 * Setup event listeners для панели
 */
function setupTherapyPanelEvents() {
    // Toggle button
    const toggleBtn = document.querySelector(THERAPY_SELECTORS.therapyToggleBtn);
    if (toggleBtn) {
        toggleBtn.addEventListener('click', () => {
            const panel = document.querySelector(THERAPY_SELECTORS.therapyPanel);
            if (panel) {
                panel.classList.toggle(THERAPY_CSS_CLASSES.panelVisible);
                logSafe('toggleTherapyPanel', { visible: panel.classList.contains(THERAPY_CSS_CLASSES.panelVisible) });
            }
        });
    }
    
    // Delete insight buttons (delegate)
    document.addEventListener('click', (e) => {
        if (e.target.classList.contains('therapy-insight-delete-btn')) {
            const insightId = e.target.dataset.insightId;
            
            // Emit custom event для обработки в app.js
            const event = new CustomEvent('therapyInsightDelete', {
                detail: { insightId }
            });
            document.dispatchEvent(event);
            
            logSafe('insightDeleteClicked', { insightId });
        }
    });
}

/**
 * Escape HTML для безопасного вывода
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

console.log('✅ Therapy Panel Renderer loaded');
