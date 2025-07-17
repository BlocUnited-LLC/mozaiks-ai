// ==============================================================================
// FILE: agents/index.js
// DESCRIPTION: Agent System - Workflow-Based Component Discovery
// ==============================================================================

/**
 * 🎯 WORKFLOW-DRIVEN AGENT SYSTEM
 * 
 * This file provides a unified interface to the agent system using
 * backend workflow.json for component discovery.
 */

// ============================================================================
// CORE AGENT SYSTEM - WORKFLOW BASED
// ============================================================================

// Simplified agent system - components come from backend workflow
const agentRegistry = new Map();
const agentCapabilities = new Map();
const agentInitializers = [];

// Local registration system for frontend agent handlers
export const registerAgent = (name, handler) => {
  agentRegistry.set(name, handler);
};

export const registerAgentCapabilities = (agentName, capabilities) => {
  agentCapabilities.set(agentName, capabilities);
};

export const addAgentInitializer = (initializer) => {
  agentInitializers.push(initializer);
};

// Agent access and discovery
export const getAgent = (name) => {
  return agentRegistry.get(name);
};

export const getAgentHandler = (name) => {
  return agentRegistry.get(name);
};

export const getAllAgents = () => {
  return Array.from(agentRegistry.keys());
};

export const getAgentsByCapability = (capability) => {
  const agents = [];
  for (const [agentName, capabilities] of agentCapabilities) {
    if (capabilities.includes(capability)) {
      agents.push(agentName);
    }
  }
  return agents;
};

export const getAgentsByCategory = () => {
  console.warn('getAgentsByCategory: Use backend workflow.json for component discovery');
  return [];
};

export const getAgentManifest = () => {
  console.warn('getAgentManifest: Use backend workflow.json for component discovery');
  return { source: 'workflow-based' };
};

// System management
export const initializeAgents = async () => {
  console.log('🚀 Initializing workflow-based agent system...');
  for (const initializer of agentInitializers) {
    try {
      await initializer();
    } catch (error) {
      console.error('Agent initializer failed:', error);
    }
  }
  return true;
};

export const discoverAgents = async () => {
  console.warn('discoverAgents: Use backend workflow.json for component discovery');
  return [];
};

// Base classes for agent development (simplified)
export class BaseAgent {
  constructor(name, capabilities = []) {
    this.name = name;
    this.capabilities = capabilities;
  }
}

export class InteractiveAgent extends BaseAgent {
  constructor(name, capabilities = []) {
    super(name, [...capabilities, 'interactive']);
  }
}

export class StatelessAgent extends BaseAgent {
  constructor(name, capabilities = []) {
    super(name, [...capabilities, 'stateless']);
  }
}

// Constants and utilities
export const AgentCapabilities = {
  UI_CAPABLE: 'ui_capable',
  API_CAPABLE: 'api_capable',
  WORKFLOW_CAPABLE: 'workflow_capable'
};

export const AgentCategories = {
  GENERATOR: 'generator',
  ANALYZER: 'analyzer',
  TRANSFORMER: 'transformer'
};

export const TransportTypes = {
  WEBSOCKET: 'websocket',
  SSE: 'sse',
  HTTP: 'http'
};

// Component Registry - For UI components (uses workflow system)
export { default as componentRegistry } from './components';

// Unified component access
export { 
  getComponent, 
  getComponentByToolType, 
  getComponentsByCategory,
  initializeComponents
} from './components';

// Dynamic Component Loading (updated to use registry system)
export { useDynamicComponent, useDynamicComponentsByCategory, useComponentRegistry } from '../hooks/useDynamicComponents';

// ============================================================================
// REGISTRY-BASED COMPONENT LOADING
// ============================================================================

/**
 * 🔍 COMPONENT DISCOVERY HELPERS
 * 
 * These functions help discover and load components dynamically.
 */

// Get a component by name (async)
export const loadComponent = async (componentName) => {
  const { getComponent } = await import('./components');
  return await getComponent(componentName);
};

// Get a component for a specific tool type (async)
export const loadComponentForTool = async (toolType) => {
  const { getComponentByToolType } = await import('./components');
  return await getComponentByToolType(toolType);
};

// Get all components in a category (async)
export const loadComponentsByCategory = async (category) => {
  const { getComponentsByCategory } = await import('./components');
  return await getComponentsByCategory(category);
};

/**
 * 🎨 REACT INTEGRATION
 * 
 * React hook for loading components dynamically.
 */
export const useAgentComponent = (componentName) => {
  const { useDynamicComponent } = require('../hooks/useDynamicComponents');
  return useDynamicComponent(componentName);
};

// ============================================================================
// AGENT SYSTEM INITIALIZATION
// ============================================================================

/**
 * Initialize the agent system
 * Call this once during application startup
 */
export async function initializeAgentSystem() {
  console.log('🚀 Initializing ChatUI Agent System...');
  
  try {
    // Use local functions instead of registry imports
    await discoverAgents();
    await initializeAgents();
    
    // Initialize component registry
    const { initializeComponents } = await import('./components');
    await initializeComponents();
    
    console.log('✅ Agent system initialized successfully');
    return true;
  } catch (error) {
    console.error('❌ Failed to initialize agent system:', error);
    return false;
  }
}

// ============================================================================
// DEVELOPER UTILITIES
// ============================================================================

// Development utilities
if (process.env.NODE_ENV === 'development') {
  window.ChatUIAgents = {
    getAllAgents,
    getAgentsByCapability,
    agentRegistry
  };
}

// Default export - the agent system
const agentSystem = {
  // Core functions
  getAllAgents,
  getAgentsByCapability,
  initializeAgentSystem,
  
  // Agent classes
  BaseAgent,
  InteractiveAgent,
  StatelessAgent,
  
  // Constants
  AgentCapabilities,
  AgentCategories,
  TransportTypes
};

export default agentSystem;
