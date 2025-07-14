/**
 * Transport Configuration
 * Dynamic transport selection based on workflow type
 * Mi/**
 * Get transport type for a specific workflow with dynamic fallback
 * @param {string} workflowType - The workflow type
 * @returns {string} Transport type ('websocket', 'sse', or 'http')
 */
export function getWorkflowTransport(workflowType) {
  // Check if we have dynamic config for this workflow
  if (transportConfig.workflows[workflowType]) {
    return transportConfig.workflows[workflowType];
  }
  
  // If no dynamic config and no workflows loaded, trigger fetch
  if (Object.keys(transportConfig.workflows).length === 0) {
    console.warn(`⚠️ No transport config for workflow '${workflowType}', consider calling fetchWorkflowTransports() first`);
  }
  
  // Default fallback
  return 'sse'; // Safe default for most workflows
}

export const transportConfig = {
  // Dynamic transport discovery - fetched from backend at runtime
  // No hardcoded workflow mappings - backend provides transport preferences
  workflows: {}, // Populated by fetchWorkflowTransports()

  // Fallback chains - if primary transport fails, try these in order
  fallbackChains: {
    websocket: ['websocket', 'sse', 'http'],  // WebSocket -> SSE -> HTTP
    sse: ['sse', 'http', 'websocket'],        // SSE -> HTTP -> WebSocket  
    http: ['http']                            // HTTP only (no fallback)
  },

  // Base URLs for each transport type
  endpoints: {
    websocket: process.env.REACT_APP_WS_URL || 'ws://localhost:8000',
    sse: process.env.REACT_APP_SSE_URL || 'http://localhost:8000',
    http: process.env.REACT_APP_HTTP_URL || 'http://localhost:8000'
  },

  // Feature flags for debugging and development
  features: {
    enableDebugLogging: process.env.NODE_ENV === 'development',
    enableFallback: true,
    maxReconnectAttempts: 5,
    reconnectDelay: 1000,
    enableConnectionStatus: true,
    enableTransportSwitching: false,  // Future feature
    // 🆕 Simple Events Integration features
    enableSimpleEvents: true,
    enableUIToolActions: true,
    enableArtifactRouting: true
  },

  // 🆕 Simple Events Integration settings
  simpleEvents: {
    // Map backend event types to frontend handlers
    eventMap: {
      'route_to_artifact': 'artifact_create',
      'route_to_chat': 'chat_component_create', 
      'ui_tool_action': 'ui_tool',
      'chat_message': 'message'
    },
    
    // Simplified tool mapping for UI components
    toolMapping: {
      progressTracker: 'progress',
      formBuilder: 'form',
      codePreview: 'code',
      fileTree: 'table',
      exportOptions: 'choices',
      validationResults: 'table'
    },

    // Default configuration
    enableDebugOutput: process.env.NODE_ENV === 'development'
  },

  // Connection timeouts (milliseconds)
  timeouts: {
    connection: 10000,  // 10 seconds
    response: 30000,    // 30 seconds
    polling: 2000       // 2 seconds for HTTP polling
  }
};

/**
 * Fetch workflow transport configurations from backend
 * Replaces hardcoded workflow mappings with dynamic discovery
 */
export async function fetchWorkflowTransports() {
  try {
    const response = await fetch('/api/workflows/transports');
    if (response.ok) {
      const workflowTransports = await response.json();
      transportConfig.workflows = workflowTransports;
      console.log('✅ Dynamic workflow transports loaded:', Object.keys(workflowTransports));
      return workflowTransports;
    } else {
      console.warn('⚠️ Failed to fetch workflow transports, using fallback');
      return {};
    }
  } catch (error) {
    console.warn('⚠️ Error fetching workflow transports:', error);
    return {};
  }
}

/**
 * Get transport type for a specific workflow
 * @param {string} workflowType - The workflow type
 * @returns {string} Transport type ('websocket', 'sse', or 'http')
 */
export function getWorkflowTransport(workflowType) {
  return transportConfig.workflows[workflowType] || transportConfig.workflows.default;
}

/**
 * Get fallback chain for a transport type
 * @param {string} transportType - Primary transport type
 * @returns {Array<string>} Ordered list of transport types to try
 */
export function getFallbackChain(transportType) {
  return transportConfig.fallbackChains[transportType] || [transportType];
}

/**
 * Get endpoint URL for a transport type
 * @param {string} transportType - Transport type
 * @returns {string} Base URL for the transport
 */
export function getTransportEndpoint(transportType) {
  return transportConfig.endpoints[transportType];
}

/**
 * Check if a feature is enabled
 * @param {string} featureName - Feature name
 * @returns {boolean} True if feature is enabled
 */
export function isFeatureEnabled(featureName) {
  return transportConfig.features[featureName] || false;
}

/**
 * Update transport configuration at runtime
 * @param {Object} newConfig - Configuration updates to merge
 */
export function updateTransportConfig(newConfig) {
  Object.assign(transportConfig, newConfig);
}

export default transportConfig;
