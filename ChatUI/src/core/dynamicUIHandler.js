// ==============================================================================
// FILE: ChatUI/src/core/dynamicUIHandler.js
// DESCRIPTION: Handles dynamic UI updates from backend transport system
// ==============================================================================

/**
 * Dynamic UI Handler
 * Processes backend UI events and triggers appropriate frontend updates
 * Bridges transport system with dynamic component system
 */

import { enterpriseApi } from '../adapters/api';
import { DynamicArtifactManager } from '../modules/Chat/utils/DynamicArtifactManager';

export class DynamicUIHandler {
  constructor() {
    this.artifactManager = new DynamicArtifactManager();
    this.eventHandlers = new Map();
    this.uiUpdateCallbacks = new Set();
    this.workflowCache = new Map(); // Add workflow cache
    this.setupDefaultHandlers();
  }

  /**
   * Setup default event handlers for backend UI events
   */
  setupDefaultHandlers() {
    // Artifact routing events
    this.registerHandler('route_to_artifact', this.handleArtifactRoute.bind(this));
    this.registerHandler('ROUTE_TO_ARTIFACT', this.handleArtifactRoute.bind(this));
    
    // UI tool action events
    this.registerHandler('ui_tool_action', this.handleUIToolAction.bind(this));
    this.registerHandler('UI_TOOL_ACTION', this.handleUIToolAction.bind(this));
    
    // Component update events
    this.registerHandler('component_update', this.handleComponentUpdate.bind(this));
    this.registerHandler('COMPONENT_UPDATE', this.handleComponentUpdate.bind(this));
    
    // Status update events
    this.registerHandler('status', this.handleStatusUpdate.bind(this));
    this.registerHandler('STATUS', this.handleStatusUpdate.bind(this));
    
    console.log('✅ Dynamic UI Handler initialized with default event handlers');
  }

  /**
   * Register a custom event handler
   * @param {string} eventType - Event type to handle
   * @param {Function} handler - Handler function
   */
  registerHandler(eventType, handler) {
    this.eventHandlers.set(eventType, handler);
  }

  /**
   * Process incoming UI event from transport layer
   * @param {Object} eventData - Event data from backend
   */
  async processUIEvent(eventData) {
    const { type, data } = eventData;
    
    console.log(`🎯 Processing UI event: ${type}`, data);
    
    const handler = this.eventHandlers.get(type);
    if (handler) {
      try {
        await handler(data, eventData);
      } catch (error) {
        console.error(`❌ Error processing UI event ${type}:`, error);
      }
    } else {
      console.warn(`⚠️ No handler found for UI event type: ${type}`);
    }
  }

  /**
   * Handle artifact routing events
   * @param {Object} data - Artifact event data
   */
  async handleArtifactRoute(data) {
    console.log('📦 Handling artifact route:', data);
    
    if (data.artifact_id) {
      // Load artifact component if specified
      if (data.component_type) {
        const component = await this.artifactManager.getArtifactComponent(data.component_type);
        if (component) {
          this.notifyUIUpdate({
            type: 'artifact_component_loaded',
            artifactId: data.artifact_id,
            componentType: data.component_type,
            component
          });
        }
      }
      
      // Trigger artifact panel if needed
      if (data.action === 'open_panel') {
        this.notifyUIUpdate({
          type: 'open_artifact_panel',
          artifactId: data.artifact_id,
          data: data
        });
      }
    }
  }

  /**
   * Handle UI tool action events
   * @param {Object} data - Tool action data
   */
  async handleUIToolAction(data) {
    console.log('🔧 Handling UI tool action:', data);
    
    switch (data.action) {
      case 'update_component':
        await this.handleComponentUpdate(data);
        break;
        
      case 'show_notification':
        this.notifyUIUpdate({
          type: 'show_notification',
          message: data.message,
          severity: data.severity || 'info'
        });
        break;
        
      case 'toggle_panel':
        this.notifyUIUpdate({
          type: 'toggle_panel',
          panel: data.panel,
          state: data.state
        });
        break;
        
      default:
        console.warn(`⚠️ Unknown UI tool action: ${data.action}`);
    }
  }

  /**
   * Handle component update events
   * @param {Object} data - Component update data
   */
  async handleComponentUpdate(data) {
    console.log('🔄 Handling component update:', data);
    
    if (data.component_id && data.updates) {
      this.notifyUIUpdate({
        type: 'component_update',
        componentId: data.component_id,
        updates: data.updates,
        enterprise_id: data.enterprise_id
      });
    }
  }

  /**
   * Handle status update events
   * @param {Object} data - Status data
   */
  handleStatusUpdate(data) {
    console.log('📊 Handling status update:', data);
    
    this.notifyUIUpdate({
      type: 'status_update',
      status: data.status,
      message: data.message,
      progress: data.progress
    });
  }

  /**
   * Register a UI update callback
   * @param {Function} callback - Callback to notify of UI updates
   */
  onUIUpdate(callback) {
    this.uiUpdateCallbacks.add(callback);
    return () => this.uiUpdateCallbacks.delete(callback);
  }

  /**
   * Notify all registered callbacks of UI updates
   * @param {Object} updateData - Update data
   */
  notifyUIUpdate(updateData) {
    console.log('📢 Notifying UI update:', updateData);
    
    for (const callback of this.uiUpdateCallbacks) {
      try {
        callback(updateData);
      } catch (error) {
        console.error('❌ Error in UI update callback:', error);
      }
    }
  }

  /**
   * Get enterprise context for dynamic UI
   * @param {string} enterpriseId - Enterprise ID
   * @returns {Object} - Enterprise context
   */
  getEnterpriseContext(enterpriseId) {
    return {
      enterprise_id: enterpriseId
    };
  }

  /**
   * Get workflow configuration from backend
   */
  async getWorkflowConfig(workflowType = 'generator') {
    const cacheKey = workflowType;
    
    if (this.workflowCache.has(cacheKey)) {
      return this.workflowCache.get(cacheKey);
    }

    try {
      const response = await enterpriseApi.get(`/workflow/${workflowType}/config`);
      const config = response.data;
      
      this.workflowCache.set(cacheKey, config);
      console.log(`✅ Loaded workflow config for UI: ${workflowType}`);
      
      return config;
      
    } catch (error) {
      console.error(`Failed to load workflow config: ${workflowType}`, error);
      return { ui_capable_agents: [] };
    }
  }

  /**
   * Get component definition from workflow config
   */
  async getComponentDefinition(componentName, workflowType = 'generator') {
    try {
      const config = await this.getWorkflowConfig(workflowType);
      
      // Search through ui_capable_agents for the component
      for (const agent of config.ui_capable_agents || []) {
        const component = agent.components?.find(c => c.name === componentName);
        if (component) {
          return {
            ...component,
            agentName: agent.name,
            agentRole: agent.role
          };
        }
      }
      
      console.warn(`Component ${componentName} not found in workflow ${workflowType}`);
      return null;
      
    } catch (error) {
      console.error(`Failed to get component definition: ${componentName}`, error);
      return null;
    }
  }
}

// Export singleton instance
export const dynamicUIHandler = new DynamicUIHandler();
export default dynamicUIHandler;
