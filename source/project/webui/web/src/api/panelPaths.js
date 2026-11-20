// Vite supplies the installation path. Standalone API clients use the root panel.
export const panelBase = import.meta.env?.BASE_URL ?? '/';
export const panelApi = panelBase + 'index.php';
