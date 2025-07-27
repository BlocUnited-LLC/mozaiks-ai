// ==============================================================================
// FILE: ChatUI/src/uiToolRegistry.js
// DESCRIPTION: Central registry for workflow UI tools/components
// ==============================================================================

/**
 * Central UI Tool Registry
 * 
 * Workflow-agnostic registry that maps toolIds to React components.
 * Each workflow registers its own components using registerUiTool().
 */

class UiToolRegistry {
  constructor() {
    this.registry = new Map();
    this.metadata = new Map(); // Store component metadata
    this.initialized = false;
  }

  /**
   * Register a UI tool component
   * @param {string} toolId - Unique identifier for the tool (e.g., 'api_key_input')
   * @param {React.Component} component - React component to render
   * @param {Object} metadata - Optional metadata about the component
   */
  registerUiTool(toolId, component, metadata = {}) {
    if (!toolId || !component) {
      console.error('❌ UiToolRegistry: toolId and component are required');
      return;
    }

    if (this.registry.has(toolId)) {
      console.warn(`⚠️ UiToolRegistry: Overwriting existing tool: ${toolId}`);
    }

    this.registry.set(toolId, component);
    this.metadata.set(toolId, {
      toolId,
      registeredAt: new Date().toISOString(),
      componentName: component.name || component.displayName || 'Anonymous',
      ...metadata
    });

    console.log(`✅ UiToolRegistry: Registered tool '${toolId}' -> ${this.metadata.get(toolId).componentName}`);
  }

  /**
   * Get a UI tool component by toolId
   * @param {string} toolId - Tool identifier
   * @returns {React.Component|null} - The registered component or null
   */
  getUiToolComponent(toolId) {
    const component = this.registry.get(toolId);
    if (!component) {
      console.warn(`⚠️ UiToolRegistry: Tool '${toolId}' not found`);
      return null;
    }
    return component;
  }

  /**
   * Get metadata for a tool
   * @param {string} toolId - Tool identifier
   * @returns {Object|null} - Tool metadata or null
   */
  getToolMetadata(toolId) {
    return this.metadata.get(toolId) || null;
  }

  /**
   * Get all registered tool IDs
   * @returns {string[]} - Array of registered tool IDs
   */
  getAllToolIds() {
    return Array.from(this.registry.keys());
  }

  /**
   * Get registry stats
   * @returns {Object} - Registry statistics
   */
  getStats() {
    return {
      totalTools: this.registry.size,
      registeredTools: this.getAllToolIds(),
      initialized: this.initialized
    };
  }

  /**
   * Unregister a tool (useful for cleanup)
   * @param {string} toolId - Tool identifier to remove
   */
  unregisterUiTool(toolId) {
    const removed = this.registry.delete(toolId);
    this.metadata.delete(toolId);
    
    if (removed) {
      console.log(`🗑️ UiToolRegistry: Unregistered tool '${toolId}'`);
    }
    
    return removed;
  }

  /**
   * Clear all registered tools
   */
  clear() {
    const count = this.registry.size;
    this.registry.clear();
    this.metadata.clear();
    console.log(`🧹 UiToolRegistry: Cleared ${count} tools`);
  }

  /**
   * Mark registry as initialized
   */
  markInitialized() {
    this.initialized = true;
    console.log(`🚀 UiToolRegistry: Initialized with ${this.registry.size} tools`);
  }
}

// Create singleton instance
const uiToolRegistry = new UiToolRegistry();

// Export both the instance and individual methods for convenience
export default uiToolRegistry;

export const registerUiTool = (toolId, component, metadata) => 
  uiToolRegistry.registerUiTool(toolId, component, metadata);

export const getUiToolComponent = (toolId) => 
  uiToolRegistry.getUiToolComponent(toolId);

export const getToolMetadata = (toolId) => 
  uiToolRegistry.getToolMetadata(toolId);

export const getAllToolIds = () => 
  uiToolRegistry.getAllToolIds();

export const getRegistryStats = () => 
  uiToolRegistry.getStats();
