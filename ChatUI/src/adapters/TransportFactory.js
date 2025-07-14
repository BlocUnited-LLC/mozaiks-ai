import { WebSocketTransport } from './WebSocketTransport.js';
import { SSETransport } from './SSETransport.js';
import { HTTPTransport } from './HTTPTransport.js';

/**
 * Transport Factory with Fallback Chain
 * Creates and manages transport instances with automatic fallback
 */
export class TransportFactory {
  constructor() {
    this.transportConfig = {
      // Fallback chains for each transport type
      fallbackChains: {
        websocket: ['websocket', 'sse', 'http'],
        sse: ['sse', 'http', 'websocket'],
        http: ['http']
      },
      
      // Environment-based overrides
      baseUrls: {
        websocket: process.env.REACT_APP_WS_URL || 'ws://localhost:8000',
        sse: process.env.REACT_APP_SSE_URL || 'http://localhost:8000',
        http: process.env.REACT_APP_HTTP_URL || 'http://localhost:8000'
      }
    };
    
    // Cache for discovered transport preferences
    this.discoveredTransports = new Map();
  }

  /**
   * Create transport for a specific workflow with automatic fallback
   * @param {string} workflowType - The workflow type
   * @param {Object} connectionParams - Connection parameters
   * @returns {Promise<BaseTransport>} Connected transport instance
   */
  async createTransport(workflowType, connectionParams) {
    const preferredTransport = await this.getPreferredTransport(workflowType);
    const fallbackChain = this.transportConfig.fallbackChains[preferredTransport] || ['http'];

    let lastError = null;

    for (const transportType of fallbackChain) {
      try {
        console.log(`Attempting ${transportType} transport for workflow: ${workflowType}`);
        
        const transport = this._createTransportInstance(transportType);
        const config = this._buildTransportConfig(transportType, workflowType, connectionParams);
        
        await transport.connect(config);
        
        console.log(`Successfully connected via ${transportType} transport`);
        return transport;
        
      } catch (error) {
        console.warn(`${transportType} transport failed:`, error.message);
        lastError = error;
        continue;
      }
    }

    throw new Error(`All transport methods failed. Last error: ${lastError?.message}`);
  }

  /**
   * Auto-discover the preferred transport type from backend
   * @param {string} workflowType - The workflow type
   * @returns {Promise<string>} Transport type ('websocket', 'sse', or 'http')
   */
  async discoverTransport(workflowType) {
    // Check cache first
    if (this.discoveredTransports.has(workflowType)) {
      return this.discoveredTransports.get(workflowType);
    }

    try {
      const response = await fetch(`${this.transportConfig.baseUrls.http}/api/workflows/${workflowType}/transport`);
      if (!response.ok) {
        throw new Error(`Failed to discover transport: ${response.status}`);
      }
      
      const data = await response.json();
      const transportType = data.transport || 'http';
      
      console.log(`Auto-discovered transport for ${workflowType}: ${transportType}`);
      
      // Cache the result
      this.discoveredTransports.set(workflowType, transportType);
      
      return transportType;
    } catch (error) {
      console.warn(`Transport discovery failed for ${workflowType}:`, error.message);
      console.log(`Falling back to 'http' transport`);
      
      // Cache the fallback
      this.discoveredTransports.set(workflowType, 'http');
      return 'http';
    }
  }

  /**
   * Get the preferred transport type for a workflow (legacy method - now uses discovery)
   * @param {string} workflowType - The workflow type
   * @returns {Promise<string>} Transport type ('websocket', 'sse', or 'http')
   */
  async getPreferredTransport(workflowType) {
    return await this.discoverTransport(workflowType);
  }

  /**
   * Create transport instance by type
   * @param {string} transportType - Transport type
   * @returns {BaseTransport} Transport instance
   */
  _createTransportInstance(transportType) {
    switch (transportType) {
      case 'websocket':
        return new WebSocketTransport();
      case 'sse':
        return new SSETransport();
      case 'http':
        return new HTTPTransport();
      default:
        throw new Error(`Unknown transport type: ${transportType}`);
    }
  }

  /**
   * Build transport configuration
   * @param {string} transportType - Transport type
   * @param {string} workflowType - Workflow type
   * @param {Object} params - Connection parameters
   * @returns {Object} Transport configuration
   */
  _buildTransportConfig(transportType, workflowType, params) {
    const baseUrl = this.transportConfig.baseUrls[transportType];
    
    return {
      workflowType,
      baseUrl,
      ...params
    };
  }

  /**
   * Update transport configuration
   * @param {Object} newConfig - New configuration to merge
   */
  updateConfig(newConfig) {
    this.transportConfig = {
      ...this.transportConfig,
      ...newConfig,
      workflows: {
        ...this.transportConfig.workflows,
        ...(newConfig.workflows || {})
      },
      fallbackChains: {
        ...this.transportConfig.fallbackChains,
        ...(newConfig.fallbackChains || {})
      },
      baseUrls: {
        ...this.transportConfig.baseUrls,
        ...(newConfig.baseUrls || {})
      }
    };
  }

  /**
   * Get available transports for a workflow
   * @param {string} workflowType - Workflow type
   * @returns {Array<string>} Available transport types in order of preference
   */
  getAvailableTransports(workflowType) {
    const preferred = this.getPreferredTransport(workflowType);
    return this.transportConfig.fallbackChains[preferred] || ['http'];
  }
}

// Export singleton instance
export const transportFactory = new TransportFactory();