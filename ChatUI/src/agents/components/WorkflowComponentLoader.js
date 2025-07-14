// ==============================================================================
// FILE: agents/components/WorkflowComponentLoader.js
// DESCRIPTION: Workflow-Aware Dynamic Component Loader
// ==============================================================================

/**
 * 🎯 WORKFLOW-AWARE COMPONENT LOADER
 * 
 * Dynamically loads components from the active workflow's Components folder
 * instead of hardcoded ChatUI components.
 */

class WorkflowComponentLoader {
  constructor() {
    this.activeWorkflow = null;
    this.artifactManifest = null;
    this.inlineManifest = null;
    this.componentCache = new Map();
  }

  /**
   * 🔄 SET ACTIVE WORKFLOW
   */
  async setActiveWorkflow(workflowName) {
    if (this.activeWorkflow === workflowName) {
      return; // Already loaded
    }

    console.log(`🔄 Switching to workflow: ${workflowName}`);
    this.activeWorkflow = workflowName;
    this.componentCache.clear();
    
    await this._loadWorkflowManifests(workflowName);
  }

  /**
   * 📦 LOAD WORKFLOW MANIFESTS
   */
  async _loadWorkflowManifests(workflowName) {
    try {
      // Load Artifacts manifest
      const artifactManifestPath = `../../../workflows/${workflowName}/Components/Artifacts/components.json`;
      const artifactModule = await import(artifactManifestPath);
      this.artifactManifest = artifactModule.default;
      console.log(`✅ Loaded Artifacts manifest for workflow: ${workflowName}`);
    } catch (error) {
      console.warn(`⚠️ No Artifacts manifest found for workflow ${workflowName}`);
      this.artifactManifest = { components: {} };
    }

    try {
      // Load Inline manifest
      const inlineManifestPath = `../../../workflows/${workflowName}/Components/Inline/components.json`;
      const inlineModule = await import(inlineManifestPath);
      this.inlineManifest = inlineModule.default;
      console.log(`✅ Loaded Inline manifest for workflow: ${workflowName}`);
    } catch (error) {
      console.warn(`⚠️ No Inline manifest found for workflow ${workflowName}`);
      this.inlineManifest = { components: {} };
    }
  }

  /**
   * 🔍 GET ARTIFACT COMPONENT
   */
  async getArtifactComponent(componentName) {
    if (!this.activeWorkflow || !this.artifactManifest) {
      console.warn('No active workflow set for artifact component loading');
      return null;
    }

    const cacheKey = `artifact_${componentName}`;
    if (this.componentCache.has(cacheKey)) {
      return this.componentCache.get(cacheKey);
    }

    const config = this.artifactManifest.components[componentName];
    if (!config) {
      console.warn(`Artifact component ${componentName} not found in workflow ${this.activeWorkflow}`);
      return null;
    }

    try {
      const componentPath = `../../../workflows/${this.activeWorkflow}/Components/Artifacts/${config.file}`;
      const module = await import(componentPath);
      const component = module.default;
      
      this.componentCache.set(cacheKey, component);
      console.log(`✅ Loaded artifact component: ${componentName} from workflow ${this.activeWorkflow}`);
      return component;
    } catch (error) {
      console.error(`Failed to load artifact component ${componentName}:`, error);
      return null;
    }
  }

  /**
   * 🔍 GET INLINE COMPONENT
   */
  async getInlineComponent(componentName) {
    if (!this.activeWorkflow || !this.inlineManifest) {
      console.warn('No active workflow set for inline component loading');
      return null;
    }

    const cacheKey = `inline_${componentName}`;
    if (this.componentCache.has(cacheKey)) {
      return this.componentCache.get(cacheKey);
    }

    const config = this.inlineManifest.components[componentName];
    if (!config) {
      console.warn(`Inline component ${componentName} not found in workflow ${this.activeWorkflow}`);
      return null;
    }

    try {
      const componentPath = `../../../workflows/${this.activeWorkflow}/Components/Inline/${config.file}`;
      const module = await import(componentPath);
      const component = module.default;
      
      this.componentCache.set(cacheKey, component);
      console.log(`✅ Loaded inline component: ${componentName} from workflow ${this.activeWorkflow}`);
      return component;
    } catch (error) {
      console.error(`Failed to load inline component ${componentName}:`, error);
      return null;
    }
  }

  /**
   * 🔍 GET COMPONENT BY TOOL TYPE
   */
  async getComponentByToolType(toolType) {
    // Check artifacts first
    if (this.artifactManifest?.toolTypes?.[toolType]) {
      const componentName = this.artifactManifest.toolTypes[toolType].defaultComponent;
      return await this.getArtifactComponent(componentName);
    }

    // Then check inline
    if (this.inlineManifest?.toolTypes?.[toolType]) {
      const componentName = this.inlineManifest.toolTypes[toolType].defaultComponent;
      return await this.getInlineComponent(componentName);
    }

    console.warn(`No component found for tool type: ${toolType} in workflow ${this.activeWorkflow}`);
    return null;
  }

  /**
   * 📋 GET ALL AVAILABLE COMPONENTS
   */
  getAvailableComponents() {
    const artifacts = this.artifactManifest ? Object.keys(this.artifactManifest.components) : [];
    const inline = this.inlineManifest ? Object.keys(this.inlineManifest.components) : [];
    
    return {
      artifacts,
      inline,
      total: artifacts.length + inline.length
    };
  }
}

// Global instance
const workflowLoader = new WorkflowComponentLoader();

// Public API
export const setActiveWorkflow = (workflowName) => workflowLoader.setActiveWorkflow(workflowName);
export const getArtifactComponent = (componentName) => workflowLoader.getArtifactComponent(componentName);
export const getInlineComponent = (componentName) => workflowLoader.getInlineComponent(componentName);
export const getComponentByToolType = (toolType) => workflowLoader.getComponentByToolType(toolType);
export const getAvailableComponents = () => workflowLoader.getAvailableComponents();

export default workflowLoader;
