import { BaseTransport } from './BaseTransport.js';

/**
 * WebSocket Transport Implementation
 * Handles bidirectional real-time communication via WebSocket
 */
export class WebSocketTransport extends BaseTransport {
  constructor() {
    super();
    this.ws = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 1000;
    this.connectionUrl = null;
  }

  async connect(config) {
    const { workflowType, enterpriseId, userId, chatId, baseUrl = 'ws://localhost:8000' } = config;
    
    this.connectionUrl = `${baseUrl}/ws/${workflowType}/${enterpriseId}/${chatId}/${userId}`;
    
    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(this.connectionUrl);
        
        this.ws.onopen = () => {
          console.log('WebSocket connected');
          this.isConnected = true;
          this.reconnectAttempts = 0;
          this._emitStatusChange('connected');
          resolve();
        };

        this.ws.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data);
            this._emitMessage(message);
          } catch (error) {
            console.error('Failed to parse WebSocket message:', error);
            this._emitError(new Error('Invalid message format'));
          }
        };

        this.ws.onclose = (event) => {
          console.log('WebSocket disconnected:', event.code, event.reason);
          this.isConnected = false;
          this._emitStatusChange('disconnected');
          
          // Auto-reconnect if not manually closed
          if (event.code !== 1000 && this.reconnectAttempts < this.maxReconnectAttempts) {
            this._attemptReconnect();
          }
        };

        this.ws.onerror = (error) => {
          console.error('WebSocket error:', error);
          this._emitError(new Error('WebSocket connection failed'));
          reject(error);
        };

        // Connection timeout
        setTimeout(() => {
          if (this.ws.readyState !== WebSocket.OPEN) {
            reject(new Error('WebSocket connection timeout'));
          }
        }, 10000);

      } catch (error) {
        reject(error);
      }
    });
  }

  async disconnect() {
    if (this.ws) {
      this.ws.close(1000, 'Manual disconnect');
      this.ws = null;
    }
    this.isConnected = false;
    this._emitStatusChange('disconnected');
  }

  async send(message) {
    if (!this.isConnected || !this.ws) {
      throw new Error('WebSocket not connected');
    }

    const payload = {
      type: 'user_input',
      ...message
    };

    this.ws.send(JSON.stringify(payload));
  }

  _attemptReconnect() {
    this.reconnectAttempts++;
    this._emitStatusChange('reconnecting');
    
    console.log(`Attempting to reconnect... (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
    
    setTimeout(async () => {
      try {
        if (this.connectionUrl) {
          this.ws = new WebSocket(this.connectionUrl);
          this._setupWebSocketHandlers();
        }
      } catch (error) {
        console.error('Reconnection failed:', error);
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
          this._attemptReconnect();
        } else {
          this._emitError(new Error('Max reconnection attempts reached'));
        }
      }
    }, this.reconnectDelay * this.reconnectAttempts);
  }

  _setupWebSocketHandlers() {
    if (!this.ws) return;

    this.ws.onopen = () => {
      console.log('WebSocket reconnected');
      this.isConnected = true;
      this.reconnectAttempts = 0;
      this._emitStatusChange('connected');
    };

    this.ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        this._emitMessage(message);
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error);
        this._emitError(new Error('Invalid message format'));
      }
    };

    this.ws.onclose = (event) => {
      console.log('WebSocket disconnected:', event.code, event.reason);
      this.isConnected = false;
      this._emitStatusChange('disconnected');
      
      if (event.code !== 1000 && this.reconnectAttempts < this.maxReconnectAttempts) {
        this._attemptReconnect();
      }
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
      this._emitError(new Error('WebSocket connection failed'));
    };
  }
}