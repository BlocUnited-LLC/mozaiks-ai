// ==============================================================================
// FILE: ChatUI/src/modules/Chat/utils/DynamicArtifactManager.js
// DESCRIPTION: Dynamic artifact manager based on workflow configuration
// ==============================================================================
import workflowConfig from '../../../config/workflowConfig';
import { getArtifactComponent } from '../../../agents/components';

/**
 * Dynamic Artifact Manager
 * Handles artifact creation and routing based on workflow configuration
 */
class DynamicArtifactManager {
  constructor() {
    this.artifactHandlers = new Map();
    // No default handlers - everything comes from workflow manifests
    console.log('✅ Dynamic Artifact Manager initialized (workflow-agnostic)');
  }

  /**
   * Get artifact component from active workflow
   * @param {string} componentType - The artifact component type
   * @returns {React.Component|null} - The artifact component
   */
  async getArtifactComponent(componentType) {
    try {
      const component = await getArtifactComponent(componentType);
      if (component) {
        return component;
      } else {
        console.warn(`Artifact component '${componentType}' not found in active workflow`);
        return null;
      }
    } catch (error) {
      console.error(`Error loading artifact component '${componentType}':`, error);
      return null;
    }
  }

  /**
   * Get artifact agent for current workflow
   * @param {string} workflowType - The workflow type
   * @returns {string|null} - The agent name that handles artifacts
   */
  getArtifactAgent(workflowType) {
    if (!workflowType) {
      workflowType = workflowConfig.getDefaultWorkflow();
    }
    return workflowConfig.getArtifactAgent(workflowType);
  }

  /**
   * Check if message is from artifact agent
   * @param {Object} message - The chat message
   * @param {string} workflowType - The workflow type
   * @returns {boolean} - True if message is from artifact agent
   */
  isFromArtifactAgent(message, workflowType) {
    const artifactAgent = this.getArtifactAgent(workflowType);
    return message.agentName === artifactAgent || message.sender === artifactAgent;
  }

  /**
   * Parse artifacts from message content
   * @param {string} content - Message content
   * @returns {Array} - Array of artifacts found
   */
  parseArtifacts(content) {
    const artifacts = [];
    const artifactRegex = /\[ARTIFACT:(\w+)\]/g;
    let match;

    while ((match = artifactRegex.exec(content)) !== null) {
      const artifactType = match[1];
      const handler = this.artifactHandlers.get(artifactType);
      
      if (handler) {
        artifacts.push({
          type: artifactType,
          ...handler
        });
      }
    }

    return artifacts;
  }

  /**
   * Create artifact message
   * @param {string} baseMessage - Base message text
   * @param {Array} artifacts - Array of artifact types to add
   * @returns {Object} - Message with artifacts
   */
  createArtifactMessage(baseMessage, artifacts = []) {
    let messageContent = baseMessage;
    const artifactData = {};

    artifacts.forEach(artifactType => {
      const handler = this.artifactHandlers.get(artifactType);
      if (handler) {
        const marker = `[ARTIFACT:${artifactType}]`;
        messageContent += ` ${marker}`;
        artifactData[artifactType] = {
          type: artifactType,
          ...handler
        };
      }
    });

    return {
      content: messageContent,
      artifactData: artifactData,
      sender: "assistant",
      hasArtifacts: artifacts.length > 0
    };
  }

  /**
   * Register a custom artifact handler
   * @param {string} type - Artifact type
   * @param {Object} handler - Handler configuration
   */
  registerArtifactHandler(type, handler) {
    this.artifactHandlers.set(type, handler);
  }

  /**
   * Get all registered artifact types
   * @returns {Array} - Array of artifact types
   */
  getAvailableArtifactTypes() {
    return Array.from(this.artifactHandlers.keys());
  }
}

// Global instance
export const dynamicArtifactManager = new DynamicArtifactManager();
export default dynamicArtifactManager;
