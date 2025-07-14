/**
 * Simple Bridge Service
 * Straightforward event handling
 */

import { SIMPLE_EVENT_TYPES } from '../core/simpleEvents.js';

export class SimpleBridge {
  constructor() {
    this.transportConnection = null;
    this.messageHandlers = [];
    console.log('✅ Simple Bridge initialize');
  }

  /**
   * Connect the bridge to a transport connection
   */
  connect(transportConnection) {
    this.transportConnection = transportConnection;
    console.log('🔗 Simple Bridge connected to transport');
  }

  /**
   * Disconnect the bridge
   */
  disconnect() {
    this.transportConnection = null;
    console.log('🔌 Simple Bridge disconnected');
  }

  /**
   * Handle messages from the transport layer
   */
  async handleTransportMessage(message) {
    try {
      // Simple routing based on event type
      switch (message.type) {
        case SIMPLE_EVENT_TYPES.CHAT_MESSAGE:
        case SIMPLE_EVENT_TYPES.ROUTE_TO_ARTIFACT:
        case SIMPLE_EVENT_TYPES.ROUTE_TO_CHAT:
        case SIMPLE_EVENT_TYPES.UI_TOOL_ACTION:
        case SIMPLE_EVENT_TYPES.STATUS:
        case SIMPLE_EVENT_TYPES.ERROR:
          // Pass simple events through
          this.emitMessage(message);
          break;
          
        // Handle legacy event types for backward compatibility
        case 'ui_tool':
          await this.handleLegacyUITool(message);
          break;
          
        case 'text_message_start':
        case 'text_message_content':
        case 'text_message_end':
          await this.handleLegacyTextMessage(message);
          break;
          
        default:
          // Pass through unknown messages
          this.emitMessage(message);
          break;
      }
    } catch (error) {
      console.error('Error in Simple Bridge message handler:', error);
      this.emitMessage({
        type: SIMPLE_EVENT_TYPES.ERROR,
        data: { message: 'Bridge processing error', code: 'BRIDGE_ERROR' },
        timestamp: Date.now()
      });
    }
  }

  /**
   * Handle legacy UI tool events (convert to simple format)
   */
  async handleLegacyUITool(message) {
    const { toolId, payload } = message.data || {};
    
    this.emitMessage({
      type: SIMPLE_EVENT_TYPES.UI_TOOL_ACTION,
      data: {
        tool_id: toolId,
        action_type: 'legacy_ui_tool',
        payload: payload
      },
      timestamp: Date.now()
    });
  }

  /**
   * Handle legacy text message events (convert to simple format)
   */
  async handleLegacyTextMessage(message) {
    // Convert legacy streaming messages to simple chat messages
    if (message.type === 'text_message_end') {
      this.emitMessage({
        type: SIMPLE_EVENT_TYPES.CHAT_MESSAGE,
        data: {
          content: message.content || 'Message received',
          sender: message.sender || 'assistant',
          role: 'assistant'
        },
        timestamp: Date.now()
      });
    }
    // Ignore start/content for now - could be enhanced for streaming
  }

  /**
   * Send message from frontend to backend
   */
  async sendToBackend(message) {
    if (!this.transportConnection) {
      throw new Error('No transport connection available');
    }

    // Convert different message types to simple format
    if (message.type === 'user_message') {
      await this.transportConnection.send({
        type: SIMPLE_EVENT_TYPES.CHAT_MESSAGE,
        data: {
          content: message.content || message.message,
          sender: 'user',
          role: 'user'
        }
      });
    } else if (message.type === 'ui_tool_action') {
      await this.transportConnection.send({
        type: SIMPLE_EVENT_TYPES.UI_TOOL_ACTION,
        data: {
          tool_id: message.tool_id,
          action_type: message.action_type,
          payload: message.data
        }
      });
    } else {
      // Send as-is for other message types
      await this.transportConnection.send(message);
    }
  }

  /**
   * Add message handler
   */
  onMessage(handler) {
    this.messageHandlers.push(handler);
  }

  /**
   * Emit message to all handlers
   */
  emitMessage(message) {
    this.messageHandlers.forEach(handler => {
      try {
        handler(message);
      } catch (error) {
        console.error('Error in message handler:', error);
      }
    });
  }
}

// Export singleton instance
export const simpleBridge = new SimpleBridge();
export default simpleBridge;
