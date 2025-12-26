// ===== МОБИЛЬНАЯ НАВИГАЦИЯ =====

import { DOM_SELECTORS } from '../config.js';
import { openSidebar, closeSidebar } from './sidebar.js';
import { logSafe } from '../utils/helpers.js';

/**
 * Инициализирует мобильное меню (кнопка hamburger и overlay)
 */
export function setupMobileNav() {
    const menuBtn = document.querySelector(DOM_SELECTORS.menuBtn);
    const overlay = document.querySelector(DOM_SELECTORS.overlay);

    if (menuBtn) {
        menuBtn.addEventListener('click', () => {
            openSidebar();
        });
    }

    if (overlay) {
        overlay.addEventListener('click', () => {
            closeSidebar();
        });
    }

    logSafe('info', '✅ Mobile navigation initialized');
}

/**
 * Проверяет, мобильное ли устройство (через ширину окна)
 * @returns {boolean}
 */
export function isMobileDevice() {
    return window.innerWidth <= 768;
}

/**
 * Слушает изменения размера экрана (resize events)
 * Закрывает sidebar если экран стал больше 768px
 */
export function setupResponsiveListener() {
    window.addEventListener('resize', () => {
        if (!isMobileDevice()) {
            closeSidebar();
        }
    });

    logSafe('info', '✅ Responsive listener initialized');
}

console.log('✅ Mobile module loaded');
