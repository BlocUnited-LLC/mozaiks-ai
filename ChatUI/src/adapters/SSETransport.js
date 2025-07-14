import { BaseTransport } from './BaseTransport.js';
import { SimpleEventProcessor } from '../core/simpleEvents.js';

/**
 * Server-Sent Events (SSE) Transport Implementation with Simple Events
 * Handles one-way streaming communication from server to client
 * Uses simplified event system
 */
export class SSETransport extends BaseTransport {
  constructor() {
    super();
    this.eventSource = null;
    this.config = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 1000;
    this.simpleEventProcessor = null;
  }

  /**
   * Initialize Simple Event processor
   */
  initializeSimpleEventProcessor(artifactManager, chatInterface, config = {}) {
    this.simpleEventProcessor = new SimpleEventProcessor(artifactManager, chatInterface, config);
  }

  async connect(config) {
    const { workflowType, enterpriseId, userId, chatId, baseUrl = 'http://localhost:8000' } = config;
    this.config = config;
    
    const sseUrl = `${baseUrl}/sse/${workflowType}/${enterpriseId}/${chatId}/${userId}`;
    
    return new Promise((resolve, reject) => {
      try {
        this.eventSource = new EventSource(sseUrl);
        
        this.eventSource.onopen = () => {
          console.log('SSE connected with Simple Events support');
          this.isConnected = true;
          this.reconnectAttempts = 0;
          this._emitStatusChange('connected');
          resolve();
        };

        this.eventSource.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data);
            
            // Process through Simple Event processor if available
            if (this.simpleEventProcessor) {
              this.simpleEventProcessor.processEvent(message);
            }
            
            // Also emit to traditional listeners for compatibility
            this._emitMessage(message);
            
          } catch (error) {
            console.error('Error parsing SSE message:', error, event.data);
            // Try to emit raw data for debugging
            this._emitMessage({ 
              type: 'raw', 
              data: event.data,
              error: error.message 
            });
          }
        };

        this.eventSource.onerror = (error) => {
          console.error('SSE error:', error);
          this.isConnected = false;
          this._emitStatusChange('disconnected');
          
          // Auto-reconnect on error
          if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this._attemptReconnect();
          } else {
            this._emitError(new Error('SSE connection failed'));
            reject(error);
          }
        };

        // Connection timeout
        setTimeout(() => {
          if (this.eventSource.readyState !== EventSource.OPEN) {
            reject(new Error('SSE connection timeout'));
          }
        }, 10000);

      } catch (error) {
        reject(error);
      }
    });
  }

  async disconnect() {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
    this.isConnected = false;
    this._emitStatusChange('disconnected');
  }

  async send(message) {
    // SSE is one-way, so we send via HTTP POST
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

    } catch (error) {
      console.error('Failed to send message via SSE:', error);
      this._emitError(error);
      throw error;
    }
  }

  _attemptReconnect() {
    this.reconnectAttempts++;
    this._emitStatusChange('reconnecting');
    
    console.log(`Attempting to reconnect SSE... (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
    
    setTimeout(async () => {
      try {
        if (this.config) {
          await this.connect(this.config);
        }
      } catch (error) {
        console.error('SSE reconnection failed:', error);
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
          this._attemptReconnect();
        } else {
          this._emitError(new Error('Max SSE reconnection attempts reached'));
        }
      }
    }, this.reconnectDelay * this.reconnectAttempts);
  }
}