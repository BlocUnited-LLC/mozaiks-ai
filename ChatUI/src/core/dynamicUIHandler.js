// ==============================================================================
// FILE: ChatUI/src/core/dynamicUIHandler.js
// DESCRIPTION: Handles dynamic UI updates from backend transport system
// ==============================================================================

/**
 * Dynamic UI Handler
 * Processes backend UI events and triggers appropriate frontend updates
 * Bridges transport system with UI components (no duplication)
 */

import { enterpriseApi } from '../adapters/api';
import { createToolsLogger } from './toolsLogger';

export class DynamicUIHandler {
  constructor() {
    this.eventHandlers = new Map();
    this.uiUpdateCallbacks = new Set();
    this.workflowCache = new Map();
    this.setupDefaultHandlers();
  }

  /**
   * Setup default event handlers for backend UI events
   */
  setupDefaultHandlers() {
    // Register only canonical lowercase event types
    this.registerHandler('ui_tool_event', this.handleUIToolEvent.bind(this));
    this.registerHandler('user_input_request', this.handleUserInputRequest.bind(this));
    this.registerHandler('component_update', this.handleComponentUpdate.bind(this));
    this.registerHandler('status', this.handleStatusUpdate.bind(this));

    console.log('✅ Dynamic UI Handler initialized');
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
   * @param {Function} sendResponse - Optional response callback (for WebSocket)
   */
  async processUIEvent(eventData, sendResponse = null) {
    if (!eventData) return;

    const originalType = eventData?.type;
    let type = originalType;
    let data = eventData?.data;

    // Support transports that send payload fields at the top level instead of nested under data
    if (data === undefined || data === null) {
      const { type: _ignoredType, data: _ignoredData, ...rest } = eventData || {};
      data = Object.keys(rest).length ? rest : {};
    }

    if (typeof type !== 'string' || !type) {
      console.warn('⚠️ Received UI event with invalid type, ignoring:', eventData);
      return;
    }
    if (type !== type.toLowerCase()) {
      // Enforce strictness: reject mixed-case legacy emissions instead of silently normalizing
      console.warn(`⚠️ Rejecting non-lowercase UI event type '${type}' (expected canonical lowercase)`);
      return;
    }
    console.log(`🎯 Processing UI event: ${originalType}`, data);

    const handler = this.eventHandlers.get(type);
    if (!handler) {
      console.warn(`⚠️ No handler found for UI event type: ${type}`);
      return;
    }

    try {
      if (type === 'ui_tool_event') {
        await handler(data, sendResponse);
      } else {
        await handler(data, eventData);
      }
    } catch (error) {
      console.error(`❌ Error processing UI event ${type}:`, error);
    }
  }

  /**
   * Handle artifact routing events
   * @param {Object} data - Artifact event data
   */

  /**
   * Handle UI tool action events
   * @param {Object} data - Tool action data
   */

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
    if (updateData?.type === 'ui_tool_event') {
      const { ui_tool_id, eventId, workflow_name, payload } = updateData;
      console.log('🧭 ui_tool_event routed to UI callbacks', {
        ui_tool_id,
        eventId,
        workflow_name,
        hasOnResponse: !!updateData.onResponse,
        payloadKeys: payload ? Object.keys(payload) : []
      });
    }
    
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
  async getWorkflowConfig(workflowname) {
    if (!workflowname) {
      throw new Error('Workflow name is required');
    }
    
    const cacheKey = workflowname;
    
    if (this.workflowCache.has(cacheKey)) {
      return this.workflowCache.get(cacheKey);
    }

    try {
      const response = await enterpriseApi.get(`/workflow/${workflowname}/config`);
      const config = response.data;
      
      this.workflowCache.set(cacheKey, config);
      console.log(`✅ Loaded workflow config for UI: ${workflowname}`);
      
      return config;
      
    } catch (error) {
      console.error(`Failed to load workflow config: ${workflowname}`, error);
      return { visual_agent: [] };
    }
  }

  /**
   * Get component definition from workflow config
   */
  async getComponentDefinition(componentName, workflowname) {
    if (!workflowname) {
      throw new Error('Workflow name is required');
    }
    
    try {
      const config = await this.getWorkflowConfig(workflowname);
      
      // Search through visual_agent for the component
      for (const agent of config.visual_agent || []) {
        const component = agent.components?.find(c => c.name === componentName);
        if (component) {
          return {
            ...component,
            agentName: agent.name,
            agentRole: agent.role
          };
        }
      }
      
      console.warn(`Component ${componentName} not found in workflow ${workflowname}`);
      return null;
      
    } catch (error) {
      console.error(`Failed to get component definition: ${componentName}`, error);
      return null;
    }
  }

  /**
   * Handle UI tool action events - SIMPLIFIED (removed duplication)
   * @param {Object} eventData - Event data from backend  
   * @param {Function} responseCallback - Callback to send response to backend
   */
  async handleUIToolEvent(eventData, responseCallback) {
    try {
      console.log('🎯 DynamicUIHandler: Processing UI tool event', eventData);
      console.log('🎯 DynamicUIHandler: responseCallback type:', typeof responseCallback);

      const { ui_tool_id, payload, eventId, workflow_name } = eventData;

      if (!ui_tool_id) {
        console.error('❌ Missing ui_tool_id in UI tool event');
        return null;
      }

      // Create response handler that sends data back to backend
      const onResponse = async (response) => {
        const tlog = createToolsLogger({ tool: ui_tool_id, eventId, workflowName: workflow_name, agentMessageId: payload?.agent_message_id });
        tlog.event('ui_response', response?.status || 'unknown');
        console.log(`📤 DynamicUIHandler: Sending UI tool response for ${ui_tool_id}`, response);
        
        if (responseCallback && typeof responseCallback === 'function') {
          await responseCallback({
            type: 'ui_tool_response',
            ui_tool_id,
            eventId,
            workflow_name,
            payload,
            response
          });
        } else {
          console.warn('⚠️ No response callback available for UI tool response');
        }
      };

  // Determine display mode ('inline' or 'artifact') with robust fallbacks
  const display = eventData.display || eventData.display_type || (payload && (payload.display || payload.mode)) || 'inline';

      // SIMPLIFIED: Just notify UI callbacks - let ChatInterface handle rendering
      // This eliminates duplication with eventDispatcher
  this.notifyUIUpdate({
        type: 'ui_tool_event',
        ui_tool_id,
        payload,
        eventId,
        workflow_name,
        display,
        onResponse
      });

  console.log(`✅ DynamicUIHandler: Notified UI callbacks for ${ui_tool_id} (display=${display})`);

      return true; // Indicate successful processing

    } catch (error) {
      console.error('❌ DynamicUIHandler: Error handling UI tool event', error);
      return null;
    }
  }

  /**
  * Bridge simple user_input_request events into a standardized ui_tool_event
  * so the chat can render an inline component based on backend-provided metadata.
   */
  async handleUserInputRequest(data) {
    try {
      const { input_request_id, chat_id, payload = {} } = data || {};

  // Only route to UI if the backend explicitly provides a tool/component
  const prompt = payload.prompt || '';
  const uiToolId = payload.ui_tool_id || payload.component_type || null;

      // If we can't infer a component, don't inject anything; let chat text stand
      if (!uiToolId) {
        console.warn('⚠️ DynamicUIHandler: user_input_request did not match a known UI tool; skipping component injection');
        return false;
      }

      // Emit a unified ui_tool_event for UI consumers
      this.notifyUIUpdate({
        type: 'ui_tool_event',
        ui_tool_id: uiToolId,
        eventId: input_request_id,
        workflowname: payload.workflow_name || payload.workflow,
        payload: {
          ...payload,
          chat_id,
          // Ensure router has needed routing hints
          workflow_name: payload.workflow_name || payload.workflow,
          workflow: payload.workflow_name || payload.workflow,
          component_type: uiToolId,
          // Surface the original prompt so it can be displayed next to the UI control
          description: prompt
        }
      });

      return true;
    } catch (error) {
      console.error('❌ DynamicUIHandler: Error handling user_input_request', error);
      return null;
    }
  }
}

// Export singleton instance
export const dynamicUIHandler = new DynamicUIHandler();
export default dynamicUIHandler;
