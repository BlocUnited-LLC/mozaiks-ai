// ==============================================================================
// FILE: ChatUI/src/config/workflowConfig.js
// DESCRIPTION: Dynamic workflow configuration for frontend
// ==============================================================================

/**
 * Workflow configuration manager for frontend
 * Fetches workflow configurations from backend
 */
class WorkflowConfig {
  constructor() {
    this.configs = new Map();
    this.defaultWorkflow = null; // Dynamic discovery from backend
  }

  /**
   * Fetch workflow configurations from backend
   */
  async fetchWorkflowConfigs() {
    try {
      const response = await fetch('/api/workflows/config');
      if (response.ok) {
        const configs = await response.json();
        Object.entries(configs).forEach(([type, config]) => {
          this.configs.set(type, config);
        });
        console.log('✅ Loaded workflow configs:', Object.keys(configs));
      }
    } catch (error) {
      console.warn('⚠️ Failed to fetch workflow configs, using defaults:', error);
    }
  }

  /**
   * Get available workflow types
   */
  getAvailableWorkflows() {
    return Array.from(this.configs.keys());
  }

  /**
   * Get default workflow type
   */
  getDefaultWorkflow() {
    const available = this.getAvailableWorkflows();
    if (available.length > 0) {
      return available[0]; // Use first available workflow
    }
    
    // If no workflows discovered, let backend handle this
    console.warn('⚠️ No workflows discovered, backend should provide default');
    return null;
  }

  /**
   * Check if workflow has human in the loop
   */
  hasHumanInTheLoop(workflowType) {
    const config = this.configs.get(workflowType);
    return config?.human_in_the_loop || false;
  }

  /**
   * Get inline component agents for workflow
   */
  getInlineComponentAgents(workflowType) {
    const config = this.configs.get(workflowType);
    return config?.inline_component_agents || [];
  }

  /**
   * Get artifact component agents for workflow
   */
  getArtifactComponentAgents(workflowType) {
    const config = this.configs.get(workflowType);
    return config?.artifact_component_agents || [];
  }
}

// Global instance
export const workflowConfig = new WorkflowConfig();
export default workflowConfig;
