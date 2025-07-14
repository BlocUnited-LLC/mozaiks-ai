// ==============================================================================
// FILE: core/pluginRegistry.js
// DESCRIPTION: Plugin Registry System
// ==============================================================================

/**
 * 🔌 PLUGIN REGISTRY SYSTEM
 * 
 * Manages plugins for the ChatUI system. Plugins can provide:
 * - UI components
 * - Transport adapters
 * - Agent capabilities
 * - Workflow processors
 */

/**
 * Plugin Registry class
 */
class PluginRegistry {
  constructor() {
    this.plugins = new Map();
    this.categories = new Map();
    this.initialized = false;
  }
  
  /**
   * Register a plugin
   * @param {string} name - Plugin name
   * @param {Object} plugin - Plugin object
   * @param {Object} options - Plugin options
   */
  register(name, plugin, options = {}) {
    if (this.plugins.has(name)) {
      console.warn(`Plugin ${name} is already registered. Overwriting...`);
    }
    
    const pluginConfig = {
      name,
      plugin,
      options,
      category: options.category || 'general',
      version: options.version || '1.0.0',
      description: options.description || '',
      dependencies: options.dependencies || [],
      registered: new Date(),
      enabled: options.enabled !== false
    };
    
    this.plugins.set(name, pluginConfig);
    
    // Add to category
    const category = pluginConfig.category;
    if (!this.categories.has(category)) {
      this.categories.set(category, new Set());
    }
    this.categories.get(category).add(name);
    
    console.log(`Plugin registered: ${name} (${category})`);
    
    // Initialize plugin if registry is already initialized
    if (this.initialized && pluginConfig.enabled) {
      this.initializePlugin(pluginConfig);
    }
  }
  
  /**
   * Get a plugin by name
   * @param {string} name - Plugin name
   * @returns {Object|null} - Plugin configuration or null
   */
  get(name) {
    return this.plugins.get(name) || null;
  }
  
  /**
   * Get all plugins
   * @returns {Array} - Array of plugin configurations
   */
  getAll() {
    return Array.from(this.plugins.values());
  }
  
  /**
   * Get plugins by category
   * @param {string} category - Category name
   * @returns {Array} - Array of plugin configurations
   */
  getByCategory(category) {
    const pluginNames = this.categories.get(category);
    if (!pluginNames) return [];
    
    return Array.from(pluginNames)
      .map(name => this.plugins.get(name))
      .filter(plugin => plugin && plugin.enabled);
  }
  
  /**
   * Enable a plugin
   * @param {string} name - Plugin name
   */
  enable(name) {
    const plugin = this.plugins.get(name);
    if (!plugin) {
      console.warn(`Plugin not found: ${name}`);
      return;
    }
    
    plugin.enabled = true;
    if (this.initialized) {
      this.initializePlugin(plugin);
    }
  }
  
  /**
   * Disable a plugin
   * @param {string} name - Plugin name
   */
  disable(name) {
    const plugin = this.plugins.get(name);
    if (!plugin) {
      console.warn(`Plugin not found: ${name}`);
      return;
    }
    
    plugin.enabled = false;
    if (plugin.plugin.destroy) {
      plugin.plugin.destroy();
    }
  }
  
  /**
   * Initialize a single plugin
   * @param {Object} pluginConfig - Plugin configuration
   */
  async initializePlugin(pluginConfig) {
    try {
      if (pluginConfig.plugin.initialize) {
        await pluginConfig.plugin.initialize(pluginConfig.options);
      }
      console.log(`Plugin initialized: ${pluginConfig.name}`);
    } catch (error) {
      console.error(`Failed to initialize plugin ${pluginConfig.name}:`, error);
    }
  }
  
  /**
   * Initialize all enabled plugins
   */
  async initialize() {
    if (this.initialized) return;
    
    const enabledPlugins = this.getAll().filter(plugin => plugin.enabled);
    
    // Sort by dependencies (basic dependency resolution)
    const sortedPlugins = this.sortByDependencies(enabledPlugins);
    
    for (const plugin of sortedPlugins) {
      await this.initializePlugin(plugin);
    }
    
    this.initialized = true;
    console.log(`Plugin registry initialized with ${enabledPlugins.length} plugins`);
  }
  
  /**
   * Sort plugins by dependencies (basic topological sort)
   * @param {Array} plugins - Array of plugin configurations
   * @returns {Array} - Sorted array of plugin configurations
   */
  sortByDependencies(plugins) {
    const sorted = [];
    const visited = new Set();
    const visiting = new Set();
    
    const visit = (plugin) => {
      if (visited.has(plugin.name)) return;
      if (visiting.has(plugin.name)) {
        console.warn(`Circular dependency detected for plugin: ${plugin.name}`);
        return;
      }
      
      visiting.add(plugin.name);
      
      // Visit dependencies first
      for (const dep of plugin.dependencies) {
        const depPlugin = plugins.find(p => p.name === dep);
        if (depPlugin) {
          visit(depPlugin);
        }
      }
      
      visiting.delete(plugin.name);
      visited.add(plugin.name);
      sorted.push(plugin);
    };
    
    for (const plugin of plugins) {
      visit(plugin);
    }
    
    return sorted;
  }
  
  /**
   * Unregister a plugin
   * @param {string} name - Plugin name
   */
  unregister(name) {
    const plugin = this.plugins.get(name);
    if (!plugin) return;
    
    if (plugin.enabled && plugin.plugin.destroy) {
      plugin.plugin.destroy();
    }
    
    this.plugins.delete(name);
    
    // Remove from category
    const category = plugin.category;
    if (this.categories.has(category)) {
      this.categories.get(category).delete(name);
      if (this.categories.get(category).size === 0) {
        this.categories.delete(category);
      }
    }
    
    console.log(`Plugin unregistered: ${name}`);
  }
  
  /**
   * Get plugin categories
   * @returns {Array} - Array of category names
   */
  getCategories() {
    return Array.from(this.categories.keys());
  }
  
  /**
   * Check if a plugin is registered
   * @param {string} name - Plugin name
   * @returns {boolean} - True if registered
   */
  has(name) {
    return this.plugins.has(name);
  }
  
  /**
   * Get registry statistics
   * @returns {Object} - Registry statistics
   */
  getStats() {
    const total = this.plugins.size;
    const enabled = this.getAll().filter(p => p.enabled).length;
    const categories = this.getCategories().length;
    
    return {
      total,
      enabled,
      disabled: total - enabled,
      categories,
      initialized: this.initialized
    };
  }
}

// Global plugin registry instance
export const pluginRegistry = new PluginRegistry();

// Convenience functions
export const registerPlugin = (name, plugin, options) => pluginRegistry.register(name, plugin, options);
export const getPlugin = (name) => pluginRegistry.get(name);
export const getAllPlugins = () => pluginRegistry.getAll();
export const getPluginsByCategory = (category) => pluginRegistry.getByCategory(category);
export const enablePlugin = (name) => pluginRegistry.enable(name);
export const disablePlugin = (name) => pluginRegistry.disable(name);
export const initializePlugins = () => pluginRegistry.initialize();

export default pluginRegistry;
