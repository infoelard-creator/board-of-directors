// ===== УТИЛИТЫ И ХЕЛПЕРЫ ДЛЯ BOARD.AI =====

/**
 * Генерирует уникальный Request ID
 * @returns {string} req_<timestamp>_<random>
 */
export function generateRequestId(prefix = 'req') {
    const timestamp = Date.now();
    const random = Math.random().toString(36).substr(2, 9);
    return `${prefix}_${timestamp}_${random}`;
}

/**
 * Генерирует userId для новой сессии
 * @returns {string} user_<random>
 */
export function generateUserId() {
    return 'user_' + Math.random().toString(36).substr(2, 9);
}

/**
 * Безопасный логгер с уровнями
 * @param {'log'|'info'|'warn'|'error'|'debug'} level
 * @param {string} message
 * @param {any} [data]
 */
export function logSafe(level, message, data) {
    try {
        const logger = console[level] || console.log;
        if (data !== undefined) {
            logger(message, data);
        } else {
            logger(message);
        }
    } catch {
        // Игнорируем ошибки логгера
    }
}

/**
 * Форматирует время в миллисекундах в строку
 * @param {number} ms
 * @returns {string}
 */
export function formatMs(ms) {
    if (!Number.isFinite(ms)) return '-';
    if (ms < 1000) return `${Math.round(ms)}ms`;
    return `${(ms / 1000).toFixed(1)}s`;
}

/**
 * Debounce для функций (часто полезен, если будем делать live-валидацию или др.)
 * @param {Function} fn
 * @param {number} delay
 * @returns {Function}
 */
export function debounce(fn, delay = 300) {
    let timeoutId;
    return (...args) => {
        clearTimeout(timeoutId);
        timeoutId = setTimeout(() => fn.apply(null, args), delay);
    };
}

/**
 * Проверяет, есть ли соединение с интернетом
 * @returns {boolean}
 */
export function isOnline() {
    if (typeof navigator === 'undefined') return true;
    return navigator.onLine;
}

/**
 * Безопасно парсит JSON
 * @param {string} text
 * @param {any} fallback
 * @returns {any}
 */
export function safeJsonParse(text, fallback = null) {
    try {
        return JSON.parse(text);
    } catch (e) {
        logSafe('warn', 'JSON parse error', e);
        return fallback;
    }
}

/**
 * Вычисляет время ответа по requestId (req_<timestamp>_<random>)
 * @param {string} requestId
 * @returns {number} миллисекунды или 0
 */
export function calculateResponseTime(requestId) {
    try {
        const parts = requestId.split('_');
        const ts = parseInt(parts[1], 10);
        if (Number.isNaN(ts)) return 0;
        return Date.now() - ts;
    } catch {
        return 0;
    }
}