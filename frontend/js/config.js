// ===== КОНФИГУРАЦИЯ BOARD.AI ===== 
// Централизованное хранилище всех констант приложения 
// 
// ===== АГЕНТЫ ===== 
export const agents = { 
    "ceo": { 
        name: "CEO", 
        icon: "👔", 
        color: "#667eea" 
    }, 
    "cfo": { 
        name: "CFO", 
        icon: "💰", 
        color: "#764ba2" 
    }, 
    "cpo": { 
        name: "CPO", 
        icon: "🎯", 
        color: "#f093fb" 
    }, 
    "marketing": { 
        name: "Marketing", 
        icon: "📢", 
        color: "#4facfe" 
    }, 
    "skeptic": { 
        name: "Skeptic", 
        icon: "⚠️", 
        color: "#fa709a" 
    } 
}; 

export const agentKeys = Object.keys(agents); 

// ===== API КОНФИГУРАЦИЯ ===== 
export const API_CONFIG = { 
    endpoint: '/api/board', 
    timeout: 30000, 
    retries: 1, 
    headers: { 'Content-Type': 'application/json' 
    } 
}; 

// ===== DOM СЕЛЕКТОРЫ ===== 
export const DOM_SELECTORS = { 
    chatArea: '#chatArea',
    messageInput: '#messageInput', 
    sendBtn: '#sendBtn', 
    summaryBtn: '#summaryBtn', 
    debugCheckbox: '#debugCheckbox', 
    agentsList: '#agentsList', 
    mobileTabs: '#mobileTabs', 
    sidebar: '#sidebar', 
    overlay: '#overlay', 
    menuBtn: '#menuBtn', 
    mobileHeader: '.mobile-header', 
    container: '.container' }; 
    
// ===== CSS КЛАССЫ ===== 
export const CSS_CLASSES = { 
    message: 'message', 
    messageUser: 'user', 
    messageAgent: 'agent', 
    agentActive: 'active', 
    sidebarOpen: 'open', 
    overlayVisible: 'visible', 
    mobileTabActive: 'active', 
    skeleton: 'skeleton-msg', 
    debugMode: 'on'
 }; 
 
 // ===== ТАЙМАУТЫ И ЗАДЕРЖКИ ===== 
 export const TIMING = {
     scrollDelay: 50,
     skeletonDuration: 1500,
     inputAutoheightMax: 100,
     progressBarDelay: 100
}; 

// ===== BADGE ТИПЫ ===== 
export const BADGE_TYPES = { 
    positive: ['go', 'fast', 'safe', 'scalable', 'fixable', 'ready'], 
    negative: ['nogo', 'slow', 'vulnerable', 'manual', 'fatal', 'blocked'] 
}; 

// ===== РЕГУЛЯРНЫЕ ВЫРАЖЕНИЯ ===== 
export const REGEX = { 
    labelValue:  /^\[?([^\]:]+)\]?\s*[—:-]\s*(.+)$/,
    percentage: /(\d+)%/,
    currency: /[\d,]+\s*(руб|rub|usd|\$|₽|р\.|млн|млрд)/i
}; 

console.log('✅ Config module loaded');
// ===== THERAPY КОНФИГУРАЦИЯ =====
export const API_ENDPOINT = '/api';  // Base API endpoint (используется в therapy-api.js)

export const RATE_LIMIT_THERAPY_CHAT = {
    maxPerMinute: 10,
    maxPerHour: 100
};

export const THERAPY_CONFIG = {
    // UI параметры
    maxInsightsVisible: 5,           // Сколько insights показать без скроллинга
    maxHypothesesVisible: 3,         // Сколько hypotheses показать без скроллинга
    confidenceReadyForBoard: 85,     // Минимальный confidence для готовности к Board
    
    // Стили
    therapyMessageClass: 'therapy-message',
    therapyPanelClass: 'therapy-panel',
    therapyInsightClass: 'therapy-insight',
    therapyHypothesisClass: 'therapy-hypothesis',
    therapyBubbleContainerClass: 'therapy-bubbles',
    
    // Иконки и эмодзи
    icons: {
        sendToBoard: '📌',
        formulate: '💭',
        continue: '❓',
        therapist: '🧠',
        insights: '💡',
        hypotheses: '🎯'
    }
};

// ===== THERAPY DOM СЕЛЕКТОРЫ =====
export const THERAPY_SELECTORS = {
    therapyPanel: '#therapyPanel',
    therapyInsightsList: '#therapyInsightsList',
    therapyHypothesesList: '#therapyHypothesesList',
    therapyBubblesContainer: '#therapyBubblesContainer',
    therapyToggleBtn: '#therapyTogglePanelBtn'
};

// ===== THERAPY CSS КЛАССЫ =====
export const THERAPY_CSS_CLASSES = {
    panelVisible: 'visible',
    insightWithDelete: 'has-delete-btn',
    hypothesisActive: 'active',
    bubbleReady: 'ready',
    mobileDrawerOpen: 'drawer-open',
    therapyMode: 'therapy-mode'
};

console.log('✅ Config module loaded with Therapy constants');
