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
      // Try the main workflows endpoint first
      const response = await fetch('/api/workflows');
      if (response.ok) {
        const data = await response.json();
        
        console.log('🔍 Raw workflow data from backend:', data);
        
        // Backend returns workflows as object with workflow names as keys
        // Convert to array format for processing
        const workflows = [];
        for (const [workflowName, workflowConfig] of Object.entries(data)) {
          workflows.push({
            workflow_name: workflowName,
            ...workflowConfig
          });
        }
        
        // Store each workflow configuration directly
        for (const workflow of workflows) {
          // Store under original key
          this.configs.set(workflow.workflow_name, workflow);
          // Also store a lowercase alias to allow case-insensitive lookups
          const lowerKey = workflow.workflow_name.toLowerCase();
          if (!this.configs.has(lowerKey)) {
            this.configs.set(lowerKey, workflow);
          }
        }
        
        console.log('✅ Loaded workflow configs:', workflows.map(w => w.workflow_name));
        
        // Set default workflow if we have any
        if (workflows.length > 0) {
          this.defaultWorkflow = workflows[0].workflow_name;
          console.log('🎯 Default workflow set to:', this.defaultWorkflow);
        }
      } else {
        console.warn('⚠️ Failed to fetch workflows, status:', response.status);
        const errorText = await response.text();
        console.warn('⚠️ Response text:', errorText.substring(0, 200));
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
   * Get workflow configuration by type
   */
  getWorkflowConfig(workflowname) {
    if (!workflowname) return null;
    // Direct hit (exact case or lowercase alias already inserted)
    const direct = this.configs.get(workflowname);
    if (direct) return direct;
    // Fallback: case-insensitive scan (handles legacy entries if any)
    const target = workflowname.toLowerCase();
    for (const [k, v] of this.configs.entries()) {
      if (k.toLowerCase() === target) return v;
    }
    return null;
  }

  /**
   * Check if workflow has human in the loop
   */
  hasHumanInTheLoop(workflowname) {
    const config = this.configs.get(workflowname);
    return config?.human_in_the_loop || false;
  }

  /**
   * Get inline component agents for workflow
   */
  getInlineComponentAgents(workflowname) {
    const config = this.configs.get(workflowname);
    return config?.inline_component_agents || [];
  }

  /**
   * Get artifact component agents for workflow
   */
  getArtifactComponentAgents(workflowname) {
    const config = this.configs.get(workflowname);
    return config?.artifact_component_agents || [];
  }

  /**
   * Check if workflow has UserProxy component integration
   */
  hasUserProxyComponent(workflowname) {
    const config = this.configs.get(workflowname);
    // Check if any ui_capable_agents have UserProxy-related components
    return config?.ui_capable_agents?.some(agent => 
      agent.name?.toLowerCase().includes('user') ||
      agent.role?.includes('user_') ||
      agent.components?.some(comp => comp.name?.toLowerCase().includes('user'))
    ) || false;
  }

  /**
   * Get UserProxy-related components for workflow
   */
  getUserProxyComponents(workflowname) {
    const config = this.configs.get(workflowname);
    const userComponents = [];
    
    if (config?.ui_capable_agents) {
      config.ui_capable_agents.forEach(agent => {
        if (agent.name?.toLowerCase().includes('user') || 
            agent.role?.includes('user_')) {
          userComponents.push(...(agent.components || []));
        }
      });
    }
    
    return userComponents;
  }

  /**
   * Check if UserProxy needs special transport handling
   */
  userProxyNeedsTransportHandling(workflowname) {
    // UserProxy with human_in_the_loop=true needs transport integration
    return this.hasHumanInTheLoop(workflowname);
  }
}

// Global instance
export const workflowConfig = new WorkflowConfig();
export default workflowConfig;
