// API adapter interface
import workflowConfig from '../config/workflowConfig';
import config from '../config';

export class ApiAdapter {
  async sendMessage(_message, _enterpriseId, _userId) {
    throw new Error('sendMessage must be implemented');
  }

  async sendMessageToWorkflow(message, enterpriseId, userId, workflowType = null, chatId = null) {
    // Use dynamic default workflow type
    const actualWorkflowType = workflowType || workflowConfig.getDefaultWorkflow();
    console.log(`Sending message to workflow: ${actualWorkflowType}`);
    throw new Error('sendMessageToWorkflow must be implemented');
  }

  createWebSocketConnection(_enterpriseId, _userId, _callbacks, _workflowType = null, _chatId = null) {
    throw new Error('createWebSocketConnection must be implemented');
  }

  async getMessageHistory(_enterpriseId, _userId) {
    throw new Error('getMessageHistory must be implemented');
  }

  async uploadFile(_file, _enterpriseId, _userId) {
    throw new Error('uploadFile must be implemented');
  }

  async getWorkflowTransport(_workflowType) {
    throw new Error('getWorkflowTransport must be implemented');
  }

  async startChat(_enterpriseId, _workflowType, _userId) {
    throw new Error('startChat must be implemented');
  }
}

// Default WebSocket API Adapter
export class WebSocketApiAdapter extends ApiAdapter {
  constructor(config) {
    super();
    this.config = config;
  }

  async sendMessage() {
    // For WebSocket, sending is handled by the connection
    // This method can be used for HTTP fallback if needed
    return { success: true };
  }

  async sendMessageToWorkflow(message, enterpriseId, userId, workflowType = null, chatId = null) {
    // Use dynamic default workflow type
    const actualWorkflowType = workflowType || workflowConfig.getDefaultWorkflow();
    
    if (!chatId) {
      console.error('Chat ID is required for sending message to workflow');
      return { success: false, error: 'Chat ID is required' };
    }
    
    try {
      const response = await fetch(`${this.config.baseUrl}/chat/${enterpriseId}/${chatId}/${userId}/input`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          message, 
          workflow_type: actualWorkflowType,
          enterprise_id: enterpriseId,
          user_id: userId 
        })
      });

      if (response.ok) {
        const result = await response.json();
        console.log('✅ Message sent to workflow:', result);
        return result;
      } else {
        console.error('Failed to send message:', response.status, response.statusText);
        return { success: false, error: `HTTP ${response.status}` };
      }
    } catch (error) {
      console.error('Failed to send message to workflow:', error);
      return { success: false, error: error.message };
    }
  }

  createWebSocketConnection(enterpriseId, userId, callbacks = {}, workflowType = null, chatId = null) {
    const actualWorkflowType = workflowType || workflowConfig.getDefaultWorkflow();
    
    if (!chatId) {
      console.error('Chat ID is required for WebSocket connection');
      return null;
    }
    
    const wsBase = this.config.wsUrl || this.config.api?.wsUrl;
    const wsUrl = `${wsBase}/ws/${actualWorkflowType}/${enterpriseId}/${chatId}/${userId}`;
    console.log(`🔗 Connecting to WebSocket: ${wsUrl}`);
    const socket = new WebSocket(wsUrl);

    socket.onopen = () => {
      console.log("WebSocket connection established");
      if (callbacks.onOpen) callbacks.onOpen();
    };

    socket.onmessage = (event) => {
      try {
        // First try to parse as JSON (for complex messages)
        let data = JSON.parse(event.data);
        
        // Handle structured AG2 simple text messages
        if (data.type === 'simple_text') {
          // Pass along with agent context (reduce logging noise)
          if (callbacks.onMessage) callbacks.onMessage({
            type: 'simple_text',
            content: data.content,
            agent_name: data.agent_name,
            timestamp: data.timestamp,
            chat_id: data.chat_id
          });
        } else {
          // Handle other JSON message types
          if (callbacks.onMessage) callbacks.onMessage(data);
        }
      } catch (error) {
        // If JSON parsing fails, treat as simple text (AG2 official approach)        
        // Handle as simple text message following AG2 official pattern
        if (callbacks.onMessage && typeof event.data === 'string' && event.data.trim()) {
          callbacks.onMessage({
            type: 'simple_text',
            content: event.data,
            timestamp: Date.now()
          });
        }
      }
    };

    socket.onerror = (error) => {
      console.error("WebSocket error:", error);
      if (callbacks.onError) callbacks.onError(error);
    };

    socket.onclose = () => {
      console.log("WebSocket connection closed");
      if (callbacks.onClose) callbacks.onClose();
    };

    return {
      socket,
      send: (message) => {
        if (socket.readyState === WebSocket.OPEN) {
          socket.send(message);
          return true;
        }
        return false;
      },
      close: () => socket.close()
    };
  }

  async getMessageHistory(enterpriseId, userId) {
    try {
      const response = await fetch(
        `${this.config.baseUrl}/api/chat/history/${enterpriseId}/${userId}`
      );
      if (response.ok) {
        return await response.json();
      }
    } catch (error) {
      console.error('Failed to fetch message history:', error);
    }
    return [];
  }

  async uploadFile(file, enterpriseId, userId) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('enterpriseId', enterpriseId);
    formData.append('userId', userId);

    try {
      const response = await fetch(`${this.config.baseUrl}/api/chat/upload`, {
        method: 'POST',
        body: formData
      });

      if (response.ok) {
        return await response.json();
      }
    } catch (error) {
      console.error('File upload failed:', error);
    }

    return { success: false, error: 'Upload failed' };
  }

  async getWorkflowTransport(workflowType) {
    try {
      const response = await fetch(`${this.config.baseUrl}/api/workflows/${workflowType}/transport`);
      if (response.ok) {
        return await response.json();
      }
    } catch (error) {
      console.error('Failed to get workflow transport:', error);
    }
    return null;
  }

  async startChat(enterpriseId, workflowType, userId) {
    const actualWorkflowType = workflowType || workflowConfig.getDefaultWorkflow();
    
    try {
      const response = await fetch(`${this.config.baseUrl}/api/chats/${enterpriseId}/${actualWorkflowType}/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId })
      });

      if (response.ok) {
        const result = await response.json();
        console.log('✅ Chat started:', result);
        return result;
      } else {
        console.error('Failed to start chat:', response.status, response.statusText);
        return { success: false, error: `HTTP ${response.status}` };
      }
    } catch (error) {
      console.error('Failed to start chat:', error);
      return { success: false, error: error.message };
    }
  }
}

// REST API Adapter (alternative to WebSocket)
export class RestApiAdapter extends ApiAdapter {
  constructor(config) {
    super();
    this.config = config;
    this.activeChatSessions = new Map(); // Track active chat sessions to prevent duplicates
  }

  async sendMessage(message, enterpriseId, userId) {
    try {
      const response = await fetch(`${this.config.baseUrl}/api/chat/send`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, enterpriseId, userId })
      });

      if (response.ok) {
        return await response.json();
      }
    } catch (error) {
      console.error('Failed to send message:', error);
    }

    return { success: false, error: 'Failed to send message' };
  }

  async sendMessageToWorkflow(message, enterpriseId, userId, workflowType = null, chatId = null) {
    // Use dynamic default workflow type
    const actualWorkflowType = workflowType || workflowConfig.getDefaultWorkflow();
    
    if (!chatId) {
      console.error('Chat ID is required for sending message to workflow');
      return { success: false, error: 'Chat ID is required' };
    }
    
    try {
      const response = await fetch(`${this.config.baseUrl}/chat/${enterpriseId}/${chatId}/${userId}/input`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          message, 
          workflow_type: actualWorkflowType,
          enterprise_id: enterpriseId,
          user_id: userId 
        })
      });

      if (response.ok) {
        const result = await response.json();
        console.log('✅ Message sent to workflow:', result);
        return result;
      } else {
        console.error('Failed to send message:', response.status, response.statusText);
        return { success: false, error: `HTTP ${response.status}` };
      }
    } catch (error) {
      console.error('Failed to send message to workflow:', error);
      return { success: false, error: error.message };
    }
  }

  createWebSocketConnection() {
    // REST API adapter doesn't support WebSocket connections
    console.warn('WebSocket not supported in REST API adapter');
    return null;
  }

  async getMessageHistory(enterpriseId, userId) {
    try {
      const response = await fetch(
        `${this.config.baseUrl}/api/chat/messages/${enterpriseId}/${userId}`
      );
      if (response.ok) {
        return await response.json();
      }
    } catch (error) {
      console.error('Failed to fetch messages:', error);
    }
    return [];
  }

  async uploadFile(file, enterpriseId, userId) {
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch(
        `${this.config.baseUrl}/api/chat/upload/${enterpriseId}/${userId}`,
        {
          method: 'POST',
          body: formData
        }
      );

      if (response.ok) {
        return await response.json();
      }
    } catch (error) {
      console.error('File upload failed:', error);
    }

    return { success: false, error: 'Upload failed' };
  }

  async getWorkflowTransport(workflowType) {
    try {
      const response = await fetch(`${this.config.baseUrl}/api/workflows/${workflowType}/transport`);
      if (response.ok) {
        return await response.json();
      }
    } catch (error) {
      console.error('Failed to get workflow transport:', error);
    }
    return null;
  }

  async startChat(enterpriseId, workflowType, userId) {
    const actualWorkflowType = workflowType || workflowConfig.getDefaultWorkflow();
    
    try {
      const response = await fetch(`${this.config.baseUrl}/api/chats/${enterpriseId}/${actualWorkflowType}/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId })
      });

      if (response.ok) {
        const result = await response.json();
        console.log('✅ Chat started:', result);
        return result;
      } else {
        console.error('Failed to start chat:', response.status, response.statusText);
        return { success: false, error: `HTTP ${response.status}` };
      }
    } catch (error) {
      console.error('Failed to start chat:', error);
      return { success: false, error: error.message };
    }
  }
}

// Default API instance for enterprise usage
export const enterpriseApi = new RestApiAdapter(config.api);
