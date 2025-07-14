// ==============================================================================
// FILE: core/agentManager.js
// DESCRIPTION: Core agent manager - uses new registry system
// ==============================================================================

import { getAgent, getAgentsByCapability, getAllAgents, getAgentMetadata } from '../agents/registry';

/**
 * Core Agent Manager
 * 
 * Now uses the registry system for dynamic agent management.
 * This provides the same interface but with registry-based backend.
 */
class CoreAgentManager {
  constructor() {
    this.instanceCache = new Map();
    this.metrics = {
      messagesProcessed: 0,
      actionsHandled: 0,
      agentsUsed: new Set(),
      errors: 0
    };
  }

  /**
   * Get agent instance (with caching)
   */
  async getAgentInstance(agentType, options = {}) {
    const cacheKey = `${agentType}_${JSON.stringify(options)}`;
    
    if (this.instanceCache.has(cacheKey)) {
      return this.instanceCache.get(cacheKey);
    }

    try {
      // Use registry to get agent
      const agent = await getAgent(agentType, options);
      this.instanceCache.set(cacheKey, agent);
      this.metrics.agentsUsed.add(agentType);
      
      console.log(`🤖 Agent instance created: ${agentType}`);
      return agent;
      
    } catch (error) {
      console.error(`Failed to create agent instance: ${agentType}`, error);
      this.metrics.errors++;
      throw error;
    }
  }

  /**
   * Process message through best available agent
   */
  async processMessage(message, agentType = null) {
    this.metrics.messagesProcessed++;
    
    try {
      if (agentType) {
        // Use specific agent
        const agent = await this.getAgentInstance(agentType);
        return await agent.processMessage(message);
      }

      // Auto-select best agent based on message content
      const selectedAgent = await this.selectAgentForMessage(message);
      if (selectedAgent) {
        const agent = await this.getAgentInstance(selectedAgent);
        return await agent.processMessage(message);
      }

      // Fallback response
      return {
        type: 'text',
        content: 'No suitable agent found for this message.',
        agentType: 'system'
      };
      
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
   * Handle UI actions
   */
  async handleAction(action) {
    this.metrics.actionsHandled++;
    
    const { agentId, agentType } = action;
    if (!agentId && !agentType) {
      console.warn('Action missing agent identifier:', action);
      return null;
    }

    try {
      const agent = await this.getAgentInstance(agentType || agentId);
      
      if (agent.handleAction) {
        return await agent.handleAction(action);
      }
      
      console.warn(`Agent ${agentType || agentId} does not support actions`);
      return null;
      
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
   * Select best agent for a message (smart routing)
   */
  async selectAgentForMessage(message) {
    // Simple capability-based selection
    // In a real system, this could use ML/LLM for better routing
    
    const messageText = message.text || message.content || '';
    const messageLower = messageText.toLowerCase();
    
    // Capability keywords mapping
    const capabilityKeywords = {
      'feedback_collection': ['feedback', 'review', 'rating', 'survey'],
      'code_generation': ['code', 'function', 'script', 'program'],
      'data_analysis': ['data', 'chart', 'analyze', 'statistics'],
      'ui_generation': ['form', 'button', 'interface', 'component'],
      'file_upload': ['upload', 'file', 'attach', 'document']
    };
    
    // Find matching capabilities
    const matchingCapabilities = [];
    for (const [capability, keywords] of Object.entries(capabilityKeywords)) {
      if (keywords.some(keyword => messageLower.includes(keyword))) {
        matchingCapabilities.push(capability);
      }
    }
    
    // Get agents with matching capabilities
    for (const capability of matchingCapabilities) {
      const agents = getAgentsByCapability(capability);
      if (agents.length > 0) {
        // Return highest priority agent
        const sortedAgents = agents
          .map(agentType => ({
            agentType,
            metadata: getAgentMetadata(agentType)
          }))
          .sort((a, b) => (b.metadata?.priority || 50) - (a.metadata?.priority || 50));
        
        return sortedAgents[0].agentType;
      }
    }
    
    // Fallback to first available agent
    const allAgents = getAllAgents();
    return allAgents.length > 0 ? allAgents[0] : null;
  }

  /**
   * Get system metrics
   */
  getMetrics() {
    return {
      ...this.metrics,
      agentsUsed: Array.from(this.metrics.agentsUsed),
      cacheSize: this.instanceCache.size
    };
  }

  /**
   * Clear agent cache
   */
  clearCache() {
    this.instanceCache.clear();
    console.log('🧹 Agent cache cleared');
  }

  /**
   * Get available agents
   */
  getAvailableAgents() {
    return getAllAgents().map(agentType => ({
      agentType,
      metadata: getAgentMetadata(agentType)
    }));
  }
}

// Create singleton instance
const manager = new CoreAgentManager();

// Export convenience functions
export const processMessage = (message, agentType) => manager.processMessage(message, agentType);
export const handleAction = (action) => manager.handleAction(action);
export const getAgentInstance = (agentType, options) => manager.getAgentInstance(agentType, options);
export const getMetrics = () => manager.getMetrics();
export const clearCache = () => manager.clearCache();
export const getAvailableAgents = () => manager.getAvailableAgents();

export default manager;
