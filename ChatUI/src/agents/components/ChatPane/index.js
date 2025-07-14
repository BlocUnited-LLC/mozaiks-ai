// WORKFLOW COMPONENT REGISTRY
// Provides access to workflow-specific inline and artifact components

import { getInlineComponent, getArtifactComponent } from '../WorkflowComponentLoader';

/**
 * Get inline component from active workflow
 */
export const getInlineUIComponent = async (componentName) => {
  try {
    return await getInlineComponent(componentName);
  } catch (error) {
    console.warn(`Inline component '${componentName}' not found in active workflow`);
    return null;
  }
};

/**
 * Get artifact component from active workflow
 */
export const getArtifactUIComponent = async (componentName) => {
  try {
    return await getArtifactComponent(componentName);
  } catch (error) {
    console.warn(`Artifact component '${componentName}' not found in active workflow`);
    return null;
  }
};

export default {
  getInlineUIComponent,
  getArtifactUIComponent
};
