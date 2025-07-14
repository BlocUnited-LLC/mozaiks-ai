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
        // TODO: Set up proper auth system - this is a placeholder enterprise ID for testing
        // Enterprise ID: 68542c1109381de738222350 (test enterprise with existing data/context)
        // This enterprise has actual data that the generator workflow uses for context variables
        defaultEnterpriseId: process.env.REACT_APP_DEFAULT_ENTERPRISE_ID || '68542c1109381de738222350',
        defaultUserId: process.env.REACT_APP_DEFAULT_USER_ID || 'user123',
        defaultWorkflow: process.env.REACT_APP_DEFAULT_WORKFLOW || null, // Let backend provide default
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
