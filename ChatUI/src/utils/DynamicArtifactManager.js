// ==============================================================================
// FILE: ChatUI/src/utils/DynamicArtifactManager.js
// DESCRIPTION: Dynamic artifact manager using clean event preparation 
// PURPOSE: Prepare artifact requests for the event system (no duplication)
// ==============================================================================

/**
 * 🎯 DYNAMIC ARTIFACT MANAGER - CLEAN VERSION
 * 
 * Prepares artifact requests for the event system.
 * No rendering duplication - lets eventDispatcher handle all component loading!
 */
class DynamicArtifactManager {
  constructor() {
    this.artifactHandlers = new Map();
    console.log('✅ Dynamic Artifact Manager initialized (using new architecture)');
  }

  /**
   * Get artifact component using the event system - SIMPLIFIED
   * @param {string} workflowName - The workflow name
   * @param {string} componentType - The artifact component type  
   * @param {Object} payload - Additional payload data
   * @returns {Object} - Event data for ChatInterface to handle
   */
  async getArtifactComponent(workflowName, componentType, payload = {}) {
    try {
      console.log(`🎨 DynamicArtifactManager: Preparing artifact ${workflowName}:${componentType}`);
      
      // Instead of creating mock events, return structured data
      // Let the ChatInterface handle the actual rendering via eventDispatcher
      return {
        type: 'artifact_request',
        ui_tool_id: `${workflowName}_${componentType}`,
        workflow_name: workflowName,
        payload: {
          ...payload,
          workflow_name: workflowName,
          component_type: componentType,
          category: 'artifact'
        },
        eventId: `artifact_${Date.now()}`
      };
      
    } catch (error) {
      console.error(`❌ DynamicArtifactManager: Error preparing ${workflowName}:${componentType}`, error);
      return null;
    }
  }

  /**
   * Register a custom artifact handler (for complex cases)
   * @param {string} artifactType - The type of artifact
   * @param {Function} handler - Handler function
   */
  registerArtifactHandler(artifactType, handler) {
    this.artifactHandlers.set(artifactType, handler);
    console.log(`📝 DynamicArtifactManager: Registered handler for '${artifactType}'`);
  }

  /**
   * Process an artifact creation request
   * @param {Object} artifactData - Artifact data
   * @returns {React.Element|null} - Rendered artifact component
   */
  async processArtifact(artifactData) {
    try {
      const { workflowName, componentType, ...payload } = artifactData;
      
      if (!workflowName || !componentType) {
        console.error('❌ DynamicArtifactManager: Missing workflowName or componentType', artifactData);
        return null;
      }

      // Check for custom handler first
      const customHandler = this.artifactHandlers.get(componentType);
      if (customHandler) {
        console.log(`🔧 DynamicArtifactManager: Using custom handler for ${componentType}`);
        return customHandler(artifactData);
      }

      // Use the new dynamic system
      return await this.getArtifactComponent(workflowName, componentType, payload);
      
    } catch (error) {
      console.error('❌ DynamicArtifactManager: Error processing artifact', error);
      return null;
    }
  }

  /**
   * Get all registered artifact handlers
   * @returns {Object} - Map of registered handlers
   */
  getRegisteredHandlers() {
    return Object.fromEntries(this.artifactHandlers);
  }

  /**
   * Clear all registered handlers
   */
  clearHandlers() {
    const count = this.artifactHandlers.size;
    this.artifactHandlers.clear();
    console.log(`🧹 DynamicArtifactManager: Cleared ${count} handlers`);
  }

  /**
   * Get manager statistics
   * @returns {Object} - Manager stats
   */
  getStats() {
    return {
      registeredHandlers: this.artifactHandlers.size,
      handlerTypes: Array.from(this.artifactHandlers.keys())
    };
  }
}

// Export singleton instance
export const dynamicArtifactManager = new DynamicArtifactManager();
export { DynamicArtifactManager };
export default dynamicArtifactManager;
