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
    this.workflowConfig = null;
    this.componentCache = new Map();
    this.componentMappings = { artifacts: {}, inline: {} };
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
    
    await this._loadWorkflowConfig(workflowName);
  }

  /**
   * 📦 LOAD WORKFLOW CONFIG
   */
  async _loadWorkflowConfig(workflowName) {
    try {
      // Load workflow.json directly
      const workflowConfigPath = `../../../workflows/${workflowName}/workflow.json`;
      const configModule = await import(workflowConfigPath);
      this.workflowConfig = configModule.default;
      
      // Build component mappings from workflow config
      this._buildComponentMappings();
      
      console.log(`✅ Loaded workflow config for: ${workflowName}`);
    } catch (error) {
      console.error(`❌ Failed to load workflow config for ${workflowName}:`, error);
      this.workflowConfig = null;
      this.componentMappings = { artifacts: {}, inline: {} };
    }
  }

  /**
   * 🗺️ BUILD COMPONENT MAPPINGS FROM WORKFLOW CONFIG
   */
  _buildComponentMappings() {
    this.componentMappings = { artifacts: {}, inline: {} };
    
    if (!this.workflowConfig?.ui_capable_agents) {
      return;
    }

    // Extract components from ui_capable_agents
    for (const agent of this.workflowConfig.ui_capable_agents) {
      if (agent.components) {
        for (const component of agent.components) {
          const componentInfo = {
            name: component.name,
            file: `${component.name}.js`,
            description: component.description,
            actions: component.actions,
            backend_handler: component.backend_handler
          };

          if (component.type === 'artifact') {
            this.componentMappings.artifacts[component.name] = componentInfo;
          } else if (component.type === 'inline') {
            this.componentMappings.inline[component.name] = componentInfo;
          }
        }
      }
    }

    console.log(`📦 Built component mappings:`, {
      artifacts: Object.keys(this.componentMappings.artifacts),
      inline: Object.keys(this.componentMappings.inline)
    });
  }

  /**
   * 🔍 GET ARTIFACT COMPONENT
   */
  async getArtifactComponent(componentName) {
    if (!this.activeWorkflow || !this.componentMappings.artifacts[componentName]) {
      console.warn(`Artifact component ${componentName} not found in workflow ${this.activeWorkflow}`);
      return null;
    }

    const cacheKey = `artifact_${componentName}`;
    if (this.componentCache.has(cacheKey)) {
      return this.componentCache.get(cacheKey);
    }

    const config = this.componentMappings.artifacts[componentName];

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
    if (!this.activeWorkflow || !this.componentMappings.inline[componentName]) {
      console.warn(`Inline component ${componentName} not found in workflow ${this.activeWorkflow}`);
      return null;
    }

    const cacheKey = `inline_${componentName}`;
    if (this.componentCache.has(cacheKey)) {
      return this.componentCache.get(cacheKey);
    }

    const config = this.componentMappings.inline[componentName];

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
    // Search through workflow config for components with matching backend_handler or actions
    for (const agent of this.workflowConfig?.ui_capable_agents || []) {
      if (agent.components) {
        for (const component of agent.components) {
          // Match by backend_handler or custom logic
          if (component.backend_handler?.includes(toolType) || 
              component.actions?.includes(toolType)) {
            
            if (component.type === 'artifact') {
              return await this.getArtifactComponent(component.name);
            } else if (component.type === 'inline') {
              return await this.getInlineComponent(component.name);
            }
          }
        }
      }
    }

    console.warn(`No component found for tool type: ${toolType} in workflow ${this.activeWorkflow}`);
    return null;
  }

  /**
   * 📋 GET ALL AVAILABLE COMPONENTS
   */
  getAvailableComponents() {
    const artifacts = Object.keys(this.componentMappings.artifacts);
    const inline = Object.keys(this.componentMappings.inline);
    
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
