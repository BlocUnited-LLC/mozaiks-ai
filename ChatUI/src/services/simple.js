import config from '../config/simple';
import { MockAuthAdapter, TokenAuthAdapter } from '../adapters/auth';
import { WebSocketApiAdapter, RestApiAdapter } from '../adapters/api';

class ChatUIServices {
  constructor() {
    this.authAdapter = null;
    this.apiAdapter = null;
    this.initialized = false;
  }

  initialize(options = {}) {
    if (this.initialized) return;

    // Initialize auth adapter
    this.authAdapter = this.createAuthAdapter(options.authAdapter);
    
    // Initialize API adapter
    this.apiAdapter = this.createApiAdapter(options.apiAdapter);

    this.initialized = true;
    console.log('ChatUI Services initialized');
  }

  createAuthAdapter(customAdapter) {
    if (customAdapter) return customAdapter;

    const authMode = config.get('auth.mode');
    
    switch (authMode) {
      case 'mock':
        return new MockAuthAdapter();
      case 'token':
        return new TokenAuthAdapter(config.get('api.baseUrl'));
      default:
        console.warn(`Unknown auth mode: ${authMode}, using mock`);
        return new MockAuthAdapter();
    }
  }

  createApiAdapter(customAdapter) {
    if (customAdapter) return customAdapter;

    // Always use real backend connection - no more mocks hiding issues
    // Use REST API adapter for real backend connection
    if (config.get('api.baseUrl')) {
      console.log('🔗 Using RestApiAdapter for real backend connection');
      return new RestApiAdapter(config.get('api'));
    }

    // Check if WebSocket is available
    if (config.get('api.wsUrl')) {
      return new WebSocketApiAdapter(config.getConfig());
    }

    // Fallback to REST API
    return new RestApiAdapter(config.getConfig());
  }

  getAuthAdapter() {
    return this.authAdapter;
  }

  getApiAdapter() {
    return this.apiAdapter;
  }

  // Convenience methods
  async getCurrentUser() {
    return this.authAdapter?.getCurrentUser();
  }

  createWebSocketConnection(enterpriseId, userId, callbacks, workflowType, chatId) {
    return this.apiAdapter?.createWebSocketConnection(enterpriseId, userId, callbacks, workflowType, chatId);
  }
}

// Singleton instance
const services = new ChatUIServices();

export default services;
