// ===== THERAPY PANEL SWIPE & TOGGLE MANAGER =====
// Управляет открытием/закрытием панели терапии на мобилке (свайпы)
// и кнопкой-закладкой на десктопе

import { THERAPY_SELECTORS, THERAPY_CSS_CLASSES } from '../config.js';
import { logSafe } from '../utils/helpers.js';

let touchStartX = 0;
let touchStartY = 0;
let touchEndX = 0;
let touchEndY = 0;
const SWIPE_THRESHOLD = 50; // минимальная дистанция для свайпа (px)
const VERTICAL_THRESHOLD = 30; // максимальное вертикальное движение для жеста (px)

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
        touchStartY = e.changedTouches[0].screenY;
    }, false);
    
    document.addEventListener('touchend', (e) => {
        touchEndX = e.changedTouches[0].screenX;
        touchEndY = e.changedTouches[0].screenY;
        handleSwipe();
    }, false);
    
    logSafe('setupSwipeGestures', { setup: true });
}

/**
 * Обработать свайп
 * 
 * ЛОГИКА ЖЕСТОВ:
 * - Pull from right (свайп справа-налево): открыть панель
 * - Push to right (свайп слева-направо): закрыть панель
 * - Защита от вертикальных жестов (скролл, прокрутка чата)
 */
function handleSwipe() {
    // Горизонтальная дистанция
    const diffX = touchEndX - touchStartX;
    
    // Вертикальная дистанция (защита от случайных вертикальных жестов)
    const diffY = Math.abs(touchEndY - touchStartY);
    
    // Если вертикальное движение > горизонтального, это скролл, не свайп
    if (diffY > VERTICAL_THRESHOLD) {
        return;
    }
    
    const isPanel = document.querySelector(THERAPY_SELECTORS.therapyPanel);
    const isVisible = isPanel?.classList.contains(THERAPY_CSS_CLASSES.panelVisible);
    
    logSafe('handleSwipe', {
        diffX: Math.round(diffX),
        diffY: Math.round(diffY),
        isVisible: isVisible,
        action: diffX < -SWIPE_THRESHOLD ? 'pull-from-right' : diffX > SWIPE_THRESHOLD ? 'push-to-right' : 'no-action'
    });
    
    // ОТКРЫТИЕ: Pull from right (свайп справа-налево = отрицательное diffX)
    // Пользователь проводит пальцем от правого края (большой X) к центру (меньший X)
    // touchEndX < touchStartX → diffX < 0 → diffX < -SWIPE_THRESHOLD
    if (diffX < -SWIPE_THRESHOLD && !isVisible) {
        openTherapyPanel();
        return;
    }
    
    // ЗАКРЫТИЕ: Push to right (свайп слева-направо = положительное diffX)
    // Пользователь проводит пальцем от центра (меньший X) к правому краю (большой X)
    // touchEndX > touchStartX → diffX > 0 → diffX > SWIPE_THRESHOLD
    if (diffX > SWIPE_THRESHOLD && isVisible) {
        closeTherapyPanel();
        return;
    }
}

/**
 * Открыть панель терапии
 */
export function openTherapyPanel() {
    const panel = document.querySelector(THERAPY_SELECTORS.therapyPanel);
    const overlay = document.querySelector('#therapyPanelOverlay');
    
    if (!panel) return;
    
    // Показываем панель (добавляем класс visible)
    panel.classList.add(THERAPY_CSS_CLASSES.panelVisible);
    
    // Показываем overlay (если существует)
    if (overlay) {
        overlay.classList.add('visible');
    }
    
    // Блокируем скролл на мобилке
    document.body.style.overflow = 'hidden';
    
    // Закрываем левое меню (бургер) если оно открыто
    closeLeftMenuIfOpen();
    
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
    
    // Скрываем панель (удаляем класс visible)
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
 * Закрыть левое меню (бургер), если оно открыто
 * Синхронизация: при открытии панели терапии закрываем левое меню
 */
function closeLeftMenuIfOpen() {
    const sidebar = document.querySelector('.sidebar');
    const overlay = document.querySelector('.overlay');
    
    if (sidebar && sidebar.classList.contains('visible')) {
        sidebar.classList.remove('visible');
    }
    
    if (overlay && overlay.classList.contains('visible')) {
        overlay.classList.remove('visible');
    }
    
    logSafe('closeLeftMenuIfOpen', { action: 'closed' });
}

/**
 * Обновить кнопку-закладку на десктопе
 * @param {boolean} isOpen - Панель открыта?
 */
function updateDesktopToggleButton(isOpen) {
    const btn = document.querySelector('#therapyDesktopToggleBtn');
    if (!btn) return;
    
    if (isOpen) {
        btn.innerHTML = '▶'; // Стрелка вправо (панель открыта, нажми чтобы закрыть)
        btn.title = 'Скрыть панель терапии';
        btn.classList.remove('hidden');
    } else {
        btn.innerHTML = '◀'; // Стрелка влево (панель закрыта, нажми чтобы открыть)
        btn.title = 'Показать панель терапии';
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
        
        // Клик на overlay = закрыть панель
        if (e.target.id === 'therapyPanelOverlay') {
            closeTherapyPanel();
            return;
        }
    });
    
    // Синхронизация: когда открывается левое меню, закрываем правую панель
    document.addEventListener('click', (e) => {
        if (e.target.id === 'menuBtn' || e.target.closest('#menuBtn')) {
            // Это клик на кнопку бургер-меню
            const sidebar = document.querySelector('.sidebar');
            if (sidebar && sidebar.classList.contains('visible')) {
                // Меню открывается, закрываем панель терапии
                closeTherapyPanel();
            }
        }
    });
    
    logSafe('setupToggleButtonEvents', { setup: true });
}

console.log('✅ Therapy Swipe & Toggle Manager loaded');
