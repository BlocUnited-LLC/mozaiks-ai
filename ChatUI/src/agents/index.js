// ==============================================================================
// FILE: agents/index.js
// DESCRIPTION: Agent System - Registry-Based Component Discovery
// ==============================================================================

/**
 * 🎯 REGISTRY-DRIVEN AGENT SYSTEM
 * 
 * This file provides a unified interface to the agent system using
 * JSON-driven component discovery. No hardcoded component imports.
 */

// ============================================================================
// CORE AGENT SYSTEM (STABLE - DO NOT MODIFY)
// ============================================================================

// Agent Registry System - The heart of dynamic agent management
export {
  // Registration system
  registerAgent,
  registerAgentCapabilities,
  addAgentInitializer,
  
  // Agent access and discovery
  getAgent,
  getAgentHandler,
  getAllAgents,
  getAgentsByCapability,
  getAgentsByCategory,
  getAgentManifest,
  
  // System management
  initializeAgents,
  discoverAgents,
  
  // Base classes for agent development
  BaseAgent,
  InteractiveAgent,
  StatelessAgent,
  
  // Constants and utilities
  AgentCapabilities,
  AgentCategories,
  TransportTypes
} from './registry';

// Component Registry - For UI components (uses new registry system)
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
    // Import functions we need
    const { discoverAgents, initializeAgents } = await import('./registry');
    const { initializeComponents } = await import('./components');
    
    // Run auto-discovery
    await discoverAgents();
    
    // Initialize all agents
    const result = await initializeAgents();
    
    // Initialize component registry
    await initializeComponents();
    
    console.log('✅ ChatUI Agent System initialized successfully');
    return result;
    
  } catch (error) {
    console.error('❌ ChatUI Agent System initialization failed:', error);
    throw error;
  }
}

// ============================================================================
// DEVELOPER UTILITIES
// ============================================================================

/**
 * Development mode utilities
 * Only available in development builds
 */
export const dev = {
  // Registry inspection
  inspectRegistry: async () => {
    if (process.env.NODE_ENV !== 'development') {
      console.warn('Registry inspection only available in development');
      return null;
    }
    const { getAgentManifest } = await import('./registry');
    return getAgentManifest();
  },
  
  // Manual agent discovery
  rediscoverAgents: async (paths) => {
    if (process.env.NODE_ENV !== 'development') {
      console.warn('Manual discovery only available in development');
      return;
    }
    const { triggerAgentDiscovery } = await import('./registry/agentDiscovery');
    return triggerAgentDiscovery(paths);
  },
  
  // Registry debugging
  debugRegistry: () => {
    if (process.env.NODE_ENV !== 'development') {
      console.warn('Registry debugging only available in development');
      return;
    }
    const { debug } = require('./registry');
    return debug;
  }
};

// Default export - the registry system
export default {
  // Core functions
  loadComponent,
  loadComponentForTool,
  loadComponentsByCategory,
  
  // Registry access (async imports)
  getComponent: async (name) => {
    const { getComponent } = await import('./components');
    return getComponent(name);
  },
  getComponentByToolType: async (type) => {
    const { getComponentByToolType } = await import('./components');
    return getComponentByToolType(type);
  },
  getComponentsByCategory: async (category) => {
    const { getComponentsByCategory } = await import('./components');
    return getComponentsByCategory(category);
  },
  
  // Initialization
  initializeAgentSystem,
  
  // React integration
  useAgentComponent,
  
  // Direct registry access (async)
  componentRegistry: async () => {
    const { default: componentRegistry } = await import('./components');
    return componentRegistry;
  }
};
