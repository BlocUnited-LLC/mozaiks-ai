// ==============================================================================
// FILE: agents/components/index.js
// DESCRIPTION: Workflow-Aware Component Registry
// ==============================================================================

/**
 * 🎯 WORKFLOW-AWARE COMPONENT REGISTRY
 * 
 * All components now come from workflow directories.
 * No global fallback components - everything is workflow-specific.
 */

// Import workflow-aware loader
import { 
  getArtifactComponent, 
  getInlineComponent, 
  getComponentByToolType as getWorkflowComponentByToolType,
  setActiveWorkflow 
} from './WorkflowComponentLoader';

/**
 * Get component from active workflow
 */
export const getComponent = async (componentName) => {
  // Try artifacts first
  let component = await getArtifactComponent(componentName);
  if (component) return component;
  
  // Try inline components
  component = await getInlineComponent(componentName);
  if (component) return component;
  
  console.warn(`Component '${componentName}' not found in active workflow`);
  return null;
};

/**
 * Get component by tool type from active workflow
 */
export const getComponentByToolType = async (toolType) => {
  const component = await getWorkflowComponentByToolType(toolType);
  if (component) return component;
  
  console.warn(`No component found for tool type '${toolType}' in active workflow`);
  return null;
};

/**
 * Get components by category from active workflow
 */
export const getComponentsByCategory = async (category) => {
  console.warn('getComponentsByCategory: All components now workflow-specific, check workflow manifests');
  return [];
};

/**
 * Get inline component by tool type from active workflow
 */
export const getInlineComponentByToolType = async (toolType) => {
  // Implementation to map tool types to inline components
  const component = await getWorkflowComponentByToolType(toolType);
  if (component) return component;
  
  console.warn(`No inline component found for tool type '${toolType}' in active workflow`);
  return null;
};

/**
 * Get artifact component by tool type from active workflow  
 */
export const getArtifactComponentByToolType = async (toolType) => {
  // Implementation to map tool types to artifact components
  const component = await getWorkflowComponentByToolType(toolType);
  if (component) return component;
  
  console.warn(`No artifact component found for tool type '${toolType}' in active workflow`);
  return null;
};

/**
 * Initialize components (now handled by workflow.json loading)
 */
export const initializeComponents = async () => {
  console.log('✅ Component initialization complete (using workflow.json discovery)');
  return Promise.resolve();
};

/**
 * React hook for workflow-specific components
 */
export const useComponent = (componentName) => {
  console.warn('useComponent: Switch to workflow-specific component loading');
  return null;
};

/**
 * Set active workflow for component loading
 */
export { setActiveWorkflow };

// Re-export workflow-specific functions
export { 
  getArtifactComponent,
  getInlineComponent
};

// Default export
const componentRegistry = {
  getComponent,
  getComponentByToolType,
  setActiveWorkflow,
  getArtifactComponent,
  getInlineComponent,
  initializeComponents
};

export default componentRegistry;
