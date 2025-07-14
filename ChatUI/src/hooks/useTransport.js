import { useState, useEffect, useCallback, useRef } from 'react';
import { transportFactory } from '../adapters/TransportFactory.js';
import { simpleBridge } from '../services/simpleBridge.js';
import { isFeatureEnabled } from '../config/transportConfig.js';

/**
 * Transport-agnostic React hook for communication
 * Automatically selects and connects to the appropriate transport based on workflow type
 */
export function useTransport(connectionParams) {
  const [isConnected, setIsConnected] = useState(false);
  const [status, setStatus] = useState('disconnected');
  const [messages, setMessages] = useState([]);
  const [error, setError] = useState(null);
  const [transportType, setTransportType] = useState(null);
  
  const transportRef = useRef(null);
  const isConnectingRef = useRef(false);

  // Validate required parameters
  const { workflowType, enterpriseId, userId, chatId } = connectionParams;
  
  const debugLog = useCallback((message, ...args) => {
    if (isFeatureEnabled('enableDebugLogging')) {
      console.log(`[useTransport] ${message}`, ...args);
    }
  }, []);

  // Connect to transport
  const connect = useCallback(async () => {
    if (!workflowType || !enterpriseId || !userId || !chatId) {
      const missingParams = [];
      if (!workflowType) missingParams.push('workflowType');
      if (!enterpriseId) missingParams.push('enterpriseId');
      if (!userId) missingParams.push('userId');
      if (!chatId) missingParams.push('chatId');
      
      const errorMsg = `Missing required parameters: ${missingParams.join(', ')}`;
      setError(new Error(errorMsg));
      return;
    }

    if (isConnectingRef.current || isConnected) {
      debugLog('Connection already in progress or established');
      return;
    }

    isConnectingRef.current = true;
    setStatus('connecting');
    setError(null);

    try {
      debugLog('Creating transport for workflow:', workflowType);
      
      const transport = await transportFactory.createTransport(workflowType, {
        enterpriseId,
        userId,
        chatId
      });

      // Set up event handlers
      transport.onMessage((message) => {
        debugLog('Received message:', message);
        // Route through Simple Bridge for processing
        simpleBridge.handleTransportMessage(message);
      });

      // Listen to bridge messages (processed/converted)
      simpleBridge.onMessage((message) => {
        debugLog('Bridge processed message:', message);
        setMessages(prev => [...prev, message]);
      });

      // Connect bridge to transport
      simpleBridge.connect(transport);

      transport.onError((err) => {
        debugLog('Transport error:', err);
        setError(err);
      });

      transport.onStatusChange((newStatus) => {
        debugLog('Status change:', newStatus);
        setStatus(newStatus);
        setIsConnected(newStatus === 'connected');
      });

      transportRef.current = transport;
      setTransportType(transport.constructor.name.replace('Transport', '').toLowerCase());
      
      debugLog('Transport connected successfully');
      
    } catch (err) {
      debugLog('Failed to connect:', err);
      setError(err);
      setStatus('error');
    } finally {
      isConnectingRef.current = false;
    }
  }, [workflowType, enterpriseId, userId, chatId, isConnected, debugLog]);

  // Disconnect from transport
  const disconnect = useCallback(async () => {
    if (transportRef.current) {
      debugLog('Disconnecting transport');
      await transportRef.current.disconnect();
      transportRef.current = null;
    }
    setIsConnected(false);
    setStatus('disconnected');
    setTransportType(null);
  }, [debugLog]);

  // Send message via transport
  const sendMessage = useCallback(async (message) => {
    if (!transportRef.current || !isConnected) {
      throw new Error('Transport not connected');
    }

    debugLog('Sending message:', message);
    
    try {
      // Check if it's an agent action that needs special handling
      if (typeof message === 'object' && (message.type === 'agent_action' || message.type === 'ui_tool_action')) {
        await simpleBridge.sendToBackend(message);
      } else {
        // Regular message
        await transportRef.current.send({ message });
      }
    } catch (err) {
      debugLog('Failed to send message:', err);
      setError(err);
      throw err;
    }
  }, [isConnected, debugLog]);

  // Auto-connect on mount and parameter changes
  useEffect(() => {
    if (workflowType && enterpriseId && userId && chatId) {
      connect();
    }

    // Cleanup on unmount
    return () => {
      if (transportRef.current) {
        transportRef.current.disconnect();
      }
    };
  }, [connect]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (transportRef.current) {
        transportRef.current.disconnect();
      }
      simpleBridge.disconnect();
    };
  }, [disconnect]);

  return {
    // Connection state
    isConnected,
    status,
    transportType,
    
    // Data
    messages,
    error,
    
    // Actions
    connect,
    disconnect,
    sendMessage,
    send: sendMessage, // Alias for convenience
    
    // Utilities
    clearMessages: () => setMessages([]),
    clearError: () => setError(null)
  };
}

/**
 * Lightweight hook for send-only transport operations
 * Use this when you only need to send messages without receiving
 */
export function useSimpleTransport(connectionParams) {
  const { sendMessage, isConnected, status, error } = useTransport(connectionParams);
  
  return {
    send: sendMessage,
    isConnected,
    status,
    error
  };
}

export default useTransport;