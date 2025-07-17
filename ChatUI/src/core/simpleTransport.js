// ==============================================================================
// FILE: ChatUI/src/core/simpleTransport.js  
// DESCRIPTION: Simplified frontend transport - matches simplified backend
// ==============================================================================

/**
 * Simple Frontend Transport
 * Connects to our simplified backend transport system
 * No over-engineering, just what we need
 */
class SimpleTransport {
  constructor() {
    this.connection = null;
    this.isConnected = false;
    this.messageHandlers = [];
    this.errorHandlers = [];
    this.statusHandlers = [];
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 3;
  }

  /**
   * Connect to backend - tries WebSocket first, falls back to SSE
   */
  async connect(chatId, userId = 'user', workflowType = 'generator', enterpriseId = '68542c1109381de738222350') {
    const baseUrl = process.env.REACT_APP_BASE_URL || 'http://localhost:8000';
    
    try {
      // Try WebSocket first (for interactive workflows)
      await this.connectWebSocket(baseUrl, chatId, userId, workflowType, enterpriseId);
    } catch (error) {
      console.log('WebSocket failed, trying SSE...', error.message);
      try {
        // Fallback to SSE (for streaming workflows)
        await this.connectSSE(baseUrl, chatId, userId, workflowType, enterpriseId);
      } catch (sseError) {
        console.error('Both WebSocket and SSE failed:', sseError);
        this.handleError(new Error('Unable to connect to backend'));
      }
    }
  }

  /**
   * Connect via WebSocket
   */
  async connectWebSocket(baseUrl, chatId, userId, workflowType, enterpriseId) {
    return new Promise((resolve, reject) => {
      const wsUrl = baseUrl.replace('http', 'ws') + `/ws/${workflowType}/${enterpriseId}/${chatId}/${userId}`;
      this.connection = new WebSocket(wsUrl);
      this.connectionType = 'websocket';

      this.connection.onopen = () => {
        console.log('✅ WebSocket connected');
        this.isConnected = true;
        this.reconnectAttempts = 0;
        this.notifyStatus('connected');
        resolve();
      };

      this.connection.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          this.handleMessage(message);
        } catch (error) {
          console.error('Failed to parse message:', error);
        }
      };

      this.connection.onclose = () => {
        this.isConnected = false;
        this.notifyStatus('disconnected');
        this.attemptReconnect(baseUrl, chatId, userId, workflowType, enterpriseId);
      };

      this.connection.onerror = (error) => {
        reject(new Error('WebSocket connection failed'));
      };
    });
  }

  /**
   * Connect via SSE  
   */
  async connectSSE(baseUrl, chatId, userId, workflowType, enterpriseId) {
    return new Promise((resolve, reject) => {
      const sseUrl = `${baseUrl}/sse/${workflowType}/${enterpriseId}/${chatId}/${userId}`;
      this.connection = new EventSource(sseUrl);
      this.connectionType = 'sse';

      this.connection.onopen = () => {
        console.log('✅ SSE connected');
        this.isConnected = true;
        this.reconnectAttempts = 0;
        this.notifyStatus('connected');
        resolve();
      };

      this.connection.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          this.handleMessage(message);
        } catch (error) {
          console.error('Failed to parse SSE message:', error);
        }
      };

      this.connection.onerror = (error) => {
        this.isConnected = false;
        this.notifyStatus('disconnected');
        reject(new Error('SSE connection failed'));
      };
    });
  }

  /**
   * Send message to backend (WebSocket only)
   */
  async sendMessage(message) {
    if (!this.isConnected || !this.connection) {
      throw new Error('Not connected');
    }

    if (this.connectionType === 'websocket') {
      const messageData = {
        type: 'user_message',
        message: message,
        timestamp: new Date().toISOString()
      };
      this.connection.send(JSON.stringify(messageData));
    } else {
      // For SSE, we'd need to make HTTP POST request
      throw new Error('Cannot send messages via SSE connection');
    }
  }

  /**
   * Handle incoming messages from backend
   */
  handleMessage(message) {
    // Simple message handling - just pass to UI
    this.messageHandlers.forEach(handler => {
      try {
        handler(message);
      } catch (error) {
        console.error('Message handler error:', error);
      }
    });
  }

  /**
   * Handle errors
   */
  handleError(error) {
    this.errorHandlers.forEach(handler => {
      try {
        handler(error);
      } catch (handlerError) {
        console.error('Error handler failed:', handlerError);
      }
    });
  }

  /**
   * Notify status changes
   */
  notifyStatus(status) {
    this.statusHandlers.forEach(handler => {
      try {
        handler(status, this.connectionType);
      } catch (error) {
        console.error('Status handler error:', error);
      }
    });
  }

  /**
   * Attempt to reconnect
   */
  async attemptReconnect(baseUrl, chatId, userId, workflowType, enterpriseId) {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      this.handleError(new Error('Max reconnection attempts reached'));
      return;
    }

    this.reconnectAttempts++;
    const delay = Math.pow(2, this.reconnectAttempts) * 1000; // Exponential backoff
    
    console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
    
    setTimeout(async () => {
      try {
        await this.connect(chatId, userId, workflowType, enterpriseId);
      } catch (error) {
        console.error('Reconnection failed:', error);
      }
    }, delay);
  }

  /**
   * Add message handler
   */
  onMessage(handler) {
    this.messageHandlers.push(handler);
  }

  /**
   * Add error handler
   */
  onError(handler) {
    this.errorHandlers.push(handler);
  }

  /**
   * Add status change handler
   */
  onStatusChange(handler) {
    this.statusHandlers.push(handler);
  }

  /**
   * Disconnect
   */
  disconnect() {
    if (this.connection) {
      if (this.connectionType === 'websocket') {
        this.connection.close();
      } else if (this.connectionType === 'sse') {
        this.connection.close();
      }
      this.connection = null;
      this.isConnected = false;
    }
  }

  /**
   * Get connection info
   */
  getConnectionInfo() {
    return {
      isConnected: this.isConnected,
      connectionType: this.connectionType,
      reconnectAttempts: this.reconnectAttempts
    };
  }
}

// Export singleton
export const simpleTransport = new SimpleTransport();
export default simpleTransport;
