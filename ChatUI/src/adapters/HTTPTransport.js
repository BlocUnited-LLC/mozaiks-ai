import { BaseTransport } from './BaseTransport.js';

/**
 * HTTP Transport Implementation (Polling Fallback)
 * Handles request/response communication via HTTP polling
 */
export class HTTPTransport extends BaseTransport {
  constructor() {
    super();
    this.pollingInterval = null;
    this.pollingDelay = 2000; // 2 seconds
    this.config = null;
    this.lastMessageId = null;
  }

  async connect(config) {
    const { workflowType, enterpriseId, userId, chatId, baseUrl = 'http://localhost:8000' } = config;
    this.config = config;
    
    try {
      // Test connection
      const testUrl = `${baseUrl}/api/workflows/${workflowType}/transport`;
      const response = await fetch(testUrl);
      
      if (!response.ok) {
        throw new Error(`HTTP transport not available: ${response.status}`);
      }

      this.isConnected = true;
      this._emitStatusChange('connected');
      this._startPolling();
      
      console.log('HTTP transport connected (polling mode)');
      
    } catch (error) {
      console.error('HTTP transport connection failed:', error);
      this._emitError(error);
      throw error;
    }
  }

  async disconnect() {
    this._stopPolling();
    this.isConnected = false;
    this._emitStatusChange('disconnected');
  }

  async send(message) {
    const { workflowType, enterpriseId, userId, chatId, baseUrl = 'http://localhost:8000' } = this.config;
    
    const inputUrl = `${baseUrl}/chat/${enterpriseId}/${chatId}/${userId}/input`;
    
    try {
      const response = await fetch(inputUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: message.message || message.content || message,
          workflow_type: workflowType
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      // Immediately poll for response
      setTimeout(() => this._pollMessages(), 100);

    } catch (error) {
      console.error('Failed to send HTTP message:', error);
      this._emitError(error);
      throw error;
    }
  }

  _startPolling() {
    if (this.pollingInterval) {
      clearInterval(this.pollingInterval);
    }

    this.pollingInterval = setInterval(() => {
      this._pollMessages();
    }, this.pollingDelay);
  }

  _stopPolling() {
    if (this.pollingInterval) {
      clearInterval(this.pollingInterval);
      this.pollingInterval = null;
    }
  }

  async _pollMessages() {
    if (!this.isConnected || !this.config) return;

    const { workflowType, enterpriseId, userId, chatId, baseUrl = 'http://localhost:8000' } = this.config;
    
    try {
      // Poll for new messages
      const messagesUrl = `${baseUrl}/api/chats/${enterpriseId}/${chatId}/messages`;
      const params = new URLSearchParams();
      if (this.lastMessageId) {
        params.append('after', this.lastMessageId);
      }
      
      const response = await fetch(`${messagesUrl}?${params}`);
      
      if (!response.ok) {
        console.warn(`Polling failed: ${response.status}`);
        return;
      }

      const data = await response.json();
      
      if (data.messages && data.messages.length > 0) {
        data.messages.forEach(message => {
          this._emitMessage(message);
          this.lastMessageId = message.id || message.timestamp;
        });
      }

    } catch (error) {
      console.error('Polling error:', error);
      // Don't emit error for polling failures - they're expected in HTTP mode
    }
  }
}