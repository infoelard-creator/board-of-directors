// ===== THERAPY PANEL SWIPE & TOGGLE MANAGER =====
// Управляет открытием/закрытием панели терапии на мобилке (свайпы)
// и кнопкой-закладкой на десктопе

import { THERAPY_SELECTORS, THERAPY_CSS_CLASSES } from '../config.js';
import { logSafe } from '../utils/helpers.js';

let touchStartX = 0;
let touchEndX = 0;
const SWIPE_THRESHOLD = 50; // минимальная дистанция для свайпа (px)

/**
 * Инициализировать управление свайпами и toggle кнопкой
 */
export function initTherapySwipeAndToggle() {
    try {
        logSafe('initTherapySwipeAndToggle', { action: 'init' });
        
        // Создаем кнопку-закладку для десктопа
        createDesktopToggleButton();
        
        // Настраиваем touch события для мобилки
        setupSwipeGestures();
        
        // Настраиваем клики на toggle кнопку
        setupToggleButtonEvents();
        
        logSafe('initTherapySwipeAndToggle SUCCESS', {});
        return true;
    } catch (error) {
        logSafe('initTherapySwipeAndToggle ERROR', { error: error.message });
        return false;
    }
}

/**
 * Создать кнопку-закладку для десктопа
 */
function createDesktopToggleButton() {
    // Проверяем, не существует ли уже
    let btn = document.querySelector('#therapyDesktopToggleBtn');
    if (btn) return;
    
    btn = document.createElement('button');
    btn.id = 'therapyDesktopToggleBtn';
    btn.className = 'therapy-desktop-toggle-btn';
    btn.innerHTML = '◀'; // Стрелка влево (панель открыта)
    btn.title = 'Скрыть панель терапии';
    
    document.body.appendChild(btn);
    
    logSafe('createDesktopToggleButton', { created: true });
}

/**
 * Настроить touch события для свайпов
 */
function setupSwipeGestures() {
    document.addEventListener('touchstart', (e) => {
        touchStartX = e.changedTouches[0].screenX;
    }, false);
    
    document.addEventListener('touchend', (e) => {
        touchEndX = e.changedTouches[0].screenX;
        handleSwipe();
    }, false);
    
    logSafe('setupSwipeGestures', { setup: true });
}

/**
 * Обработать свайп
 */
function handleSwipe() {
    const diff = touchStartX - touchEndX;
    const isPanel = document.querySelector(THERAPY_SELECTORS.therapyPanel);
    const isVisible = isPanel?.classList.contains(THERAPY_CSS_CLASSES.panelVisible);
    
    // Свайп справа-налево (pull from right) = открыть панель
    if (diff < -SWIPE_THRESHOLD && !isVisible) {
        openTherapyPanel();
    }
    
    // Свайп слева-направо (push to right) = закрыть панель
    if (diff > SWIPE_THRESHOLD && isVisible) {
        closeTherapyPanel();
    }
}

/**
 * Открыть панель терапии
 */
export function openTherapyPanel() {
    const panel = document.querySelector(THERAPY_SELECTORS.therapyPanel);
    const overlay = document.querySelector('#therapyPanelOverlay');
    
    if (!panel) return;
    
    // Показываем панель
    panel.classList.add(THERAPY_CSS_CLASSES.panelVisible);
    
    // Показываем overlay (если существует)
    if (overlay) {
        overlay.classList.add('visible');
    }
    
    // Блокируем скролл на мобилке (optional)
    document.body.style.overflow = 'hidden';
    
    // Обновляем кнопку на десктопе (стрелка вправо)
    updateDesktopToggleButton(true);
    
    logSafe('openTherapyPanel', { panelVisible: true });
}

/**
 * Закрыть панель терапии
 */
export function closeTherapyPanel() {
    const panel = document.querySelector(THERAPY_SELECTORS.therapyPanel);
    const overlay = document.querySelector('#therapyPanelOverlay');
    
    if (!panel) return;
    
    // Скрываем панель
    panel.classList.remove(THERAPY_CSS_CLASSES.panelVisible);
    
    // Скрываем overlay
    if (overlay) {
        overlay.classList.remove('visible');
    }
    
    // Разрешаем скролл
    document.body.style.overflow = 'auto';
    
    // Обновляем кнопку на десктопе (стрелка влево)
    updateDesktopToggleButton(false);
    
    logSafe('closeTherapyPanel', { panelVisible: false });
}

/**
 * Переключить видимость панели
 */
export function toggleTherapyPanel() {
    const panel = document.querySelector(THERAPY_SELECTORS.therapyPanel);
    if (!panel) return;
    
    const isVisible = panel.classList.contains(THERAPY_CSS_CLASSES.panelVisible);
    
    if (isVisible) {
        closeTherapyPanel();
    } else {
        openTherapyPanel();
    }
}

/**
 * Обновить кнопку-закладку на десктопе
 * @param {boolean} isOpen - Панель открыта?
 */
function updateDesktopToggleButton(isOpen) {
    const btn = document.querySelector('#therapyDesktopToggleBtn');
    if (!btn) return;
    
    if (isOpen) {
        btn.innerHTML = '▶'; // Стрелка вправо (панель скрыта)
        btn.title = 'Показать панель терапии';
        btn.classList.remove('hidden');
    } else {
        btn.innerHTML = '◀'; // Стрелка влево (панель открыта)
        btn.title = 'Скрыть панель терапии';
    }
}

/**
 * Настроить события клика на toggle кнопку
 */
function setupToggleButtonEvents() {
    document.addEventListener('click', (e) => {
        // Desktop toggle button
        if (e.target.id === 'therapyDesktopToggleBtn') {
            toggleTherapyPanel();
            return;
        }
        
        // Старая кнопка в панели (если существует)
        if (e.target.id === 'therapyTogglePanelBtn') {
            toggleTherapyPanel();
            return;
        }
        
        // Клик на overlay = закрыть панель
        if (e.target.id === 'therapyPanelOverlay') {
            closeTherapyPanel();
            return;
        }
    });
    
    logSafe('setupToggleButtonEvents', { setup: true });
}

console.log('✅ Therapy Swipe & Toggle Manager loaded');
