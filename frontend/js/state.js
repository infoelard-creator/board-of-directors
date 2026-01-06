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
        
        // ===== THERAPY PROPERTIES =====
        this.therapySessionId = null;
        this.therapyMode = false;
        this.therapyInsights = [];
        this.therapyHypotheses = [];
        this.therapyReadyForBoard = false;
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


    // ===== THERAPY STATE =====
    // Управление сессией терапии и данными

    setTherapySessionId(sessionId) {
        this.therapySessionId = sessionId;
    }

    getTherapySessionId() {
        return this.therapySessionId;
    }

    setTherapyMode(flag) {
        this.therapyMode = flag;
    }

    isTherapyMode() {
        return this.therapyMode;
    }

    // Insights
    setTherapyInsights(insights) {
        this.therapyInsights = insights || [];
    }

    getTherapyInsights() {
        return this.therapyInsights;
    }

    addTherapyInsight(insight) {
        this.therapyInsights.push(insight);
    }

    removeTherapyInsightById(insightId) {
        this.therapyInsights = this.therapyInsights.filter(
            insight => insight.id !== insightId
        );
    }

    getTherapyInsightsCount() {
        return this.therapyInsights.length;
    }

    // Hypotheses
    setTherapyHypotheses(hypotheses) {
        this.therapyHypotheses = hypotheses || [];
    }

    getTherapyHypotheses() {
        return this.therapyHypotheses;
    }

    getTherapyHypothesesSorted() {
        // Сортируем по confidence (убывание)
        return [...this.therapyHypotheses].sort(
            (a, b) => (b.confidence || 0) - (a.confidence || 0)
        );
    }

    getBestHypothesis() {
        const sorted = this.getTherapyHypothesesSorted();
        return sorted.length > 0 ? sorted[0] : null;
    }

    getTherapyHypothesesCount() {
        return this.therapyHypotheses.length;
    }

    // Ready for board
    setTherapyReadyForBoard(flag) {
        this.therapyReadyForBoard = flag;
    }

    isTherapyReadyForBoard() {
        return this.therapyReadyForBoard;
    }

    // ===== RESET THERAPY STATE =====
    resetTherapyState() {
        this.therapySessionId = null;
        this.therapyMode = false;
        this.therapyInsights = [];
        this.therapyHypotheses = [];
        this.therapyReadyForBoard = false;
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
