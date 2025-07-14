// ==============================================================================
// FILE: agents/registry/agentRegistry.js
// DESCRIPTION: Central registry for agents - mirrors core workflow registry pattern
// ==============================================================================

/**
 * Agent Registry System
 * 
 * Mirrors the Python core/workflow/init_registry.py pattern:
 * - Decorator-based registration
 * - Auto-discovery system
 * - Metadata-driven configuration
 * - Plugin architecture support
 * - Transport-aware routing
 */

// Registry storage - mirrors Python _WORKFLOW_HANDLERS pattern
const _AGENT_HANDLERS = new Map();
const _AGENT_METADATA = new Map();
const _AGENT_CAPABILITIES = new Map();
const _AGENT_CATEGORIES = new Map();
const _INITIALIZERS = [];

/**
 * Add agent initialization function - mirrors add_initialization_coroutine
 */
export function addAgentInitializer(initFunc) {
  _INITIALIZERS.push(initFunc);
  console.log(`🔧 Registered agent initializer: ${initFunc.name}`);
  return initFunc;
}

/**
 * Register agent decorator - mirrors register_workflow
 * 
 * @param {string} agentType - Unique identifier for the agent
 * @param {Object} options - Agent configuration
 * @param {Array} options.capabilities - Agent capabilities (like tools in workflow)
 * @param {string} options.category - Agent category
 * @param {boolean} options.interactive - Whether agent supports UI interactions
 * @param {string} options.transport - Preferred transport method
 */
export function registerAgent(agentType, options = {}) {
  const {
    capabilities = [],
    category = 'general',
    interactive = true,
    transport = 'websocket',
    priority = 50,
    ...metadata
  } = options;

  return function(agentClass) {
    // Validate agent class
    if (typeof agentClass !== 'function') {
      throw new Error(`Agent "${agentType}" must be a class or constructor function`);
    }

    // Store agent handler
    _AGENT_HANDLERS.set(agentType, agentClass);
    
    // Store metadata - mirrors Python workflow metadata
    _AGENT_METADATA.set(agentType, {
      agentType,
      category,
      interactive,
      transport,
      priority,
      capabilities,
      registeredAt: new Date().toISOString(),
      ...metadata
    });

    // Index by capabilities (like workflow tools)
    _AGENT_CAPABILITIES.set(agentType, capabilities);
    
    // Index by category
    if (!_AGENT_CATEGORIES.has(category)) {
      _AGENT_CATEGORIES.set(category, new Set());
    }
    _AGENT_CATEGORIES.get(category).add(agentType);

    console.log(`✅ Registered agent: ${agentType} (category=${category}, capabilities=[${capabilities.join(', ')}], transport=${transport})`);
    
    return agentClass;
  };
}

/**
 * Register agent capabilities - mirrors register_workflow_tools
 */
export function registerAgentCapabilities(agentType, capabilities) {
  const existing = _AGENT_CAPABILITIES.get(agentType) || [];
  const updated = [...new Set([...existing, ...capabilities])];
  
  _AGENT_CAPABILITIES.set(agentType, updated);
  
  // Update metadata
  const metadata = _AGENT_METADATA.get(agentType);
  if (metadata) {
    metadata.capabilities = updated;
  }

  console.log(`🔧 Registered ${capabilities.length} capabilities for ${agentType}: [${capabilities.join(', ')}]`);
}

/**
 * Get agent handler by type - mirrors get_workflow_handler
 */
export function getAgentHandler(agentType) {
  return _AGENT_HANDLERS.get(agentType);
}

/**
 * Get agent metadata - mirrors workflow metadata access
 */
export function getAgentMetadata(agentType) {
  return _AGENT_METADATA.get(agentType);
}

/**
 * Get all registered agents - mirrors get_all_workflows
 */
export function getAllAgents() {
  return Array.from(_AGENT_HANDLERS.keys());
}

/**
 * Get agents by capability - mirrors workflow tool filtering
 */
export function getAgentsByCapability(capability) {
  const matches = [];
  for (const [agentType, capabilities] of _AGENT_CAPABILITIES) {
    if (capabilities.includes(capability)) {
      matches.push(agentType);
    }
  }
  return matches;
}

/**
 * Get agents by category
 */
export function getAgentsByCategory(category) {
  const categorySet = _AGENT_CATEGORIES.get(category);
  return categorySet ? Array.from(categorySet) : [];
}

/**
 * Get agent transport preference - mirrors workflow transport mapping
 */
export function getAgentTransport(agentType) {
  const metadata = _AGENT_METADATA.get(agentType);
  return metadata?.transport || 'websocket';
}

/**
 * Get all agent capabilities - for discovery
 */
export function getAllCapabilities() {
  const allCapabilities = new Set();
  for (const capabilities of _AGENT_CAPABILITIES.values()) {
    capabilities.forEach(cap => allCapabilities.add(cap));
  }
  return Array.from(allCapabilities);
}

/**
 * Get registry manifest - mirrors plugin system
 */
export function getAgentManifest() {
  return {
    agents: Object.fromEntries(
      Array.from(_AGENT_METADATA.entries()).map(([type, metadata]) => [
        type,
        {
          ...metadata,
          handler: _AGENT_HANDLERS.has(type)
        }
      ])
    ),
    capabilities: getAllCapabilities(),
    categories: Object.fromEntries(
      Array.from(_AGENT_CATEGORIES.entries()).map(([cat, agents]) => [
        cat,
        Array.from(agents)
      ])
    ),
    stats: {
      totalAgents: _AGENT_HANDLERS.size,
      totalCapabilities: getAllCapabilities().length,
      totalCategories: _AGENT_CATEGORIES.size
    }
  };
}

/**
 * Initialize all agents - mirrors workflow initialization
 */
export async function initializeAgents() {
  console.log('🚀 Initializing agent registry...');
  
  const startTime = Date.now();
  let successCount = 0;
  let errorCount = 0;

  // Run all registered initializers
  for (const initializer of _INITIALIZERS) {
    try {
      await initializer();
      successCount++;
      console.log(`✅ Agent initializer completed: ${initializer.name}`);
    } catch (error) {
      errorCount++;
      console.error(`❌ Agent initializer failed: ${initializer.name}`, error);
    }
  }

  const duration = Date.now() - startTime;
  
  console.log(`🎯 Agent registry initialization complete:`, {
    duration: `${duration}ms`,
    agents: _AGENT_HANDLERS.size,
    capabilities: getAllCapabilities().length,
    categories: _AGENT_CATEGORIES.size,
    initializers: { success: successCount, errors: errorCount }
  });

  return {
    success: errorCount === 0,
    stats: {
      duration,
      agents: _AGENT_HANDLERS.size,
      capabilities: getAllCapabilities().length,
      initializers: { success: successCount, errors: errorCount }
    }
  };
}

/**
 * Agent instance manager - handles actual agent instantiation
 */
class AgentInstanceManager {
  constructor() {
    this.instances = new Map();
    this.instanceMetrics = new Map();
  }

  async getInstance(agentType, options = {}) {
    const instanceKey = `${agentType}_${JSON.stringify(options)}`;
    
    if (this.instances.has(instanceKey)) {
      return this.instances.get(instanceKey);
    }

    const AgentClass = getAgentHandler(agentType);
    if (!AgentClass) {
      throw new Error(`Agent type "${agentType}" not registered`);
    }

    try {
      const instance = new AgentClass(options);
      this.instances.set(instanceKey, instance);
      
      // Track metrics
      this.instanceMetrics.set(instanceKey, {
        created: new Date().toISOString(),
        agentType,
        options,
        usageCount: 0
      });

      console.log(`🤖 Created agent instance: ${agentType}`);
      return instance;
      
    } catch (error) {
      console.error(`Failed to create agent instance: ${agentType}`, error);
      throw error;
    }
  }

  getInstanceMetrics() {
    return Object.fromEntries(this.instanceMetrics.entries());
  }

  clearInstances() {
    this.instances.clear();
    this.instanceMetrics.clear();
  }
}

// Export singleton instance manager
export const agentInstanceManager = new AgentInstanceManager();

/**
 * Convenience function for getting agent instances
 */
export async function getAgent(agentType, options = {}) {
  return agentInstanceManager.getInstance(agentType, options);
}

/**
 * Debug utilities
 */
export const debug = {
  getHandlers: () => _AGENT_HANDLERS,
  getMetadata: () => _AGENT_METADATA,
  getCapabilities: () => _AGENT_CAPABILITIES,
  getCategories: () => _AGENT_CATEGORIES,
  getInitializers: () => _INITIALIZERS,
  clearRegistry: () => {
    _AGENT_HANDLERS.clear();
    _AGENT_METADATA.clear();
    _AGENT_CAPABILITIES.clear();
    _AGENT_CATEGORIES.clear();
    _INITIALIZERS.length = 0;
    agentInstanceManager.clearInstances();
    console.log('🧹 Agent registry cleared');
  }
};
