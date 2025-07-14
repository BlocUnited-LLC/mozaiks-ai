import React, { useState, useRef, useEffect } from 'react';
import { useTransport } from '../../../../hooks/useTransport.js';
import ConnectionStatus from './ConnectionStatus.js';
import { useDynamicComponent } from '../../../../hooks/useDynamicComponents';
import { agentManager } from '../../../../agents/services/agentManager.js';

/**
 * Transport-Agnostic Chat Component
 * Works with WebSocket, SSE, or HTTP transport automatically
 */
function TransportAwareChatComponent({ 
  workflowType, 
  enterpriseId, 
  userId, 
  chatId,
  className = '' 
}) {
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [agentsInitialized, setAgentsInitialized] = useState(false);
  const messagesEndRef = useRef(null);

  // Dynamically load the AgentUIRenderer component
  const { 
    component: AgentUIRenderer, 
    loading: componentLoading, 
    error: componentError 
  } = useDynamicComponent('AgentUIRenderer', 'inline-component');

  // Use the transport-agnostic hook
  const {
    isConnected,
    status,
    transportType,
    messages,
    error,
    sendMessage,
    clearError
  } = useTransport({
    workflowType,
    enterpriseId,
    userId,
    chatId
  });

  // Initialize agents on component mount
  useEffect(() => {
    if (agentsInitialized) return;
    
    // Auto-activate the example agent for demonstration
    agentManager.activateAgent('example-agent');
    setAgentsInitialized(true);
  }, [agentsInitialized]);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  const handleSendMessage = async (e) => {
    e.preventDefault();
    
    if (!inputMessage.trim() || !isConnected || isLoading) {
      return;
    }

    const messageContent = inputMessage.trim();
    setIsLoading(true);
    
    try {
      // Process message through agents first
      try {
        const agentResponses = await agentManager.processMessage(
          { sender: 'user', content: messageContent },
          { enterpriseId, userId }
        );
        
        // Agent responses are handled through the transport system
        // They will appear in the messages array automatically
      } catch (error) {
        console.error('Error processing message with agents:', error);
      }
      
      // Send to backend via transport
      await sendMessage(messageContent);
      setInputMessage('');
    } catch (err) {
      console.error('Failed to send message:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const renderMessage = (message, index) => {
    // Handle different message types from Simple Events system
    switch (message.type) {
      case 'text_message_start':
      case 'text_message_content':
      case 'text_message_end':
        return renderTextMessage(message, index);
      
      case 'tool_call_start':
      case 'tool_call_result':
        return renderToolCall(message, index);
      
      case 'agent_message':
        return renderAgentMessage(message, index);
      
      case 'input_required':
        return renderInputRequired(message, index);
      
      case 'ui_tool':  // 🆕 Handle backend UI tools (workflow-agnostic)
        return renderUITool(message, index);
      
      case 'error':
        return renderErrorMessage(message, index);
      
      default:
        // 🆕 Check if it's a frontend agent UI message
        if (message.agentUI) {
          return renderAgentUIMessage(message, index);
        }
        return renderGenericMessage(message, index);
    }
  };

  const renderTextMessage = (message, index) => {
    const isAgent = message.agent_name || message.data?.role === 'assistant';
    
    return (
      <div key={index} className={`message ${isAgent ? 'agent' : 'user'}`}>
        <div className="message-header">
          <span className="sender">
            {message.agent_name || (isAgent ? 'Assistant' : 'You')}
          </span>
          <span className="timestamp">
            {new Date(message.timestamp || Date.now()).toLocaleTimeString()}
          </span>
        </div>
        <div className="message-content">
          {message.data?.content || message.data?.delta || message.content || message.message}
        </div>
      </div>
    );
  };

  const renderAgentMessage = (message, index) => {
    return (
      <div key={index} className="message agent">
        <div className="message-header">
          <span className="sender">{message.agent_name || 'Agent'}</span>
          <span className="timestamp">
            {new Date(message.timestamp || Date.now()).toLocaleTimeString()}
          </span>
        </div>
        <div className="message-content">
          {message.data?.content || message.content}
        </div>
      </div>
    );
  };

  const renderToolCall = (message, index) => {
    return (
      <div key={index} className="message tool-call">
        <div className="message-header">
          <span className="sender">🔧 Tool: {message.data?.toolName}</span>
          <span className="timestamp">
            {new Date(message.timestamp || Date.now()).toLocaleTimeString()}
          </span>
        </div>
        <div className="message-content tool-content">
          {message.data?.content || JSON.stringify(message.data, null, 2)}
        </div>
      </div>
    );
  };

  const renderInputRequired = (message, index) => {
    return (
      <div key={index} className="message system input-required">
        <div className="message-header">
          <span className="sender">System</span>
          <span className="timestamp">
            {new Date(message.timestamp || Date.now()).toLocaleTimeString()}
          </span>
        </div>
        <div className="message-content">
          <div className="input-prompt">
            💬 {message.data?.prompt || 'Input required'}
          </div>
        </div>
      </div>
    );
  };

  const renderErrorMessage = (message, index) => {
    return (
      <div key={index} className="message error">
        <div className="message-header">
          <span className="sender">⚠️ Error</span>
          <span className="timestamp">
            {new Date(message.timestamp || Date.now()).toLocaleTimeString()}
          </span>
        </div>
        <div className="message-content error-content">
          {message.data?.message || message.message || 'Unknown error'}
        </div>
      </div>
    );
  };

  const renderGenericMessage = (message, index) => {
    return (
      <div key={index} className="message generic">
        <div className="message-header">
          <span className="sender">{message.agent_name || 'Unknown'}</span>
          <span className="type-badge">{message.type}</span>
          <span className="timestamp">
            {new Date(message.timestamp || Date.now()).toLocaleTimeString()}
          </span>
        </div>
        <div className="message-content">
          <pre>{JSON.stringify(message.data || message, null, 2)}</pre>
        </div>
      </div>
    );
  };

  const renderUITool = (message, index) => {
    // Handle backend UI tools (ui_tool events) - workflow-agnostic
    if (!message.data || !message.data.toolId) {
      return renderGenericMessage(message, index);
    }

    return (
      <div key={index} className="message ui-tool">
        <div className="message-header">
          <span className="sender">🔧 {message.agent_name || 'Backend Tool'}</span>
          <span className="tool-badge">{message.data.toolId}</span>
          <span className="timestamp">
            {new Date(message.timestamp || Date.now()).toLocaleTimeString()}
          </span>
        </div>
        <div className="message-content">
          {AgentUIRenderer ? (
            <AgentUIRenderer
              agentUI={{
                type: mapBackendToolToFrontend(message.data.toolId),
                agentId: message.agent_name || 'backend',
                props: message.data.payload || {}
              }}
              onAction={(action) => handleUIToolAction(action, message.data.toolId)}
            />
          ) : componentLoading ? (
            <div className="text-cyan-400 text-sm">Loading UI component...</div>
          ) : (
            <div className="text-red-400 text-sm">UI component not available</div>
          )}
        </div>
      </div>
    );
  };

  const renderAgentUIMessage = (message, index) => {
    // Handle frontend agent UI messages (agentUI property)
    return (
      <div key={index} className="message agent-ui">
        <div className="message-header">
          <span className="sender">🤖 {message.sender || 'Agent'}</span>
          <span className="ui-badge">{message.agentUI.type}</span>
          <span className="timestamp">
            {new Date(message.timestamp || Date.now()).toLocaleTimeString()}
          </span>
        </div>
        <div className="message-content">
          {message.content && (
            <div className="agent-message-text">
              {message.content}
            </div>
          )}
          {AgentUIRenderer ? (
            <AgentUIRenderer
              agentUI={message.agentUI}
              onAction={(action) => handleAgentAction(action, message.agentUI.agentId)}
            />
          ) : componentLoading ? (
            <div className="text-cyan-400 text-sm">Loading UI component...</div>
          ) : (
            <div className="text-red-400 text-sm">UI component not available</div>
          )}
        </div>
      </div>
    );
  };

  // Map backend tool IDs to frontend component types (workflow-agnostic)
  const mapBackendToolToFrontend = (toolId) => {
    // No hardcoded mappings - let workflow manifests handle tool->component mapping
    // This function should ideally query the active workflow's tool manifest
    console.warn(`Tool mapping for '${toolId}' should come from workflow manifest, not hardcoded mappings`);
    
    // Basic fallback mapping for common UI patterns
    const genericMapping = {
      progress: 'progress',
      form: 'form', 
      code: 'code',
      table: 'table',
      choices: 'choices'
    };
    
    return genericMapping[toolId] || 'custom';
  };

  // Handle actions from backend UI tools
  const handleUIToolAction = async (action, toolId) => {
    try {
      // Send action back to backend via transport with bridge
      await sendMessage({
        type: 'ui_tool_action',
        tool_id: toolId,
        action_type: action.type,
        data: action.data
      });
    } catch (error) {
      console.error('Failed to send UI tool action:', error);
    }
  };

  // Handle actions from frontend agents
  const handleAgentAction = async (action, agentId) => {
    try {
      // Send agent action via bridge
      await sendMessage({
        type: 'agent_action',
        agent_id: agentId,
        action_type: action.type,
        data: action.data
      });
    } catch (error) {
      console.error('Failed to send agent action:', error);
    }
  };

  return (
    <div className={`chat-container transport-aware ${className}`}>
      {/* Connection Status */}
      <ConnectionStatus
        isConnected={isConnected}
        status={status}
        transportType={transportType}
        error={error}
        onRetry={clearError}
        workflowType={workflowType}
      />

      {/* Messages Area */}
      <div className="messages-area">
        <div className="messages-list">
          {messages.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">💬</div>
              <h3>Start a conversation</h3>
              <p>Send a message to begin chatting with the {workflowType} workflow</p>
            </div>
          ) : (
            messages.map((message, index) => renderMessage(message, index))
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
              disabled={!isConnected || !inputMessage.trim() || isLoading}
              className="send-button"
            >
              {isLoading ? '⏳' : '📤'}
            </button>
          </div>
        </form>
      </div>

      {/* Debug Info (Development Only) */}
      {process.env.NODE_ENV === 'development' && (
        <div className="debug-info">
          <details>
            <summary>Debug Info</summary>
            <div className="debug-content">
              <div><strong>Workflow:</strong> {workflowType}</div>
              <div><strong>Transport:</strong> {transportType || 'unknown'}</div>
              <div><strong>Status:</strong> {status}</div>
              <div><strong>Messages:</strong> {messages.length}</div>
              <div><strong>Enterprise:</strong> {enterpriseId}</div>
              <div><strong>Chat:</strong> {chatId}</div>
              <div><strong>User:</strong> {userId}</div>
            </div>
          </details>
        </div>
      )}
    </div>
  );
}

export default TransportAwareChatComponent;
