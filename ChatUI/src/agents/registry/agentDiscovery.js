// ==============================================================================
// FILE: agents/registry/agentDiscovery.js
// DESCRIPTION: Auto-discovery system for agents - mirrors workflow discovery
// ==============================================================================

import { addAgentInitializer } from './agentRegistry.js';

/**
 * Agent auto-discovery system
 * Mirrors the Python workflow auto-discovery pattern
 */

/**
 * Discover and auto-register agents from specified directories
 */
export async function discoverAgents(discoveryPaths = []) {
  const defaultPaths = [
    '../instances/**/*.js',
    '../plugins/**/*.js'
  ];
  
  const paths = discoveryPaths.length > 0 ? discoveryPaths : defaultPaths;
  
  console.log('🔍 Starting agent auto-discovery...', { paths });
  
  const discovered = {
    agents: [],
    errors: [],
    skipped: []
  };

  for (const pattern of paths) {
    try {
      await discoverFromPattern(pattern, discovered);
    } catch (error) {
      console.error(`Discovery failed for pattern: ${pattern}`, error);
      discovered.errors.push({ pattern, error: error.message });
    }
  }

  console.log('🎯 Agent discovery complete:', {
    found: discovered.agents.length,
    errors: discovered.errors.length,
    skipped: discovered.skipped.length
  });

  return discovered;
}

/**
 * Discover agents from a specific glob pattern
 */
async function discoverFromPattern(pattern, discovered) {
  try {
    // Skip glob pattern discovery in browser environment
    if (typeof window !== 'undefined') {
      console.log(`⚠️ Skipping glob pattern discovery in browser: ${pattern}`);
      return;
    }
    
    // Use Vite's import.meta.glob for dynamic imports (only in Node.js-like environments)
    const modules = import.meta.glob(pattern, { eager: false });
    
    for (const [path, moduleLoader] of Object.entries(modules)) {
      try {
        const module = await moduleLoader();
        await processModule(module, path, discovered);
      } catch (error) {
        console.warn(`Failed to load module: ${path}`, error);
        discovered.errors.push({ path, error: error.message });
      }
    }
  } catch (error) {
    console.error(`Pattern discovery failed: ${pattern}`, error);
    throw error;
  }
}

/**
 * Process a discovered module for agent registration
 */
async function processModule(module, modulePath, discovered) {
  // Check for agent export patterns
  const agentExports = findAgentExports(module);
  
  if (agentExports.length === 0) {
    discovered.skipped.push({ 
      path: modulePath, 
      reason: 'No agent exports found' 
    });
    return;
  }

  for (const agentExport of agentExports) {
    try {
      const agentInfo = await registerDiscoveredAgent(agentExport, modulePath);
      discovered.agents.push(agentInfo);
      console.log(`📦 Auto-registered agent: ${agentInfo.type} from ${modulePath}`);
    } catch (error) {
      console.error(`Failed to register agent from ${modulePath}:`, error);
      discovered.errors.push({ 
        path: modulePath, 
        agent: agentExport.name,
        error: error.message 
      });
    }
  }
}

/**
 * Find agent exports in a module
 */
function findAgentExports(module) {
  const exports = [];
  
  // Check default export
  if (module.default && isAgentClass(module.default)) {
    exports.push({
      name: 'default',
      agentClass: module.default,
      metadata: extractAgentMetadata(module.default)
    });
  }
  
  // Check named exports
  for (const [name, exportValue] of Object.entries(module)) {
    if (name !== 'default' && isAgentClass(exportValue)) {
      exports.push({
        name,
        agentClass: exportValue,
        metadata: extractAgentMetadata(exportValue)
      });
    }
  }
  
  return exports;
}

/**
 * Check if a value is an agent class
 */
function isAgentClass(value) {
  if (typeof value !== 'function') return false;
  
  // Check for agent-like properties
  const agentIndicators = [
    'processMessage',
    'handleAction', 
    'agentType',
    'capabilities',
    'category'
  ];
  
  // Check prototype for methods
  const hasAgentMethods = agentIndicators.some(prop => 
    value.prototype && typeof value.prototype[prop] === 'function'
  );
  
  // Check static properties
  const hasAgentStatics = agentIndicators.some(prop => 
    value.hasOwnProperty(prop)
  );
  
  return hasAgentMethods || hasAgentStatics;
}

/**
 * Extract metadata from agent class
 */
function extractAgentMetadata(agentClass) {
  const metadata = {};
  
  // Extract static properties
  const staticProps = [
    'agentType', 'capabilities', 'category', 'description',
    'version', 'author', 'transport', 'interactive', 'priority'
  ];
  
  for (const prop of staticProps) {
    if (agentClass.hasOwnProperty(prop)) {
      metadata[prop] = agentClass[prop];
    }
  }
  
  // Try to extract from prototype
  if (agentClass.prototype) {
    for (const prop of staticProps) {
      if (agentClass.prototype[prop] !== undefined) {
        metadata[prop] = agentClass.prototype[prop];
      }
    }
  }
  
  // Defaults
  metadata.agentType = metadata.agentType || agentClass.name || 'unknown';
  metadata.capabilities = metadata.capabilities || [];
  metadata.category = metadata.category || 'general';
  metadata.interactive = metadata.interactive !== false; // default true
  metadata.transport = metadata.transport || 'websocket';
  metadata.priority = metadata.priority || 50;
  
  return metadata;
}

/**
 * Register a discovered agent with automatic metadata
 */
async function registerDiscoveredAgent(agentExport, modulePath) {
  const { agentClass, metadata } = agentExport;
  
  // Use registerAgent to properly register
  const { registerAgent } = await import('./agentRegistry.js');
  
  // Create registration options
  const registrationOptions = {
    ...metadata,
    discoveredFrom: modulePath,
    autoDiscovered: true
  };
  
  // Apply the registration decorator
  const registeredClass = registerAgent(metadata.agentType, registrationOptions)(agentClass);
  
  return {
    type: metadata.agentType,
    class: registeredClass,
    metadata: registrationOptions,
    source: modulePath
  };
}

/**
 * Auto-discovery initializer - runs during system startup
 */
export const autoDiscoveryInitializer = addAgentInitializer(async function agentAutoDiscovery() {
  console.log('🔄 Running agent auto-discovery...');
  
  try {
    const result = await discoverAgents();
    
    if (result.errors.length > 0) {
      console.warn('⚠️ Agent discovery completed with errors:', result.errors);
    } else {
      console.log('✅ Agent auto-discovery completed successfully');
    }
    
    return result;
  } catch (error) {
    console.error('❌ Agent auto-discovery failed:', error);
    throw error;
  }
});

/**
 * Manual discovery trigger for development
 */
export async function triggerAgentDiscovery(paths) {
  console.log('🔧 Manual agent discovery triggered');
  return discoverAgents(paths);
}
