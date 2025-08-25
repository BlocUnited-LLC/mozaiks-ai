// ==============================================================================
// FILE: ChatUI/src/workflows/index.js
// DESCRIPTION: Workflow metadata registry (CLEAN VERSION - API DRIVEN)
// PURPOSE: Fetch workflow metadata from backend API (no duplication!)
// ==============================================================================

/**
 * 🎯 WORKFLOW REGISTRY - API DRIVEN CLEAN VERSION
 * 
 * Registry for workflow metadata fetched from backend API.
 * Single source of truth: YAML files in backend, accessed via /api/workflows
 * No duplicate configuration files, no hardcoded metadata.
 * 
 * Benefits:
 * - Single source of truth (backend YAML files)
 * - No duplicate metadata
 * - Real-time configuration updates
 * - Clean separation of concerns
 */

class WorkflowRegistry {
  constructor() {
    this.loadedWorkflows = new Map();
    this.initialized = false;
    this.apiBaseUrl = 'http://localhost:8000/api'; // Direct backend API base URL (bypass proxy)
  }

  /**
   * Initialize all workflows by fetching from backend API
   */
  async initializeWorkflows() {
    if (this.initialized) {
      console.log('⏭️ WorkflowRegistry: Already initialized');
      return this.getWorkflowSummary();
    }

    console.log('🚀 WorkflowRegistry: Fetching workflows from backend API...');

    try {
      // Fetch all workflow configurations from backend API
      // This reads the YAML files from the backend (single source of truth)
      const response = await fetch(`${this.apiBaseUrl}/workflows`);
      
      if (!response.ok) {
        throw new Error(`API request failed: ${response.status} ${response.statusText}`);
      }
      
      const workflowConfigs = await response.json();
      
      // Process each workflow configuration
      for (const [workflowName, config] of Object.entries(workflowConfigs)) {
        const workflowInfo = {
          name: workflowName,
          displayName: config.name || workflowName,
          description: `${config.name || workflowName} workflow`,
          version: '1.0.0',
          metadata: {
            maxTurns: config.max_turns,
            humanInTheLoop: config.human_in_the_loop,
            startupMode: config.startup_mode,
            orchestrationPattern: config.orchestration_pattern,
            chatPaneAgents: config.chat_pane_agents || [],
            artifactAgents: config.artifact_agents || [],
            initialMessage: config.initial_message,
            uiTools: config.ui_tools || {}
          },
          visualAgents: config.visual_agents || {},
          tools: config.tools || {},
          loadedAt: new Date().toISOString()
        };
        
        this.loadedWorkflows.set(workflowName, workflowInfo);
        console.log(`✅ Loaded workflow from API: ${workflowName}`);
      }

      this.initialized = true;
      console.log(`✅ WorkflowRegistry: Loaded ${this.loadedWorkflows.size} workflows from backend`);
      
      return this.getWorkflowSummary();

    } catch (error) {
      console.error('❌ WorkflowRegistry: Failed to fetch workflows from API:', error);
      throw error;
    }
  }

  /**
   * Get all loaded workflows
   * @returns {Array} - Array of workflow info objects
   */
  getLoadedWorkflows() {
    return Array.from(this.loadedWorkflows.values());
  }

  /**
   * Get specific workflow info
   * @param {string} workflowName - Name of the workflow
   * @returns {Object|null} - Workflow info or null
   */
  getWorkflow(workflowName) {
    return this.loadedWorkflows.get(workflowName) || null;
  }

  /**
   * Get workflow summary for debugging
   * @returns {Object} - Summary of all workflows
   */
  getWorkflowSummary() {
    return {
      initialized: this.initialized,
      workflowCount: this.loadedWorkflows.size,
      workflows: this.getLoadedWorkflows().map(w => ({
        name: w.name,
        displayName: w.displayName,
        version: w.version,
        agentCount: Object.keys(w.visualAgents || {}).length,
        hasHumanInLoop: w.metadata.humanInTheLoop
      }))
    };
  }

  /**
   * Refresh workflows from backend (useful for development)
   */
  async refresh() {
    console.log('🔄 WorkflowRegistry: Refreshing workflows from backend...');
    this.clear();
    return await this.initializeWorkflows();
  }

  /**
   * Clear all loaded workflows
   */
  clear() {
    const count = this.loadedWorkflows.size;
    this.loadedWorkflows.clear();
    this.initialized = false;
    console.log(`🧹 WorkflowRegistry: Cleared ${count} workflows`);
  }

  /**
   * Get registry statistics
   * @returns {Object} - Registry stats
   */
  getStats() {
    return {
      initialized: this.initialized,
      loadedWorkflows: this.loadedWorkflows.size,
      workflowNames: Array.from(this.loadedWorkflows.keys()),
      apiEndpoint: `${this.apiBaseUrl}/workflows`
    };
  }
}

// Create singleton instance
const workflowRegistry = new WorkflowRegistry();

// Export both the instance and convenience methods
export default workflowRegistry;

export const initializeWorkflows = () => workflowRegistry.initializeWorkflows();
export const getLoadedWorkflows = () => workflowRegistry.getLoadedWorkflows();
export const getWorkflow = (name) => workflowRegistry.getWorkflow(name);
export const getWorkflowSummary = () => workflowRegistry.getWorkflowSummary();
export const refreshWorkflows = () => workflowRegistry.refresh();