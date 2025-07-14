// ==============================================================================
// FILE: agents/components/componentRegistry.js
// DESCRIPTION: Component Registry - Base functionality
// ==============================================================================

/**
 * 🎯 BASE COMPONENT REGISTRY
 * 
 * Provides base functionality for component registries.
 * Used by Inline and Artifacts registries.
 */

import { componentCache } from '../../core/dynamicComponentLoader';

/**
 * Base Component Registry class
 */
export class ComponentRegistry {
  constructor(name, basePath, manifestPath) {
    this.name = name;
    this.basePath = basePath;
    this.manifestPath = manifestPath;
    this.manifest = null;
    this.components = new Map();
    this.initialized = false;
  }
  
  /**
   * Load the component manifest
   */
  async loadManifest() {
    try {
      const manifestModule = await import(this.manifestPath);
      this.manifest = manifestModule.default || manifestModule;
      console.log(`Loaded manifest for ${this.name}:`, this.manifest);
    } catch (error) {
      console.error(`Failed to load manifest for ${this.name}:`, error);
      this.manifest = { components: {} };
    }
  }
  
  /**
   * Initialize the registry
   */
  async initialize() {
    if (this.initialized) return;
    
    await this.loadManifest();
    this.initialized = true;
    
    console.log(`${this.name} registry initialized`);
  }
  
  /**
   * Get component by name
   * @param {string} componentName - Component name
   * @returns {Promise<React.Component>} - Component or null
   */
  async getComponent(componentName) {
    if (!this.initialized) {
      await this.initialize();
    }
    
    if (!this.manifest || !this.manifest.components) {
      console.warn(`No manifest loaded for ${this.name}`);
      return null;
    }
    
    const componentConfig = this.manifest.components[componentName];
    if (!componentConfig) {
      console.warn(`Component not found in ${this.name}: ${componentName}`);
      return null;
    }
    
    try {
      const component = await componentCache.get(this.basePath, componentConfig.file);
      return component;
    } catch (error) {
      console.error(`Failed to load component ${componentName}:`, error);
      return null;
    }
  }
  
  /**
   * Get component by tool type
   * @param {string} toolType - Tool type
   * @returns {Promise<React.Component>} - Component or null
   */
  async getComponentByToolType(toolType) {
    if (!this.initialized) {
      await this.initialize();
    }
    
    if (!this.manifest || !this.manifest.components) {
      return null;
    }
    
    // Find component with matching toolType
    const componentEntry = Object.entries(this.manifest.components).find(([name, config]) => {
      return config.toolType === toolType;
    });
    
    if (!componentEntry) {
      return null;
    }
    
    const [componentName] = componentEntry;
    return this.getComponent(componentName);
  }
  
  /**
   * Get components by category
   * @param {string} category - Category name
   * @returns {Promise<Array>} - Array of components
   */
  async getComponentsByCategory(category) {
    if (!this.initialized) {
      await this.initialize();
    }
    
    if (!this.manifest || !this.manifest.components) {
      return [];
    }
    
    const components = [];
    
    for (const [name, config] of Object.entries(this.manifest.components)) {
      if (config.category === category) {
        try {
          const component = await this.getComponent(name);
          if (component) {
            components.push({ name, component, config });
          }
        } catch (error) {
          console.error(`Failed to load component ${name}:`, error);
        }
      }
    }
    
    return components;
  }
  
  /**
   * Get all available components
   * @returns {Array} - Array of component names
   */
  getAvailableComponents() {
    if (!this.manifest || !this.manifest.components) {
      return [];
    }
    
    return Object.keys(this.manifest.components);
  }
  
  /**
   * Get component manifest
   * @returns {Object} - Component manifest
   */
  getManifest() {
    return this.manifest;
  }
  
  /**
   * Check if component exists
   * @param {string} componentName - Component name
   * @returns {boolean} - True if component exists
   */
  hasComponent(componentName) {
    if (!this.manifest || !this.manifest.components) {
      return false;
    }
    
    return componentName in this.manifest.components;
  }
  
  /**
   * Get registry statistics
   * @returns {Object} - Registry statistics
   */
  getStats() {
    const totalComponents = this.manifest?.components ? Object.keys(this.manifest.components).length : 0;
    const categories = this.manifest?.components ? 
      [...new Set(Object.values(this.manifest.components).map(c => c.category))] : [];
    
    return {
      name: this.name,
      basePath: this.basePath,
      initialized: this.initialized,
      totalComponents,
      categories: categories.length,
      categoryList: categories
    };
  }
}

export default ComponentRegistry;
