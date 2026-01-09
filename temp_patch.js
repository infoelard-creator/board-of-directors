// Найти и заменить innerHTML панели
const oldHTML = `
            <div class="therapy-panel-header">
                <h3>${THERAPY_CONFIG.icons.insights} Key Insights</h3>
                <button id="therapyTogglePanelBtn" class="therapy-toggle-btn" title="Скрыть/показать">×</button>
            </div>
`;

const newHTML = `
            <div class="therapy-panel-header">
                <h3>${THERAPY_CONFIG.icons.insights} Key Insights</h3>
            </div>
`;
