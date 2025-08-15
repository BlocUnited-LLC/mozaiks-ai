// Simple configuration for agentic chat platform
class ChatUIConfig {
  constructor() {
    this.config = this.loadConfig();
  }

  loadConfig() {
    const defaultConfig = {
      // API Configuration
      api: {
        baseUrl: process.env.REACT_APP_API_BASE_URL || 'http://localhost:8000',
        wsUrl: process.env.REACT_APP_WS_URL || 'ws://localhost:8000',
      },

      // Auth Configuration
      auth: {
        mode: process.env.REACT_APP_AUTH_MODE || 'mock', // 'mock' or 'token'
      },

      // UI Configuration
      ui: {
        showHeader: process.env.REACT_APP_SHOW_HEADER !== 'false',
        enableNotifications: process.env.REACT_APP_ENABLE_NOTIFICATIONS !== 'false',
      },

      // Chat Configuration
      chat: {
        // Auth system placeholder - replace with actual auth implementation
        defaultEnterpriseId: process.env.REACT_APP_DEFAULT_ENTERPRISE_ID || '68542c1109381de738222350',
        defaultUserId: process.env.REACT_APP_DEFAULT_USER_ID || '56132',
  // If backend isn't running or no workflow selected, use a safe placeholder
  defaultWorkflow: process.env.REACT_APP_DEFAULT_WORKFLOW || 'TestWorkflow',
      },
    };

    // Override with window.ChatUIConfig if available
    if (typeof window !== 'undefined' && window.ChatUIConfig) {
      return { ...defaultConfig, ...window.ChatUIConfig };
    }

    return defaultConfig;
  }

  get(path) {
    return path.split('.').reduce((current, key) => current?.[key], this.config);
  }

  getConfig() {
    return this.config;
  }
}

// Singleton instance
const configInstance = new ChatUIConfig();

export default configInstance;
