// ==============================================================================
// FILE: ChatUI/src/eventDispatcher.js
// DESCRIPTION: Handles UI tool events and renders appropriate components
// ==============================================================================

import React from 'react';
import { getUiToolComponent, getToolMetadata } from './uiToolRegistry';

/**
 * Event Dispatcher for UI Tools
 * 
 * Receives events from backend and renders the appropriate UI component
 * based on the toolId in the event payload.
 */

class EventDispatcher {
  constructor() {
    this.activeEvents = new Map(); // Track active UI events
    this.eventHistory = []; // Keep history for debugging
    this.eventHandlers = new Map(); // Custom event handlers
  }

  /**
   * Handle a UI tool event from the backend
   * @param {Object} event - Event object with toolId and payload
   * @param {Function} onResponse - Callback to send response back to backend
   * @returns {React.Element|null} - Rendered component or null
   */
  handleEvent(event, onResponse = null) {
    try {
      const { toolId, payload = {}, eventId, workflowName } = event;

      if (!toolId) {
        console.error('❌ EventDispatcher: Missing toolId in event', event);
        return null;
      }

      console.log(`🎯 EventDispatcher: Handling event for tool '${toolId}'`);

      // Get the component for this tool
      const Component = getUiToolComponent(toolId);
      if (!Component) {
        console.error(`❌ EventDispatcher: No component found for tool '${toolId}'`);
        return this.renderErrorComponent(toolId, 'Component not found');
      }

      // Get metadata for additional context
      const metadata = getToolMetadata(toolId);

      // Track this active event
      if (eventId) {
        this.activeEvents.set(eventId, {
          toolId,
          payload,
          workflowName,
          startTime: Date.now(),
          status: 'active'
        });
      }

      // Add to event history
      this.eventHistory.push({
        toolId,
        eventId,
        workflowName,
        timestamp: new Date().toISOString(),
        status: 'handled'
      });

      // Create response handler
      const responseHandler = (response) => {
        console.log(`📤 EventDispatcher: Sending response for tool '${toolId}'`, response);
        
        // Update active event status
        if (eventId && this.activeEvents.has(eventId)) {
          const activeEvent = this.activeEvents.get(eventId);
          activeEvent.status = 'completed';
          activeEvent.endTime = Date.now();
          activeEvent.response = response;
        }

        // Call the original response handler
        if (onResponse) {
          onResponse(response);
        }
      };

      // Render the component with enhanced props
      return React.createElement(Component, {
        ...payload,
        toolId,
        eventId,
        workflowName,
        metadata,
        onResponse: responseHandler,
      });

    } catch (error) {
      console.error('❌ EventDispatcher: Error handling event', error);
      return this.renderErrorComponent(event?.toolId, error.message);
    }
  }

  /**
   * Render an error component when tool loading fails
   * @param {string} toolId - The tool that failed to load
   * @param {string} errorMessage - Error description
   * @returns {React.Element} - Error component
   */
  renderErrorComponent(toolId, errorMessage) {
    return React.createElement('div', {
      className: 'ui-tool-error',
      style: {
        padding: '16px',
        border: '1px solid #ef4444',
        borderRadius: '8px',
        backgroundColor: '#fef2f2',
        color: '#dc2626'
      }
    }, [
      React.createElement('h4', { key: 'title' }, `UI Tool Error: ${toolId}`),
      React.createElement('p', { key: 'message' }, errorMessage),
      React.createElement('small', { key: 'help' }, 'Check console for more details.')
    ]);
  }

  /**
   * Register a custom event handler for specific event types
   * @param {string} eventType - Type of event to handle
   * @param {Function} handler - Handler function
   */
  registerEventHandler(eventType, handler) {
    this.eventHandlers.set(eventType, handler);
    console.log(`📝 EventDispatcher: Registered handler for event type '${eventType}'`);
  }

  /**
   * Get active events (useful for debugging)
   * @returns {Object} - Map of active events
   */
  getActiveEvents() {
    return Object.fromEntries(this.activeEvents);
  }

  /**
   * Get event history
   * @returns {Array} - Array of handled events
   */
  getEventHistory() {
    return [...this.eventHistory];
  }

  /**
   * Clear completed events from active tracking
   */
  cleanupCompletedEvents() {
    let cleaned = 0;
    for (const [eventId, event] of this.activeEvents) {
      if (event.status === 'completed' || event.status === 'cancelled') {
        this.activeEvents.delete(eventId);
        cleaned++;
      }
    }
    if (cleaned > 0) {
      console.log(`🧹 EventDispatcher: Cleaned up ${cleaned} completed events`);
    }
  }

  /**
   * Get dispatcher statistics
   * @returns {Object} - Dispatcher stats
   */
  getStats() {
    return {
      activeEvents: this.activeEvents.size,
      totalEventsHandled: this.eventHistory.length,
      customHandlers: this.eventHandlers.size
    };
  }
}

// Create singleton instance
const eventDispatcher = new EventDispatcher();

// Export both the instance and the main handler for convenience
export default eventDispatcher;

export const handleEvent = (event, onResponse) => 
  eventDispatcher.handleEvent(event, onResponse);

export const registerEventHandler = (eventType, handler) =>
  eventDispatcher.registerEventHandler(eventType, handler);

export const getActiveEvents = () =>
  eventDispatcher.getActiveEvents();

export const getEventHistory = () =>
  eventDispatcher.getEventHistory();
