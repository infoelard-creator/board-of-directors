// ===== ПАРСИНГ ОТВЕТОВ ОТ АГЕНТОВ =====
// Выделяет из текста семантические блоки (label-value пары)
// Определяет тип каждого блока: badge, progress, currency, text

import { REGEX, BADGE_TYPES } from '../config.js';

/**
 * Парсит ответ агента в массив семантических блоков
 * @param {string} text - текст ответа от агента
 * @param {string} agentType - тип агента (для логики определения типов)
 * @returns {Array} массив {label, value, type, badgeType}
 */
export function parseAgentResponse(text, agentType) {
    if (!text || typeof text !== 'string') {
        return [];
    }

    const lines = text.split('\n').filter(l => l.trim());
    const sections = [];

    lines.forEach(line => {
        const match = line.match(REGEX.labelValue);

        // Если строка не соответствует формату "Label: value", добавляем как простой текст
        if (!match) {
            if (line.length > 2) {
                sections.push({
                    label: null,
                    value: line,
                    type: 'text',
                    badgeType: null
                });
            }
            return;
        }

        const label = match[1].trim().replace(/[*_]/g, '');
        const value = match[2].trim();

        let type = 'text';
        let badgeType = null;

        // ===== ОПРЕДЕЛЕНИЕ ТИПА БЛОКА =====

        const lowerLabel = label.toLowerCase();
        const upperVal = value.toUpperCase();

        // 1. BADGE (Verdict, Risk, Status)
        if (lowerLabel.includes('verdict') ||
            lowerLabel.includes('risk') ||
            lowerLabel.includes('status') ||
            lowerLabel.includes('решение')) {

            if (BADGE_TYPES.positive.includes(upperVal.toLowerCase())) {
                type = 'badge';
                badgeType = upperVal.toLowerCase();
            } else if (BADGE_TYPES.negative.includes(upperVal.toLowerCase().replace('-', ''))) {
                type = 'badge';
                badgeType = upperVal.toLowerCase().replace('-', '');
            }
        }

        // 2. PROGRESS BAR (Confidence %)
        if ((lowerLabel.includes('confidence') ||
             lowerLabel.includes('уверен') ||
             lowerLabel.includes('вероятност')) &&
            REGEX.percentage.test(value)) {
            type = 'progress';
        }

        // 3. CURRENCY (Cost, Budget, Investment)
        if ((lowerLabel.includes('cost') ||
             lowerLabel.includes('бюджет') ||
             lowerLabel.includes('цена') ||
             lowerLabel.includes('инвест')) &&
            REGEX.currency.test(value)) {
            type = 'currency';
        }

        sections.push({
            label,
            value,
            type,
            badgeType
        });
    });

    return sections;
}

/**
 * Извлекает процент из строки типа "75%"
 * @param {string} value
 * @returns {number} 0-100
 */
export function extractPercentage(value) {
    if (!value) return 0;
    const match = value.match(REGEX.percentage);
    if (match) {
        const num = parseInt(match[1], 10);
        return Math.min(Math.max(num, 0), 100);
    }
    return 0;
}

/**
 * Проверяет, валидны ли секции (массив не пуст)
 * @param {Array} sections
 * @returns {boolean}
 */
export function isValidSections(sections) {
    return Array.isArray(sections) && sections.length > 0;
}

console.log('✅ Parser module loaded');
