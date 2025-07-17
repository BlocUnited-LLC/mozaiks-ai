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

  async createSSEConnection(_enterpriseId, _userId, _callbacks) {
    throw new Error('createSSEConnection must be implemented');
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
    
    const wsUrl = `${this.config.api.wsUrl}/ws/${actualWorkflowType}/${enterpriseId}/${chatId}/${userId}`;
    console.log(`🔗 Connecting to WebSocket: ${wsUrl}`);
    const socket = new WebSocket(wsUrl);

    socket.onopen = () => {
      console.log("WebSocket connection established");
      if (callbacks.onOpen) callbacks.onOpen();
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (callbacks.onMessage) callbacks.onMessage(data);
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error);
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

  async createSSEConnection(enterpriseId, userId, callbacks = {}) {
    try {
      const workflowType = workflowConfig.getDefaultWorkflow();
      
      // First, create a chat session
      const chatResponse = await fetch(`${this.config.baseUrl}/api/chats/${enterpriseId}/${workflowType}/start`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ user_id: userId })
      });
      
      if (!chatResponse.ok) {
        throw new Error(`Failed to create chat session: ${chatResponse.status}`);
      }
      
      const { chat_id } = await chatResponse.json();
      console.log(`🆔 Created chat session: ${chat_id}`);
      
      const sseUrl = `${this.config.baseUrl}/sse/${workflowType}/${enterpriseId}/${chat_id}/${userId}`;
      console.log(`🔗 Connecting to SSE: ${sseUrl}`);
      
      const eventSource = new EventSource(sseUrl);
      
      eventSource.onopen = () => {
        console.log("✅ SSE connection established");
        if (callbacks.onOpen) callbacks.onOpen();
      };
      
      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          console.log("📨 SSE message received:", data);
          if (callbacks.onMessage) callbacks.onMessage(data);
        } catch (error) {
          console.error('Failed to parse SSE message:', error);
        }
      };
      
      eventSource.onerror = (error) => {
        console.error("❌ SSE error:", error);
        if (callbacks.onError) callbacks.onError(error);
      };
      
      return {
        eventSource,
        chatId: chat_id,
        close: () => eventSource.close()
      };
    } catch (error) {
      console.error("❌ Failed to create SSE connection:", error);
      if (callbacks.onError) callbacks.onError(error);
      throw error;
    }
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

  async createSSEConnection(enterpriseId, userId, callbacks = {}) {
    try {
      const workflowType = workflowConfig.getDefaultWorkflow();
      
      // Create a unique key for this chat session
      const sessionKey = `${enterpriseId}:${userId}:${workflowType}`;
      
      // Check if we already have an active session for this combination
      if (this.activeChatSessions.has(sessionKey)) {
        const existingSession = this.activeChatSessions.get(sessionKey);
        // Return existing session if it's still valid and not closed
        if (existingSession && existingSession.eventSource && existingSession.eventSource.readyState !== EventSource.CLOSED) {
          console.log(`♻️ Reusing existing chat session for ${sessionKey}`);
          return existingSession;
        } else {
          // Clean up dead session
          console.log(`🗑️ Cleaning up dead session for ${sessionKey}`);
          this.activeChatSessions.delete(sessionKey);
        }
      }
      
      // First, create a chat session
      const chatResponse = await fetch(`${this.config.baseUrl}/api/chats/${enterpriseId}/${workflowType}/start`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ user_id: userId })
      });
      
      if (!chatResponse.ok) {
        throw new Error(`Failed to create chat session: ${chatResponse.status}`);
      }
      
      const { chat_id } = await chatResponse.json();
      console.log(`🆔 Created chat session: ${chat_id}`);
      
      const sseUrl = `${this.config.baseUrl}/sse/${workflowType}/${enterpriseId}/${chat_id}/${userId}`;
      console.log(`🔗 Connecting to SSE: ${sseUrl}`);
      
      const eventSource = new EventSource(sseUrl);
      
      eventSource.onopen = () => {
        console.log("✅ SSE connection established");
        if (callbacks.onOpen) callbacks.onOpen();
      };
      
      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          console.log("📨 SSE message received:", data);
          if (callbacks.onMessage) callbacks.onMessage(data);
        } catch (error) {
          console.error('Failed to parse SSE message:', error);
        }
      };
      
      eventSource.onerror = (error) => {
        console.error("❌ SSE error:", error);
        // Clean up session on error
        this.activeChatSessions.delete(sessionKey);
        if (callbacks.onError) callbacks.onError(error);
        eventSource.close(); // Ensure the connection is closed on error
      };
      
      const sessionObject = {
        eventSource,
        chatId: chat_id,
        close: () => {
          eventSource.close();
          this.activeChatSessions.delete(sessionKey);
          console.log(`🚪 Closed and cleaned up session for ${sessionKey}`);
        }
      };
      
      // Store the active session
      this.activeChatSessions.set(sessionKey, sessionObject);
      console.log(`📝 Stored chat session: ${sessionKey} -> ${chat_id}`);
      
      return sessionObject;
    } catch (error) {
      console.error("❌ Failed to create SSE connection:", error);
      if (callbacks.onError) callbacks.onError(error);
      throw error;
    }
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
}

// Default API instance for enterprise usage
export const enterpriseApi = new RestApiAdapter(config.api);
