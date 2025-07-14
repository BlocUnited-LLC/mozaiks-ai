/**
 * Simple Events System
 * Handles our core event types without unnecessary complexity
 */

// Simple event types
export const SIMPLE_EVENT_TYPES = {
  CHAT_MESSAGE: "chat_message",
  ROUTE_TO_ARTIFACT: "route_to_artifact",
  ROUTE_TO_CHAT: "route_to_chat", 
  UI_TOOL_ACTION: "ui_tool_action",
  STATUS: "status",
  ERROR: "error"
};

/**
 * Simple Event Processor
 * Processes our simplified events
 */
export class SimpleEventProcessor {
  constructor(artifactManager, chatInterface, config = {}) {
    this.artifactManager = artifactManager;
    this.chatInterface = chatInterface;
    this.config = config;
    
    console.log('✅ Simple Event Processor initialized');
  }

  /**
   * Process incoming simple event
   */
  processEvent(event) {
    try {
      const parsedEvent = typeof event === 'string' ? JSON.parse(event) : event;
      
      // Validate event has required fields
      if (!parsedEvent.type) {
        console.warn('Invalid event: missing type', parsedEvent);
        return;
      }
      
      switch (parsedEvent.type) {
        case SIMPLE_EVENT_TYPES.CHAT_MESSAGE:
          this.handleChatMessage(parsedEvent);
          break;
          
        case SIMPLE_EVENT_TYPES.ROUTE_TO_ARTIFACT:
          this.handleArtifactRoute(parsedEvent);
          break;
          
        case SIMPLE_EVENT_TYPES.ROUTE_TO_CHAT:
          this.handleInlineComponentRoute(parsedEvent);
          break;
          
        case SIMPLE_EVENT_TYPES.UI_TOOL_ACTION:
          this.handleUIToolAction(parsedEvent);
          break;
          
        case SIMPLE_EVENT_TYPES.STATUS:
          this.handleStatus(parsedEvent);
          break;
          
        case SIMPLE_EVENT_TYPES.ERROR:
          this.handleError(parsedEvent);
          break;
          
        default:
          console.log('Unknown event type:', parsedEvent.type);
          // Pass through to chat interface
          this.chatInterface.addMessage?.({
            sender: 'system',
            content: `Unknown event: ${parsedEvent.type}`,
            timestamp: Date.now()
          });
          break;
      }
    } catch (error) {
      console.error('Error processing simple event:', error, event);
    }
  }

  /**
   * Handle chat message
   */
  handleChatMessage(event) {
    const { content, sender, role } = event.data;
    
    this.chatInterface.addMessage?.({
      content: content,
      sender: sender || 'assistant',
      role: role || 'assistant',
      timestamp: event.timestamp || Date.now()
    });
  }

  /**
   * Handle artifact component routing (full-featured right panel components)
   */
  handleArtifactRoute(event) {
    const { title, content, category, artifact_id, component_name, component_data } = event.data;
    
    // Create artifact in artifact manager with component info
    this.artifactManager.createArtifact?.({
      id: artifact_id,
      title: title,
      content: content,
      category: category || 'general',
      componentName: component_name,
      componentData: component_data,
      needsWorkflowResolution: true,
      timestamp: event.timestamp || Date.now()
    });
    
    console.log(`📄 Created artifact component: ${component_name || title}`);
  }

  /**
   * Handle inline component routing (lightweight UI elements in chat)
   */
  handleInlineComponentRoute(event) {
    const { content, component_name, component_data } = event.data;
    
    // Add as chat message with inline component
    this.chatInterface.addMessage?.({
      content: content,
      sender: 'assistant',
      type: 'inline_component',
      inlineComponent: {
        name: component_name,
        data: component_data,
        // Let the UI loader resolve the actual component from workflow
        needsWorkflowResolution: true
      },
      timestamp: event.timestamp || Date.now()
    });
    
    console.log(`🔧 Routed to inline component: ${component_name}`);
  }

  /**
   * Handle UI tool action
   */
  handleUIToolAction(event) {
    const { tool_id, action_type, payload } = event.data;
    
    // Emit UI tool action for components to handle
    if (this.config.onUIToolAction) {
      this.config.onUIToolAction(tool_id, action_type, payload);
    }
    
    console.log(`🔧 UI Tool Action: ${tool_id} - ${action_type}`);
  }

  /**
   * Handle status message
   */
  handleStatus(event) {
    const { message } = event.data;
    
    this.chatInterface.addMessage?.({
      content: message,
      sender: 'system',
      type: 'status',
      timestamp: event.timestamp || Date.now()
    });
  }

  /**
   * Handle error message
   */
  handleError(event) {
    const { message, code } = event.data;
    
    this.chatInterface.addMessage?.({
      content: `Error: ${message}`,
      sender: 'system',
      type: 'error',
      timestamp: event.timestamp || Date.now()
    });
    
    console.error('Event error:', message, code);
  }
}

/**
 * React Hook for Simple Event Processing
 */
export function useSimpleEvents(transport, artifactManager, chatInterface, config = {}) {
  const [processor, setProcessor] = React.useState(null);

  React.useEffect(() => {
    if (!transport || !artifactManager || !chatInterface) return;

    const eventProcessor = new SimpleEventProcessor(artifactManager, chatInterface, config);
    setProcessor(eventProcessor);

    // Set up transport event listeners
    const handleTransportMessage = (data) => {
      eventProcessor.processEvent(data);
    };

    // Listen for events from transport
    transport.addEventListener?.('message', handleTransportMessage);
    transport.onmessage = handleTransportMessage; // Fallback for different transport types

    return () => {
      transport.removeEventListener?.('message', handleTransportMessage);
      transport.onmessage = null;
    };
  }, [transport, artifactManager, chatInterface]);

  return {
    processor
  };
}

/**
 * Simple Action Handler for sending actions back to backend
 */
export class SimpleActionHandler {
  constructor(transport) {
    this.transport = transport;
  }

  async sendChatMessage(content) {
    await this.transport.send({
      type: SIMPLE_EVENT_TYPES.CHAT_MESSAGE,
      data: { content, sender: 'user', role: 'user' }
    });
  }

  async sendUIToolAction(toolId, actionType, payload) {
    await this.transport.send({
      type: SIMPLE_EVENT_TYPES.UI_TOOL_ACTION,
      data: { tool_id: toolId, action_type: actionType, payload }
    });
  }
}

export default {
  SimpleEventProcessor,
  useSimpleEvents,
  SimpleActionHandler,
  SIMPLE_EVENT_TYPES
};