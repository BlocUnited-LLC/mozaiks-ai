// ==============================================================================
// FILE: agents/registry/agentBase.js
// DESCRIPTION: Base agent classes and interfaces - like workflow base classes
// ==============================================================================

/**
 * Base Agent Class
 * Provides standard interface that all agents should implement
 */
export class BaseAgent {
  constructor(options = {}) {
    this.id = options.id || this.constructor.name.toLowerCase();
    this.name = options.name || this.constructor.name;
    this.description = options.description || this.constructor.description || '';
    this.version = options.version || this.constructor.version || '1.0.0';
    this.options = options;
    
    // Initialize metrics
    this.metrics = {
      messagesProcessed: 0,
      actionsHandled: 0,
      errorsEncountered: 0,
      lastActivity: null,
      createdAt: new Date().toISOString()
    };
  }

  /**
   * Process incoming message - MUST be implemented by subclasses
   * @param {Object} message - The message to process
   * @returns {Promise<Object>} - Agent response
   */
  async processMessage(message) {
    throw new Error(`processMessage must be implemented by ${this.constructor.name}`);
  }

  /**
   * Handle UI actions - Optional for interactive agents
   * @param {Object} action - The action to handle
   * @returns {Promise<Object|null>} - Action response or null
   */
  async handleAction(action) {
    return null; // Default: no action handling
  }

  /**
   * Get agent capabilities - Should be overridden
   * @returns {Array<string>} - List of capabilities
   */
  getCapabilities() {
    return this.constructor.capabilities || [];
  }

  /**
   * Get agent metadata
   * @returns {Object} - Agent metadata
   */
  getMetadata() {
    return {
      id: this.id,
      name: this.name,
      description: this.description,
      version: this.version,
      capabilities: this.getCapabilities(),
      category: this.constructor.category || 'general',
      transport: this.constructor.transport || 'websocket',
      interactive: this.constructor.interactive !== false,
      metrics: this.metrics
    };
  }

  /**
   * Update metrics
   */
  updateMetrics(type, error = null) {
    this.metrics.lastActivity = new Date().toISOString();
    
    switch (type) {
      case 'message':
        this.metrics.messagesProcessed++;
        break;
      case 'action':
        this.metrics.actionsHandled++;
        break;
      case 'error':
        this.metrics.errorsEncountered++;
        break;
    }
    
    if (error) {
      console.error(`Agent ${this.id} error:`, error);
    }
  }

  /**
   * Cleanup resources - Called when agent is destroyed
   */
  async cleanup() {
    // Override in subclasses if needed
  }
}

/**
 * Interactive Agent Class
 * For agents that provide UI components and handle user interactions
 */
export class InteractiveAgent extends BaseAgent {
  constructor(options = {}) {
    super(options);
    this.allowedComponents = this.constructor.allowedComponents || [];
  }

  /**
   * Handle UI actions - MUST be implemented by interactive agents
   */
  async handleAction(action) {
    throw new Error(`handleAction must be implemented by ${this.constructor.name}`);
  }

  /**
   * Create UI message helper
   * @param {string} type - Component type
   * @param {Object} data - Component data
   * @param {string} message - Display message
   * @returns {Object} - UI message object
   */
  createUIMessage(type, data = {}, message = '') {
    if (this.allowedComponents.length > 0 && !this.allowedComponents.includes(type)) {
      throw new Error(`Component type "${type}" not allowed for ${this.constructor.name}`);
    }

    return {
      type: 'ui_component',
      component: type,
      data,
      message,
      agentId: this.id,
      timestamp: new Date().toISOString()
    };
  }

  /**
   * Validate component type
   */
  validateComponentType(type) {
    return this.allowedComponents.length === 0 || this.allowedComponents.includes(type);
  }
}

/**
 * Stateless Agent Class
 * For simple agents that don't maintain state between requests
 */
export class StatelessAgent extends BaseAgent {
  constructor(options = {}) {
    super(options);
    this.stateless = true;
  }

  /**
   * Process message without maintaining state
   */
  async processMessage(message) {
    this.updateMetrics('message');
    
    try {
      const response = await this.handleMessage(message);
      return response;
    } catch (error) {
      this.updateMetrics('error', error);
      throw error;
    }
  }

  /**
   * Handle message - to be implemented by subclasses
   * @param {Object} message - The message to handle
   * @returns {Promise<Object>} - Response
   */
  async handleMessage(message) {
    throw new Error(`handleMessage must be implemented by ${this.constructor.name}`);
  }
}

/**
 * Agent capability constants
 */
export const AgentCapabilities = {
  // Text processing
  TEXT_GENERATION: 'text_generation',
  TEXT_ANALYSIS: 'text_analysis',
  TRANSLATION: 'translation',
  
  // Code related
  CODE_GENERATION: 'code_generation',
  CODE_ANALYSIS: 'code_analysis',
  DEBUGGING: 'debugging',
  
  // UI and interaction
  UI_GENERATION: 'ui_generation',
  FORM_HANDLING: 'form_handling',
  FILE_UPLOAD: 'file_upload',
  
  // Data processing
  DATA_ANALYSIS: 'data_analysis',
  VISUALIZATION: 'visualization',
  MACHINE_LEARNING: 'machine_learning',
  
  // Integration
  API_INTEGRATION: 'api_integration',
  AUTHENTICATION: 'authentication',
  WORKFLOW_ORCHESTRATION: 'workflow_orchestration',
  
  // Specialized
  FEEDBACK_COLLECTION: 'feedback_collection',
  USER_ONBOARDING: 'user_onboarding',
  SYSTEM_MONITORING: 'system_monitoring'
};

/**
 * Agent categories
 */
export const AgentCategories = {
  GENERAL: 'general',
  CODING: 'coding',
  DATA: 'data',
  UI: 'ui',
  INTEGRATION: 'integration',
  SYSTEM: 'system',
  SPECIALIZED: 'specialized'
};

/**
 * Transport types
 */
export const TransportTypes = {
  WEBSOCKET: 'websocket',
  SSE: 'sse',
  HTTP: 'http',
  HYBRID: 'hybrid'
};

/**
 * Agent decorator helpers
 */
export function agentMetadata(metadata) {
  return function(agentClass) {
    Object.assign(agentClass, metadata);
    return agentClass;
  };
}

export function capabilities(...caps) {
  return function(agentClass) {
    agentClass.capabilities = caps;
    return agentClass;
  };
}

export function category(cat) {
  return function(agentClass) {
    agentClass.category = cat;
    return agentClass;
  };
}

export function transport(transportType) {
  return function(agentClass) {
    agentClass.transport = transportType;
    return agentClass;
  };
}
