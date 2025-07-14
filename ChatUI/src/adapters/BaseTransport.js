/**
 * Base Transport Interface
 * Provides a common interface for all transport methods (WebSocket, SSE, HTTP)
 */
export class BaseTransport {
  constructor() {
    this.isConnected = false;
    this.messageHandlers = new Set();
    this.errorHandlers = new Set();
    this.statusHandlers = new Set();
  }

  /**
   * Connect to the transport
   * @param {Object} config - Connection configuration
   */
  async connect(config) {
    throw new Error('connect() must be implemented by transport');
  }

  /**
   * Disconnect from the transport
   */
  async disconnect() {
    throw new Error('disconnect() must be implemented by transport');
  }

  /**
   * Send a message via the transport
   * @param {Object} message - Message to send
   */
  async send(message) {
    throw new Error('send() must be implemented by transport');
  }

  /**
   * Add message handler
   * @param {Function} handler - Message handler function
   */
  onMessage(handler) {
    this.messageHandlers.add(handler);
    return () => this.messageHandlers.delete(handler);
  }

  /**
   * Add error handler
   * @param {Function} handler - Error handler function
   */
  onError(handler) {
    this.errorHandlers.add(handler);
    return () => this.errorHandlers.delete(handler);
  }

  /**
   * Add status change handler
   * @param {Function} handler - Status change handler function
   */
  onStatusChange(handler) {
    this.statusHandlers.add(handler);
    return () => this.statusHandlers.delete(handler);
  }

  /**
   * Emit message to all handlers
   * @param {Object} message - Message to emit
   */
  _emitMessage(message) {
    this.messageHandlers.forEach(handler => {
      try {
        handler(message);
      } catch (error) {
        console.error('Error in message handler:', error);
      }
    });
  }

  /**
   * Emit error to all handlers
   * @param {Error} error - Error to emit
   */
  _emitError(error) {
    this.errorHandlers.forEach(handler => {
      try {
        handler(error);
      } catch (err) {
        console.error('Error in error handler:', err);
      }
    });
  }

  /**
   * Emit status change to all handlers
   * @param {string} status - New status
   */
  _emitStatusChange(status) {
    this.statusHandlers.forEach(handler => {
      try {
        handler(status);
      } catch (error) {
        console.error('Error in status handler:', error);
      }
    });
  }

  /**
   * Get current connection status
   */
  getStatus() {
    return this.isConnected ? 'connected' : 'disconnected';
  }
}