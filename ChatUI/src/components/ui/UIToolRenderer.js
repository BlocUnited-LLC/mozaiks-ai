// ==============================================================================
// FILE: ChatUI/src/components/UIToolRenderer.js
// DESCRIPTION: Component that renders UI tools from backend events
// ==============================================================================

import React from 'react';
import { handleEvent } from '../../core/eventDispatcher';

/**
 * UIToolRenderer - Renders UI tools from backend events
 * 
 * This component receives UI tool events from the backend and renders
 * the appropriate UI component using the event dispatcher.
 */
const UIToolRenderer = ({ 
  event, 
  onResponse,
  className = ""
}) => {
  // Validate event structure
  if (!event || !event.toolId) {
    console.warn('⚠️ UIToolRenderer: Invalid event structure', event);
    return (
      <div className={`ui-tool-error ${className}`}>
        <p className="text-red-400">Invalid UI tool event</p>
      </div>
    );
  }

  try {
    // Use the event dispatcher to render the component
    const renderedComponent = handleEvent(event, onResponse);

    if (!renderedComponent) {
      return (
        <div className={`ui-tool-not-found ${className}`}>
          <p className="text-yellow-400">
            UI tool '{event.toolId}' not found or failed to load
          </p>
          <p className="text-gray-400 text-sm">
            Check if the workflow is properly registered
          </p>
        </div>
      );
    }

    return (
      <div className={`ui-tool-container ${className}`}>
        {renderedComponent}
      </div>
    );

  } catch (error) {
    console.error('❌ UIToolRenderer: Error rendering UI tool', error);
    return (
      <div className={`ui-tool-error ${className}`}>
        <p className="text-red-400">Error rendering UI tool: {event.toolId}</p>
        <p className="text-gray-400 text-sm">{error.message}</p>
      </div>
    );
  }
};

export default UIToolRenderer;
