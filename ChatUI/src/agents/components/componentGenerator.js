// ==============================================================================
// FILE: agents/components/componentGenerator.js
// DESCRIPTION: Component Generator - Creates components dynamically
// ==============================================================================

/**
 * 🏗️ COMPONENT GENERATOR
 * 
 * Utility for generating React components dynamically.
 * Useful for creating wrapper components, placeholders, and error components.
 */

import React from 'react';

/**
 * Generate a placeholder component
 * @param {string} name - Component name
 * @param {Object} props - Default props
 * @returns {React.Component} - Placeholder component
 */
export const generatePlaceholderComponent = (name, props = {}) => {
  return React.forwardRef((receivedProps, ref) => {
    const combinedProps = { ...props, ...receivedProps };
    
    return (
      <div 
        ref={ref}
        className="border-2 border-dashed border-gray-400 rounded-lg p-6 text-center text-gray-500"
        {...combinedProps}
      >
        <div className="text-lg font-semibold mb-2">📦 {name}</div>
        <div className="text-sm">Component placeholder</div>
        <div className="text-xs mt-2 opacity-75">
          This component is being loaded dynamically
        </div>
      </div>
    );
  });
};

/**
 * Generate an error component
 * @param {string} name - Component name
 * @param {string} error - Error message
 * @returns {React.Component} - Error component
 */
export const generateErrorComponent = (name, error) => {
  return React.forwardRef((props, ref) => {
    return (
      <div 
        ref={ref}
        className="border border-red-400 rounded-lg p-4 text-red-400 bg-red-50"
        {...props}
      >
        <div className="font-semibold mb-2">❌ {name} - Error</div>
        <div className="text-sm">{error}</div>
        <details className="mt-2 text-xs">
          <summary className="cursor-pointer">Technical Details</summary>
          <pre className="mt-2 p-2 bg-gray-100 rounded text-gray-800 overflow-auto">
            {error}
          </pre>
        </details>
      </div>
    );
  });
};

/**
 * Generate a loading component
 * @param {string} name - Component name
 * @returns {React.Component} - Loading component
 */
export const generateLoadingComponent = (name) => {
  return React.forwardRef((props, ref) => {
    return (
      <div 
        ref={ref}
        className="border border-blue-400 rounded-lg p-4 text-blue-400 bg-blue-50"
        {...props}
      >
        <div className="flex items-center justify-center space-x-2">
          <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-400"></div>
          <span className="text-sm">Loading {name}...</span>
        </div>
      </div>
    );
  });
};

/**
 * Generate a wrapper component with error boundary
 * @param {React.Component} WrappedComponent - Component to wrap
 * @param {string} name - Component name
 * @returns {React.Component} - Wrapped component
 */
export const generateErrorBoundaryWrapper = (WrappedComponent, name) => {
  return class ErrorBoundaryWrapper extends React.Component {
    constructor(props) {
      super(props);
      this.state = { hasError: false, error: null };
    }
    
    static getDerivedStateFromError(error) {
      return { hasError: true, error };
    }
    
    componentDidCatch(error, errorInfo) {
      console.error(`Error in ${name}:`, error, errorInfo);
    }
    
    render() {
      if (this.state.hasError) {
        const ErrorComponent = generateErrorComponent(name, this.state.error?.message || 'Unknown error');
        return <ErrorComponent />;
      }
      
      return <WrappedComponent {...this.props} />;
    }
  };
};

/**
 * Generate a lazy component with loading and error states
 * @param {Function} importFunction - Dynamic import function
 * @param {string} name - Component name
 * @returns {React.Component} - Lazy component
 */
export const generateLazyComponent = (importFunction, name) => {
  const LazyComponent = React.lazy(importFunction);
  
  return React.forwardRef((props, ref) => {
    const LoadingComponent = generateLoadingComponent(name);
    const ErrorComponent = generateErrorComponent(name, 'Failed to load component');
    
    return (
      <React.Suspense fallback={<LoadingComponent />}>
        <React.ErrorBoundary fallback={<ErrorComponent />}>
          <LazyComponent {...props} ref={ref} />
        </React.ErrorBoundary>
      </React.Suspense>
    );
  });
};

/**
 * Generate a component with retry functionality
 * @param {Function} loadFunction - Function to load the component
 * @param {string} name - Component name
 * @returns {React.Component} - Component with retry
 */
export const generateRetryComponent = (loadFunction, name) => {
  return React.forwardRef((props, ref) => {
    const [component, setComponent] = React.useState(null);
    const [loading, setLoading] = React.useState(true);
    const [error, setError] = React.useState(null);
    const [retryCount, setRetryCount] = React.useState(0);
    
    const loadComponent = React.useCallback(async () => {
      try {
        setLoading(true);
        setError(null);
        const loadedComponent = await loadFunction();
        setComponent(loadedComponent);
      } catch (err) {
        setError(err);
        console.error(`Failed to load ${name}:`, err);
      } finally {
        setLoading(false);
      }
    }, [loadFunction, name]);
    
    const handleRetry = React.useCallback(() => {
      setRetryCount(prev => prev + 1);
      loadComponent();
    }, [loadComponent]);
    
    React.useEffect(() => {
      loadComponent();
    }, [loadComponent]);
    
    if (loading) {
      const LoadingComponent = generateLoadingComponent(name);
      return <LoadingComponent />;
    }
    
    if (error) {
      return (
        <div className="border border-red-400 rounded-lg p-4 text-red-400 bg-red-50">
          <div className="font-semibold mb-2">❌ {name} - Error</div>
          <div className="text-sm mb-3">{error.message}</div>
          <button 
            onClick={handleRetry}
            className="px-3 py-1 bg-red-400 text-white rounded text-sm hover:bg-red-500 transition-colors"
          >
            Retry (Attempt {retryCount + 1})
          </button>
        </div>
      );
    }
    
    if (!component) {
      const ErrorComponent = generateErrorComponent(name, 'Component not found');
      return <ErrorComponent />;
    }
    
    const Component = component;
    return <Component {...props} ref={ref} />;
  });
};

/**
 * Generate a component factory
 * @param {Object} config - Component configuration
 * @returns {React.Component} - Generated component
 */
export const generateComponent = (config) => {
  const { name, type = 'placeholder', ...options } = config;
  
  switch (type) {
    case 'placeholder':
      return generatePlaceholderComponent(name, options.props);
    case 'error':
      return generateErrorComponent(name, options.error);
    case 'loading':
      return generateLoadingComponent(name);
    case 'lazy':
      return generateLazyComponent(options.importFunction, name);
    case 'retry':
      return generateRetryComponent(options.loadFunction, name);
    default:
      console.warn(`Unknown component type: ${type}`);
      return generatePlaceholderComponent(name);
  }
};

export default {
  generatePlaceholderComponent,
  generateErrorComponent,
  generateLoadingComponent,
  generateErrorBoundaryWrapper,
  generateLazyComponent,
  generateRetryComponent,
  generateComponent
};
