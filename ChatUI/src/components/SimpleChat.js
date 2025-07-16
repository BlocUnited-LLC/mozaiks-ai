// ==============================================================================
// FILE: ChatUI/src/components/SimpleChat.js
// DESCRIPTION: Simple chat component - no over-engineering
// ==============================================================================

import React, { useState, useRef, useEffect } from 'react';
import { useSimpleChat } from '../hooks/useSimpleChat.js';

/**
 * Simple Chat Component
 * Replaces the complex TransportAwareChatComponent with something much simpler
 */
function SimpleChat({ 
  chatId, 
  userId = 'user', 
  workflowType = 'generator',
  className = '' 
}) {
  const [inputMessage, setInputMessage] = useState('');
  const messagesEndRef = useRef(null);

  // Use the simple chat hook
  const {
    messages,
    isConnected,
    connectionType,
    error,
    isLoading,
    sendMessage,
    clearError
  } = useSimpleChat(chatId, userId, workflowType);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  // Handle form submission
  const handleSendMessage = async (e) => {
    e.preventDefault();
    
    if (!inputMessage.trim() || !isConnected || isLoading) {
      return;
    }

    const messageContent = inputMessage.trim();
    setInputMessage('');
    
    try {
      await sendMessage(messageContent);
    } catch (err) {
      console.error('Failed to send message:', err);
    }
  };

  // Render a single message
  const renderMessage = (message) => {
    const isUser = message.agentName === 'You' || message.type === 'user_message';
    const isAgent = !isUser;

    return (
      <div key={message.id} className={`message ${isUser ? 'user' : 'agent'}`}>
        <div className="message-header">
          <span className="sender">{message.agentName}</span>
          <span className="timestamp">
            {new Date(message.timestamp).toLocaleTimeString()}
          </span>
        </div>
        <div className="message-content">
          {message.content}
        </div>
      </div>
    );
  };

  return (
    <div className={`simple-chat ${className}`}>
      {/* Connection Status */}
      <div className="connection-status">
        <div className="status-bar">
          <div className="status-main">
            <span className="status-icon">
              {isConnected ? '🟢' : '🔴'}
            </span>
            <span>
              {isConnected ? `Connected via ${connectionType}` : 'Disconnected'}
            </span>
          </div>
          {error && (
            <button onClick={clearError} className="clear-error-btn">
              Clear Error
            </button>
          )}
        </div>
        
        {/* Error Display */}
        {error && (
          <div className="error-display">
            <span className="error-icon">⚠️</span>
            <span className="error-message">{error.message}</span>
          </div>
        )}
      </div>

      {/* Messages Area */}
      <div className="messages-area">
        <div className="messages-list">
          {messages.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">💬</div>
              <h3>Start a conversation</h3>
              <p>Send a message to begin chatting with the AI assistant.</p>
            </div>
          ) : (
            messages.map(renderMessage)
          )}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Input Area */}
      <div className="input-area">
        <form onSubmit={handleSendMessage} className="input-form">
          <div className="input-group">
            <input
              type="text"
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              placeholder={isConnected ? "Type your message..." : "Connecting..."}
              disabled={!isConnected || isLoading}
              className="message-input"
            />
            <button
              type="submit"
              disabled={!isConnected || isLoading || !inputMessage.trim()}
              className="send-button"
            >
              {isLoading ? '⏳' : '📤'}
            </button>
          </div>
        </form>
      </div>

      {/* Debug Info (optional) */}
      {process.env.NODE_ENV === 'development' && (
        <div className="debug-info">
          <details>
            <summary>Debug Info</summary>
            <div className="debug-content">
              <div>Chat ID: {chatId}</div>
              <div>User ID: {userId}</div>
              <div>Workflow: {workflowType}</div>
              <div>Connected: {isConnected ? 'Yes' : 'No'}</div>
              <div>Transport: {connectionType || 'None'}</div>
              <div>Messages: {messages.length}</div>
            </div>
          </details>
        </div>
      )}
    </div>
  );
}

export default SimpleChat;
