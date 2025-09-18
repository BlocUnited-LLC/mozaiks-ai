// ==============================================================================
// FILE: ChatUI/src/core/WorkflowUIRouter.js
// DESCRIPTION: Dynamic router for workflow-specific UI components
// PURPOSE: Dynamically discover and route UI tool events to any workflow
// ==============================================================================

import React from 'react';

/**
 * 🎯 WORKFLOW UI ROUTER - TRULY MODULAR
 * 
 * This core system dynamically discovers and routes UI tool events to the 
 * correct workflow-specific components without hardcoding any workflows.
 * 
 * DYNAMIC ARCHITECTURE:
 * 1. Receives UI tool event with workflow_name and component_type
 * 2. Dynamically imports the workflow's components  
 * 3. Renders the specific component for that workflow
 * 4. Handles responses back to the agent
 * 
 * NO HARDCODED WORKFLOWS - Completely modular and discoverable!
 */

// Cache for loaded workflow component modules
const componentCache = new Map();

const WorkflowUIRouter = ({ 
  payload, 
  onResponse, 
  onCancel,
  submitInputRequest,
  ui_tool_id,
  eventId
}) => {
  const [Component, setComponent] = React.useState(null);
  const [error, setError] = React.useState(null);
  const [isLoading, setIsLoading] = React.useState(true);

  // Extract routing information from payload
  const workflowName = payload?.workflow || payload?.workflow_name || 'Unknown';
  const componentType = payload?.component_type || 'UnknownComponent';
  
  /**
   * Dynamically load workflow component - NO HARDCODING
   */
  const loadWorkflowComponent = React.useCallback(async (workflow, component) => {
    try {
      setIsLoading(true);
      setError(null);
      console.log('🛰️ WorkflowUIRouter: Loading component', { workflow, component });
      // Derive chat-specific cache key (include cache_seed if present in localStorage)
      let chatId = null;
      try { chatId = localStorage.getItem('mozaiks.current_chat_id'); } catch {}
      let cacheSeed = null;
      if (chatId) {
        try { const storedSeed = localStorage.getItem(`mozaiks.current_chat_id.cache_seed.${chatId}`); if (storedSeed) cacheSeed = storedSeed; } catch {}
      }
      const cacheKey = `${chatId || 'nochat'}:${cacheSeed || 'noseed'}:${workflow}:${component}`;
      
      // Check cache first
      if (componentCache.has(cacheKey)) {
        console.log('🛰️ WorkflowUIRouter: Cache hit', { cacheKey });
        setComponent(componentCache.get(cacheKey));
        setIsLoading(false);
        return;
      }

      // Dynamically import the workflow's component index
      const workflowModule = await import(`../workflows/${workflow}/components/index.js`);
      
      // Get the specific component from the workflow module
      const WorkflowComponent = workflowModule.default[component] || workflowModule[component];
      
      if (!WorkflowComponent) {
        throw new Error(`Component '${component}' not found in workflow '${workflow}'`);
      }
      
      // Cache the component
  componentCache.set(cacheKey, WorkflowComponent);
      setComponent(() => WorkflowComponent);
      
      console.log(`✅ WorkflowUIRouter: Loaded ${workflow}:${component}`);
      
    } catch (loadError) {
      console.warn(`⚠️ WorkflowUIRouter: Failed to load ${workflow}:${component}, trying core components`, loadError);
      
      // Fallback to core components (F5: UserInputRequest support)
      try {
        const coreModule = await import('./ui/index.js');
        const coreComponents = {
          'UserInputRequest': coreModule.UserInputRequest,
          'user_input': coreModule.UserInputRequest, // Map user_input to UserInputRequest
        };
        
        const coreComponent = coreComponents[component] || coreComponents[ui_tool_id];
        if (coreComponent) {
          console.log(`✅ WorkflowUIRouter: Using core component ${component || ui_tool_id}`);
          setComponent(() => coreComponent);
          setIsLoading(false);
          return;
        }
      } catch (coreError) {
        console.warn(`⚠️ WorkflowUIRouter: Failed to load core components`, coreError);
      }
      
      // No fallback found
      setError({
        type: 'component_not_found',
        workflow,
        component,
        message: loadError.message
      });
    } finally {
      setIsLoading(false);
    }
  }, [ui_tool_id]); // useCallback dependencies - include ui_tool_id since it's used in the function

  React.useEffect(() => {
    loadWorkflowComponent(workflowName, componentType);
  }, [workflowName, componentType, loadWorkflowComponent]);

  // Loading state
  if (isLoading) {
    return (
      <div className="workflow-ui-loading p-4 bg-gray-800 border border-gray-600 rounded">
        <div className="flex items-center space-x-2">
          <div className="animate-spin h-4 w-4 border-2 border-blue-500 border-t-transparent rounded-full"></div>
          <span className="text-gray-300">Loading {workflowName}:{componentType}...</span>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="workflow-ui-error bg-red-900 border border-red-500 rounded p-4">
        <h3 className="text-red-400 font-semibold mb-2">UI Component Error</h3>
        <p className="text-red-300 text-sm mb-2">
          Could not load component <code>{error.component}</code> from workflow <code>{error.workflow}</code>
        </p>
        <p className="text-red-400 text-xs mb-3">{error.message}</p>
        
        <div className="text-yellow-300 text-xs mb-3">
          <p><strong>Expected structure:</strong></p>
          <code className="block bg-gray-800 p-2 rounded text-xs">
            workflows/{error.workflow}/components/index.js<br/>
            ↳ export {'{'}  {error.component} {'}'};
          </code>
        </div>
        
        <button 
          onClick={() => onCancel?.({ status: 'error', error: 'Component not found' })}
          className="px-3 py-1 bg-red-700 hover:bg-red-600 rounded text-sm"
        >
          Close
        </button>
      </div>
    );
  }

  // Success state - render the dynamically loaded component
  console.log('🛰️ WorkflowUIRouter: Rendering state:', {
    Component: Component ? 'loaded' : 'null',
    ComponentType: typeof Component,
    payload: payload ? 'present' : 'null',
    payloadType: typeof payload
  });

  return (
    <div className="workflow-ui-container">
      {/* Debug info (development only) */}
      {process.env.NODE_ENV === 'development' && (
        <div className="workflow-debug text-xs text-gray-500 mb-2 p-2 bg-gray-800 rounded">
          🔧 Router: {workflowName}:{componentType} | Tool: {ui_tool_id} | Event: {eventId}
        </div>
      )}
      
      {/* Render the dynamically loaded workflow component */}
      {Component && typeof Component === 'function' && (
        <Component
          payload={payload || {}}
          onResponse={onResponse}
          onCancel={onCancel}
          submitInputRequest={submitInputRequest}
          ui_tool_id={ui_tool_id}
          eventId={eventId}
          workflowName={workflowName}
          componentId={componentType}
        />
      )}
    </div>
  );
};

export default WorkflowUIRouter;

/**
 * 🎯 WORKFLOW INTEGRATION GUIDE - NEW DYNAMIC SYSTEM
 * 
 * To add UI components for a new workflow (NO HARDCODING NEEDED):
 * 
 * 1. CREATE WORKFLOW COMPONENTS DIRECTORY:
 *    workflows/YourWorkflow/components/
 *    ├── YourComponent.js
 *    ├── AnotherComponent.js
 *    └── index.js
 * 
 * 2. CREATE COMPONENTS INDEX FILE:
 *    // workflows/YourWorkflow/components/index.js
 *    import YourComponent from './YourComponent';
 *    import AnotherComponent from './AnotherComponent';
 *    
 *    export {
 *      YourComponent,
 *      AnotherComponent
 *    };
 * 
 * 3. CREATE WORKFLOW UI TOOL (Backend):
 *    // workflows/YourWorkflow/tools/your_tool.py
 *    class YourUITool(WorkflowUITool):
 *      def __init__(self):
 *        super().__init__("YourWorkflow", "your_tool", "YourComponent")
 * 
 * 4. COMPONENT RECEIVES STANDARD PROPS:
 *    const YourComponent = ({ payload, onResponse, onCancel, ui_tool_id, eventId }) => {
 *      // Your component logic
 *    };
 * 
 * ✨ MAGIC: The router automatically discovers and loads your components!
 * ✨ NO REGISTRATION: No need to modify any core files!
 * ✨ FULLY MODULAR: Each workflow is completely self-contained!
 */
