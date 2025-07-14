// ==============================================================================
// FILE: agents/registry/index.js
// DESCRIPTION: Export all registry functionality - mirrors core/workflow/__init__.py
// ==============================================================================

// Core registry functions - mirrors Python init_registry exports
export {
  // Registration decorators
  registerAgent,
  registerAgentCapabilities,
  addAgentInitializer,
  
  // Agent access
  getAgent,
  getAgentHandler,
  getAgentMetadata,
  
  // Discovery and querying
  getAllAgents,
  getAgentsByCapability,
  getAgentsByCategory,
  getAgentTransport,
  getAllCapabilities,
  
  // System management
  initializeAgents,
  getAgentManifest,
  
  // Instance management
  agentInstanceManager,
  
  // Debug utilities
  debug
} from './agentRegistry.js';

// Auto-discovery system
export { discoverAgents } from './agentDiscovery.js';

// Agent base classes and interfaces
export { BaseAgent, InteractiveAgent, StatelessAgent } from './agentBase.js';

// Agent constants and utilities
export { 
  AgentCapabilities,
  AgentCategories,
  TransportTypes,
  agentMetadata,
  capabilities,
  category,
  transport
} from './agentBase.js';
