// ==============================================================================
// FILE: ChatUI/src/workflows/index.js
// DESCRIPTION: Workflow registry - automatically loads all workflow components
// ==============================================================================

import uiToolRegistry from '../core/uiToolRegistry';

/**
 * Workflow Registry
 * 
 * Centralized workflow loading system that automatically discovers and loads
 * all workflow components by scanning the workflows directory structure.
 * Zero maintenance - just create a {workflowName}/index.js and it's auto-discovered!
 */

class WorkflowRegistry {
  constructor() {
    this.loadedWorkflows = new Map();
    this.loading = false;
    this.initialized = false;
  }

  /**
   * Initialize all workflows
   * Auto-discovers and loads workflow registrations
   */
  async initializeWorkflows() {
    if (this.loading || this.initialized) {
      console.log('⏭️ WorkflowRegistry: Already initialized or loading');
      return;
    }

    this.loading = true;
    console.log('🚀 WorkflowRegistry: Initializing workflows...');

    try {
      // Auto-discover all available workflows
      const availableWorkflows = await this.discoverWorkflows();
      console.log(`🔍 Discovered workflows: [${availableWorkflows.join(', ')}]`);

      // Load all discovered workflows
      for (const workflowName of availableWorkflows) {
        try {
          await this.loadWorkflow(workflowName);
        } catch (error) {
          console.warn(`⚠️ Failed to load workflow '${workflowName}':`, error.message);
          // Continue loading other workflows even if one fails
        }
      }

      this.initialized = true;
      uiToolRegistry.markInitialized();
      
      console.log(`✅ WorkflowRegistry: Initialized ${this.loadedWorkflows.size} workflows`);
      console.log('📊 Registry Stats:', uiToolRegistry.getStats());

    } catch (error) {
      console.error('❌ WorkflowRegistry: Failed to initialize workflows:', error);
      throw error;
    } finally {
      this.loading = false;
    }
  }

  /**
   * Auto-discover available workflows by testing imports
   * @returns {Array<string>} - Array of workflow names
   */
  async discoverWorkflows() {
    try {
      console.log('🔍 Auto-discovering workflows...');
      const workflowNames = [];
      
      // Test common workflow names by attempting imports
      const possibleWorkflows = ['Generator', 'Marketing', 'Analysis', 'Deployment'];
      
      for (const workflow of possibleWorkflows) {
        try {
          await import(`./${workflow}`);
          workflowNames.push(workflow);
          console.log(`  ✓ Found: ${workflow}`);
        } catch (e) {
          // Skip silently if workflow doesn't exist
        }
      }
      
      console.log(`🎯 Discovered workflows: [${workflowNames.join(', ')}]`);
      return workflowNames.length > 0 ? workflowNames : ['Generator'];
      
    } catch (error) {
      console.error('❌ Failed to discover workflows:', error);
      return ['Generator'];
    }
  }

  /**
   * Load a specific workflow dynamically
   * @param {string} workflowName - Name of the workflow to load
   */
  async loadWorkflow(workflowName) {
    try {
      console.log(`📦 Loading workflow: ${workflowName}...`);
      
      // Dynamic import using standard convention: ./{workflowName}/index.js
      const workflowModule = await import(`./${workflowName}`);

      // Store workflow info
      this.loadedWorkflows.set(workflowName, {
        name: workflowName,
        module: workflowModule,
        workflowInfo: workflowModule.workflowInfo || workflowModule.default,
        loadedAt: new Date().toISOString()
      });

      console.log(`✅ Loaded workflow: ${workflowName}`);

    } catch (error) {
      console.error(`❌ Failed to load workflow '${workflowName}':`, error);
      throw error;
    }
  }

  /**
   * Get information about loaded workflows
   * @returns {Object} - Workflow information
   */
  getLoadedWorkflows() {
    const workflows = {};
    for (const [name, info] of this.loadedWorkflows) {
      workflows[name] = {
        name: info.name,
        workflowInfo: info.workflowInfo,
        loadedAt: info.loadedAt
      };
    }
    return workflows;
  }

  /**
   * Check if a specific workflow is loaded
   * @param {string} workflowName - Workflow name to check
   * @returns {boolean} - True if loaded
   */
  isWorkflowLoaded(workflowName) {
    return this.loadedWorkflows.has(workflowName);
  }

  /**
   * Get workflow registry statistics
   * @returns {Object} - Registry statistics
   */
  getStats() {
    return {
      totalWorkflows: this.loadedWorkflows.size,
      loadedWorkflows: Array.from(this.loadedWorkflows.keys()),
      initialized: this.initialized,
      loading: this.loading,
      uiToolStats: uiToolRegistry.getStats()
    };
  }

  /**
   * Reload all workflows (useful for development)
   */
  async reload() {
    console.log('🔄 WorkflowRegistry: Reloading workflows...');
    this.loadedWorkflows.clear();
    this.initialized = false;
    uiToolRegistry.clear();
    await this.initializeWorkflows();
  }
}

// Create singleton instance
const workflowRegistry = new WorkflowRegistry();

// Auto-initialize workflows when this module is imported
// This ensures components are registered before they're needed
const initPromise = workflowRegistry.initializeWorkflows().catch(error => {
  console.error('❌ Critical: Failed to initialize workflow registry:', error);
});

// Export the registry and key functions
export default workflowRegistry;

export const getLoadedWorkflows = () => workflowRegistry.getLoadedWorkflows();
export const isWorkflowLoaded = (name) => workflowRegistry.isWorkflowLoaded(name);
export const getWorkflowStats = () => workflowRegistry.getStats();
export const reloadWorkflows = () => workflowRegistry.reload();

// Export the initialization promise for apps that need to wait
export const workflowsInitialized = initPromise;
