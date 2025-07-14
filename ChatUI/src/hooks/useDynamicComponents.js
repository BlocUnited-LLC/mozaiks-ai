/**
 * React Hook for Dynamic Component Loading
 * Uses the new registry-based component system
 */

import { useState, useEffect, useCallback } from 'react';
import { getComponent, getComponentByToolType } from '../agents/components';

/**
 * Hook for loading components dynamically from active workflow
 * @param {string} componentName - Name of the component to load
 * @param {string} context - Context (deprecated - now workflow-aware)
 * @param {Object} options - Loading options
 * @returns {Object} { component, loading, error, metadata, reload }
 */
export function useDynamicComponent(componentName, context = 'workflow', options = {}) {
  const [component, setComponent] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [metadata, setMetadata] = useState(null);

  const { preload = false } = options;

  const loadComponent = useCallback(async () => {
    if (!componentName) return;

    setLoading(true);
    setError(null);

    try {
      // Use workflow-aware component loading
      const loadedComponent = await getComponent(componentName);
      if (!loadedComponent) {
        throw new Error(`Component ${componentName} not found in active workflow`);
      }

      setComponent(loadedComponent);
      setMetadata({ name: componentName, source: 'workflow' });

    } catch (err) {
      console.error(`Failed to load component ${componentName}:`, err);
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [componentName]);

  // Load component on mount or when dependencies change
  useEffect(() => {
    if (componentName) {
      loadComponent();
    }
  }, [loadComponent, componentName]);

  // Preload if requested
  useEffect(() => {
    if (preload && componentName) {
      // Preloading is now automatic with the registry system
      console.log(`✅ Component ${componentName} preloading enabled (automatic in registry)`);
    }
  }, [preload, componentName]);

  const reload = useCallback(() => {
    loadComponent();
  }, [loadComponent]);

  return {
    component,
    loading,
    error,
    metadata,
    reload
  };
}

/**
 * Hook for loading multiple components by category
 * @param {string} category - Component category to load
 * @param {string} context - Context (deprecated, registry handles this automatically)
 * @returns {Object} { components, loading, error, reload }
 */
export function useDynamicComponentsByCategory(category, context = 'inline-component') {
  const [components, setComponents] = useState({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const loadComponents = useCallback(async () => {
    if (!category) return;

    setLoading(true);
    setError(null);

    try {
      // Workflow-aware component loading - categories are now in workflow manifests
      console.warn(`useComponentsByCategory: Category-based loading deprecated. Check workflow manifest for '${category}' components`);
      setComponents({});
    } catch (err) {
      console.error(`Failed to load components for category ${category}:`, err);
      setError(err);
    } finally {
      setLoading(false);
    }
  }, [category]);

  useEffect(() => {
    loadComponents();
  }, [loadComponents]);

  const reload = useCallback(() => {
    loadComponents();
  }, [loadComponents]);

  return {
    components,
    loading,
    error,
    reload
  };
}

/**
 * Hook for getting component registry status
 * @returns {Object} { initialized, manifest, availableComponents }
 */
export function useComponentRegistry() {
  const [registryState, setRegistryState] = useState({
    initialized: false,
    manifest: null,
    availableComponents: []
  });

  useEffect(() => {
    const checkRegistry = async () => {
      try {
        // Component registry is now workflow-specific
        console.warn('useComponentRegistry: Component metadata now comes from workflow manifests');
        
        setRegistryState({
          initialized: true,
          manifest: { source: 'workflow-manifests' },
          availableComponents: []
        });
      } catch (error) {
        console.error('Failed to check component registry:', error);
        setRegistryState({
          initialized: false,
          manifest: null,
          availableComponents: []
        });
      }
    };

    checkRegistry();
  }, []);

  return registryState;
}
