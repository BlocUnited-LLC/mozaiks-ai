// ==============================================================================
// FILE: core/dynamicComponentLoader.js
// DESCRIPTION: Dynamic Component Loading System
// ==============================================================================

/**
 * 🚀 DYNAMIC COMPONENT LOADER
 * 
 * Handles dynamic imports and component loading for the registry system.
 * Provides utilities for safely loading components with error handling.
 */

import React from 'react';

/**
 * Dynamically import a component from a given path
 * @param {string} basePath - Base path for the component
 * @param {string} fileName - Component file name
 * @returns {Promise<React.Component>} - The loaded component
 */
export const loadComponent = async (basePath, fileName) => {
  try {
    // Construct the full path
    const fullPath = `${basePath}/${fileName}`;
    
    // Dynamic import
    const module = await import(fullPath);
    
    // Return the default export or named export
    return module.default || module;
  } catch (error) {
    console.error(`Failed to load component: ${basePath}/${fileName}`, error);
    return null;
  }
};

/**
 * Load component with fallback
 * @param {string} componentName - Name of the component
 * @param {string} basePath - Base path for the component
 * @param {string} fileName - Component file name
 * @returns {Promise<React.Component>} - The loaded component or fallback
 */
export const loadComponentWithFallback = async (componentName, basePath, fileName) => {
  const component = await loadComponent(basePath, fileName);
  
  if (!component) {
    // Return a fallback component
    return ({ children, ...props }) => (
      <div className="text-red-400 text-sm p-4 border border-red-400 rounded">
        <div className="font-semibold">Component Load Error</div>
        <div>Failed to load: {componentName}</div>
        <div className="text-xs mt-2">Path: {basePath}/{fileName}</div>
        {children}
      </div>
    );
  }
  
  return component;
};

/**
 * Batch load components
 * @param {Array} componentConfigs - Array of {basePath, fileName, name} objects
 * @returns {Promise<Object>} - Object with component names as keys and components as values
 */
export const loadComponentBatch = async (componentConfigs) => {
  const results = {};
  
  const loadPromises = componentConfigs.map(async (config) => {
    const { basePath, fileName, name } = config;
    const component = await loadComponent(basePath, fileName);
    return { name, component };
  });
  
  const loadedComponents = await Promise.all(loadPromises);
  
  loadedComponents.forEach(({ name, component }) => {
    results[name] = component;
  });
  
  return results;
};

/**
 * Create a lazy-loaded component wrapper
 * @param {string} basePath - Base path for the component
 * @param {string} fileName - Component file name
 * @returns {React.LazyExoticComponent} - Lazy component
 */
export const createLazyComponent = (basePath, fileName) => {
  return React.lazy(() => loadComponent(basePath, fileName));
};

/**
 * Component loader with caching
 */
class ComponentCache {
  constructor() {
    this.cache = new Map();
    this.loadingPromises = new Map();
  }
  
  async get(basePath, fileName) {
    const key = `${basePath}/${fileName}`;
    
    // Return cached component if available
    if (this.cache.has(key)) {
      return this.cache.get(key);
    }
    
    // Return existing loading promise if component is being loaded
    if (this.loadingPromises.has(key)) {
      return this.loadingPromises.get(key);
    }
    
    // Load component
    const loadPromise = loadComponent(basePath, fileName);
    this.loadingPromises.set(key, loadPromise);
    
    try {
      const component = await loadPromise;
      this.cache.set(key, component);
      this.loadingPromises.delete(key);
      return component;
    } catch (error) {
      this.loadingPromises.delete(key);
      throw error;
    }
  }
  
  clear() {
    this.cache.clear();
    this.loadingPromises.clear();
  }
  
  has(basePath, fileName) {
    const key = `${basePath}/${fileName}`;
    return this.cache.has(key);
  }
}

// Global component cache instance
export const componentCache = new ComponentCache();

/**
 * Load component with caching
 * @param {string} basePath - Base path for the component
 * @param {string} fileName - Component file name
 * @returns {Promise<React.Component>} - The cached or loaded component
 */
export const loadComponentCached = async (basePath, fileName) => {
  return componentCache.get(basePath, fileName);
};

export default {
  loadComponent,
  loadComponentWithFallback,
  loadComponentBatch,
  createLazyComponent,
  componentCache,
  loadComponentCached
};
