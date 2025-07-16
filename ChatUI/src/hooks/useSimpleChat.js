// ==============================================================================
// FILE: ChatUI/src/hooks/useSimpleChat.js
// DESCRIPTION: Simple React hook for chat - no over-engineering
// ==============================================================================

import { useState, useEffect, useCallback } from 'react';
import { simpleTransport } from '../core/simpleTransport.js';

/**
 * Simple chat hook - connects to backend and manages messages
 * Replaces the complex useTransport hook with something much simpler
 */
export function useSimpleChat(chatId, userId = 'user', workflowType = 'generator') {
  const [messages, setMessages] = useState([]);
  const [isConnected, setIsConnected] = useState(false);
  const [connectionType, setConnectionType] = useState(null);
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(false);

  // Connect to backend
  useEffect(() => {
    if (!chatId) return;

    let mounted = true;

    const connect = async () => {
      try {
        setError(null);
        await simpleTransport.connect(chatId, userId, workflowType);
      } catch (err) {
        if (mounted) {
          setError(err);
        }
      }
    };

    // Set up message handler
    const handleMessage = (message) => {
      if (!mounted) return;

      console.log('Received message:', message);
      
      // Simple message processing - just add to messages array
      setMessages(prev => [...prev, {
        id: Date.now() + Math.random(),
        timestamp: message.timestamp || new Date().toISOString(),
        type: message.type || 'message',
        content: message.content || message.message || '',
        agentName: message.agent_name || (message.type === 'user_message' ? 'You' : 'Assistant'),
        data: message.data || message
      }]);
    };

    // Set up status handler
    const handleStatus = (status, connType) => {
      if (!mounted) return;
      setIsConnected(status === 'connected');
      setConnectionType(connType);
    };

    // Set up error handler
    const handleError = (err) => {
      if (!mounted) return;
      setError(err);
      setIsConnected(false);
    };

    // Register handlers
    simpleTransport.onMessage(handleMessage);
    simpleTransport.onStatusChange(handleStatus);
    simpleTransport.onError(handleError);

    // Connect
    connect();

    // Cleanup
    return () => {
      mounted = false;
      simpleTransport.disconnect();
    };
  }, [chatId, userId, workflowType]);

  // Send message function
  const sendMessage = useCallback(async (message) => {
    if (!message.trim() || !isConnected) {
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      // Add user message to UI immediately
      const userMessage = {
        id: Date.now(),
        timestamp: new Date().toISOString(),
        type: 'user_message',
        content: message,
        agentName: 'You'
      };
      setMessages(prev => [...prev, userMessage]);

      // Send to backend
      await simpleTransport.sendMessage(message);
    } catch (err) {
      setError(err);
      console.error('Failed to send message:', err);
    } finally {
      setIsLoading(false);
    }
  }, [isConnected]);

  // Clear messages
  const clearMessages = useCallback(() => {
    setMessages([]);
  }, []);

  // Clear error
  const clearError = useCallback(() => {
    setError(null);
  }, []);

  return {
    messages,
    isConnected,
    connectionType,
    error,
    isLoading,
    sendMessage,
    clearMessages,
    clearError
  };
}
