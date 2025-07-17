// ==============================================================================
// FILE: core/agentManager.js
// DESCRIPTION: Production-ready agent manager - connects to backend workflow system
// ==============================================================================

import { enterpriseApi } from '../adapters/api';

/**
 * Production Agent Manager
 * 
 * Connects to backend workflow system instead of duplicating registry logic.
 * Gets agent/component info from workflow.json via backend API.
 */
class ProductionAgentManager {
  constructor() {
    this.metrics = {
      messagesProcessed: 0,
      actionsHandled: 0,
      errors: 0
    };
    this.workflowCache = new Map();
  }

  /**
   * Get workflow configuration from backend
   */
  async getWorkflowConfig(workflowType = 'generator') {
    const cacheKey = workflowType;
    
    if (this.workflowCache.has(cacheKey)) {
      return this.workflowCache.get(cacheKey);
    }

    try {
      // Get workflow config from backend API
      const response = await enterpriseApi.get(`/workflow/${workflowType}/config`);
      const config = response.data;
      
      this.workflowCache.set(cacheKey, config);
      console.log(`✅ Loaded workflow config: ${workflowType}`);
      
      return config;
      
    } catch (error) {
      console.error(`Failed to load workflow config: ${workflowType}`, error);
      // Fallback to basic config
      return {
        ui_capable_agents: [],
        workflow_name: workflowType
      };
    }
  }

  /**
   * Process message through backend workflow system
   */
  async processMessage(message, agentType = null) {
    this.metrics.messagesProcessed++;
    
    try {
      // Send to backend workflow system
      const response = await enterpriseApi.post('/chat/message', {
        content: message.content || message.text || message,
        agent_type: agentType,
        workflow_type: 'generator', // Use actual workflow type from context
        context: {
          session_id: message.sessionId,
          enterprise_id: message.enterpriseId
        }
      });

      return response.data;
      
    } catch (error) {
      this.metrics.errors++;
      console.error('Message processing failed:', error);
      
      return {
        type: 'error',
        content: 'Sorry, I encountered an error processing your message.',
        error: error.message
      };
    }
  }

  /**
   * Handle UI actions via backend
   */
  async handleAction(action) {
    this.metrics.actionsHandled++;
    
    try {
      // Send action to backend workflow system
      const response = await enterpriseApi.post('/agent/action', {
        action_type: action.type,
        action_data: action.data || action,
        agent_id: action.agentId,
        component_name: action.componentName,
        context: {
          session_id: action.sessionId,
          enterprise_id: action.enterpriseId
        }
      });

      return response.data;
      
    } catch (error) {
      this.metrics.errors++;
      console.error('Action handling failed:', error);
      return {
        type: 'error',
        content: 'Failed to handle action'
      };
    }
  }

  /**
   * Get available agents from workflow config
   */
  async getAvailableAgents(workflowType = 'generator') {
    try {
      const config = await this.getWorkflowConfig(workflowType);
      return config.ui_capable_agents || [];
    } catch (error) {
      console.error('Failed to get available agents:', error);
      return [];
    }
  }

  /**
   * Get agent components from workflow config
   */
  async getAgentComponents(agentName, workflowType = 'generator') {
    try {
      const config = await this.getWorkflowConfig(workflowType);
      const agent = config.ui_capable_agents?.find(a => a.name === agentName);
      return agent?.components || [];
    } catch (error) {
      console.error('Failed to get agent components:', error);
      return [];
    }
  }

  /**
   * Get system metrics
   */
  getMetrics() {
    return {
      ...this.metrics,
      cacheSize: this.workflowCache.size
    };
  }

  /**
   * Clear cache
   */
  clearCache() {
    this.workflowCache.clear();
    console.log('🧹 Agent cache cleared');
  }
}

// Create singleton instance
const manager = new ProductionAgentManager();

// Export convenience functions that connect to real backend
export const processMessage = (message, agentType) => manager.processMessage(message, agentType);
export const handleAction = (action) => manager.handleAction(action);
export const getAvailableAgents = (workflowType) => manager.getAvailableAgents(workflowType);
export const getAgentComponents = (agentName, workflowType) => manager.getAgentComponents(agentName, workflowType);
export const getMetrics = () => manager.getMetrics();
export const clearCache = () => manager.clearCache();

export default manager;
