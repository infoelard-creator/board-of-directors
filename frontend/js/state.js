// ===== ГЛОБАЛЬНОЕ СОСТОЯНИЕ BOARD.AI =====
// Отвечает за authToken, выбранных агентов, историю чата, флаги загрузки и debug

import { agentKeys } from './config.js';

class BoardState {
    constructor() {
        this.authToken = null;
        this.selectedAgents = new Set();
        this.chatHistory = [];
        this.isLoading = false;
        this.summaryShown = false;
        this.debugMode = false;
    }

    // ===== AUTH =====
    setAuthToken(token) {
        this.authToken = token;
        try {
            localStorage.setItem('authToken', token);
        } catch (e) {
            console.warn('Не удалось сохранить токен в localStorage', e);
        }
    }

    getAuthToken() {
        return this.authToken;
    }

    restoreAuthToken() {
        try {
            const token = localStorage.getItem('authToken');
            if (token) {
                this.authToken = token;
                console.info('✅ Сессия восстановлена');
                return true;
            }
        } catch (e) {
            console.warn('Не удалось прочитать токен из localStorage', e);
        }
        return false;
    }

    // ===== AGENTS =====
    initDefaultAgents() {
        agentKeys.forEach(key => this.selectedAgents.add(key));
    }

    toggleAgent(agentKey) {
        if (this.selectedAgents.has(agentKey)) {
            this.selectedAgents.delete(agentKey);
        } else {
            this.selectedAgents.add(agentKey);
        }
    }

    selectAgent(agentKey) {
        this.selectedAgents.add(agentKey);
    }

    deselectAgent(agentKey) {
        this.selectedAgents.delete(agentKey);
    }

    getSelectedAgents() {
        return Array.from(this.selectedAgents);
    }

    getSelectedAgentsCount() {
        return this.selectedAgents.size;
    }

    clearSelectedAgents() {
        this.selectedAgents.clear();
    }

    // ===== CHAT HISTORY =====
    addToHistory(sender, agentType, text) {
        const prefix = sender === 'user' ? 'User' : agentType;
        this.chatHistory.push(`${prefix}: ${text}`);
    }

    getHistory() {
        return this.chatHistory;
    }

    getHistoryLength() {
        return this.chatHistory.length;
    }

    clearHistory() {
        this.chatHistory = [];
    }

    // ===== LOADING / SUMMARY =====
    setLoading(flag) {
        this.isLoading = flag;
    }

    isCurrentlyLoading() {
        return this.isLoading;
    }

    setSummaryShown(flag) {
        this.summaryShown = flag;
    }

    isSummaryShown() {
        return this.summaryShown;
    }

    // ===== DEBUG =====
    setDebugMode(flag) {
        this.debugMode = flag;
    }

    isDebugEnabled() {
        return this.debugMode;
    }

    // ===== RESET ВСЕГО СОСТОЯНИЯ =====
    resetAll() {
        this.clearHistory();
        this.clearSelectedAgents();
        this.isLoading = false;
        this.summaryShown = false;
        this.debugMode = false;
    }
}

export const appState = new BoardState();

console.log('✅ State module loaded');