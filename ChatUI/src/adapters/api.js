// API adapter interface
import workflowConfig from '../config/workflowConfig';
import config from '../config';

export class ApiAdapter {
  async sendMessage(_message, _enterpriseId, _userId) {
    throw new Error('sendMessage must be implemented');
  }

  async sendMessageToWorkflow(message, enterpriseId, userId, workflowname = null, chatId = null) {
    // Use dynamic default workflow type
    const actualworkflowname = workflowname || workflowConfig.getDefaultWorkflow();
    console.log(`Sending message to workflow: ${actualworkflowname}`);
    throw new Error('sendMessageToWorkflow must be implemented');
  }

  createWebSocketConnection(_enterpriseId, _userId, _callbacks, _workflowname = null, _chatId = null) {
    throw new Error('createWebSocketConnection must be implemented');
  }

  async getMessageHistory(_enterpriseId, _userId) {
    throw new Error('getMessageHistory must be implemented');
  }

  async uploadFile(_file, _enterpriseId, _userId) {
    throw new Error('uploadFile must be implemented');
  }

  async getWorkflowTransport(_workflowname) {
    throw new Error('getWorkflowTransport must be implemented');
  }

  async startChat(_enterpriseId, _workflowname, _userId) {
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

  async sendMessageToWorkflow(message, enterpriseId, userId, workflowname = null, chatId = null) {
    // Use dynamic default workflow type
    const actualworkflowname = workflowname || workflowConfig.getDefaultWorkflow();
    
    if (!chatId) {
      console.error('Chat ID is required for sending message to workflow');
      return { success: false, error: 'Chat ID is required' };
    }
    
    try {
      const response = await fetch(`http://localhost:8000/chat/${enterpriseId}/${chatId}/${userId}/input`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          message, 
          workflow_name: actualworkflowname,
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

  createWebSocketConnection(enterpriseId, userId, callbacks = {}, workflowname = null, chatId = null) {
    const actualworkflowname = workflowname || workflowConfig.getDefaultWorkflow();
    
    if (!chatId) {
      console.error('Chat ID is required for WebSocket connection');
      return null;
    }
    
    const wsBase = this.config.wsUrl || this.config.api?.wsUrl;
    const wsUrl = `${wsBase}/ws/${actualworkflowname}/${enterpriseId}/${chatId}/${userId}`;
    console.log(`🔗 Connecting to WebSocket: ${wsUrl}`);
    const socket = new WebSocket(wsUrl);
    
    // F7/F8: Sequence tracking and resume capability
    let lastSequence = parseInt(localStorage.getItem(`ws_seq_${chatId}`) || '0');
    let resumePending = false;
    
    // Helper to send client.resume
    const sendResume = () => {
      if (socket.readyState === WebSocket.OPEN && !resumePending) {
        resumePending = true;
        console.log(`📡 Sending client.resume with lastClientSeq: ${lastSequence}`);
        socket.send(JSON.stringify({
          type: 'client.resume',
          chat_id: chatId,
          lastClientSeq: lastSequence
        }));
      }
    };

    socket.onopen = () => {
      console.log("WebSocket connection established");
      
      // If we have a previous sequence, request resume first
      if (lastSequence > 0) {
        sendResume();
      }
      
      if (callbacks.onOpen) callbacks.onOpen();
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        // F7/F8: Track sequence numbers for resume capability
        if (data.seq && typeof data.seq === 'number') {
          if (data.seq > lastSequence) {
            lastSequence = data.seq;
            localStorage.setItem(`ws_seq_${chatId}`, lastSequence.toString());
          } else if (data.seq < lastSequence - 1 && !resumePending) {
            // Sequence gap detected - request resume
            console.warn(`⚠️ Sequence gap detected: received ${data.seq}, expected > ${lastSequence}`);
            sendResume();
            return; // Don't process this message until after resume
          }
        }
        
        // Handle resume boundary
        if (data.type === 'chat.resume_boundary') {
          console.log(`✅ Resume completed: ${data.data?.replayed_events || 0} events replayed`);
          resumePending = false;
        }
        
        // Production: Only handle chat.* namespace events
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
          try {
            // Allow caller to pass objects; serialize to JSON
            if (typeof message === 'object') {
              socket.send(JSON.stringify(message));
            } else {
              socket.send(message);
            }
          } catch (e) {
            console.error('Failed to send WS message', e);
            return false;
          }
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
        `http://localhost:8000/api/chat/history/${enterpriseId}/${userId}`
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
      const response = await fetch(`http://localhost:8000/api/chat/upload`, {
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

  async getWorkflowTransport(workflowname) {
    try {
      const response = await fetch(`http://localhost:8000/api/workflows/${workflowname}/transport`);
      if (response.ok) {
        return await response.json();
      }
    } catch (error) {
      console.error('Failed to get workflow transport:', error);
    }
    return null;
  }

  async startChat(enterpriseId, workflowname, userId, fetchOpts = {}) {
    const actualworkflowname = workflowname || workflowConfig.getDefaultWorkflow();
    const clientRequestId = crypto?.randomUUID ? crypto.randomUUID() : (Date.now()+"-"+Math.random().toString(36).slice(2));
    
    try {
      if (this._startingChat) {
        console.log('🛑 startChat skipped (already in progress)');
        return { success: false, error: 'in_progress' };
      }
      this._startingChat = true;
      const response = await fetch(`http://localhost:8000/api/chats/${enterpriseId}/${actualworkflowname}/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, client_request_id: clientRequestId })
        , ...fetchOpts
      });

      if (response.ok) {
        const result = await response.json();
        console.log('✅ Chat started:', result);
        this._startingChat = false;
        return result;
      } else {
        console.error('Failed to start chat:', response.status, response.statusText);
        this._startingChat = false;
        return { success: false, error: `HTTP ${response.status}` };
      }
    } catch (error) {
      console.error('Failed to start chat:', error);
      this._startingChat = false;
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
      const response = await fetch(`http://localhost:8000/api/chat/send`, {
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

  async sendMessageToWorkflow(message, enterpriseId, userId, workflowname = null, chatId = null) {
    // Use dynamic default workflow type
    const actualworkflowname = workflowname || workflowConfig.getDefaultWorkflow();
    
    if (!chatId) {
      console.error('Chat ID is required for sending message to workflow');
      return { success: false, error: 'Chat ID is required' };
    }
    
    try {
      const response = await fetch(`http://localhost:8000/chat/${enterpriseId}/${chatId}/${userId}/input`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          message, 
          workflow_name: actualworkflowname,
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
        `http://localhost:8000/api/chat/messages/${enterpriseId}/${userId}`
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
        `http://localhost:8000/api/chat/upload/${enterpriseId}/${userId}`,
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

  async getWorkflowTransport(workflowname) {
    try {
      const response = await fetch(`http://localhost:8000/api/workflows/${workflowname}/transport`);
      if (response.ok) {
        return await response.json();
      }
    } catch (error) {
      console.error('Failed to get workflow transport:', error);
    }
    return null;
  }

  async startChat(enterpriseId, workflowname, userId, fetchOpts = {}) {
    const actualworkflowname = workflowname || workflowConfig.getDefaultWorkflow();
    const clientRequestId = crypto?.randomUUID ? crypto.randomUUID() : (Date.now()+"-"+Math.random().toString(36).slice(2));
    
    try {
      if (this._startingChat) {
        console.log('🛑 startChat skipped (already in progress)');
        return { success: false, error: 'in_progress' };
      }
      this._startingChat = true;
      const response = await fetch(`http://localhost:8000/api/chats/${enterpriseId}/${actualworkflowname}/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, client_request_id: clientRequestId })
        , ...fetchOpts
      });

      if (response.ok) {
        const result = await response.json();
        console.log('✅ Chat started:', result);
        this._startingChat = false;
        return result;
      } else {
        console.error('Failed to start chat:', response.status, response.statusText);
        this._startingChat = false;
        return { success: false, error: `HTTP ${response.status}` };
      }
    } catch (error) {
      console.error('Failed to start chat:', error);
      this._startingChat = false;
      return { success: false, error: error.message };
    }
  }
}

// Default API instance for enterprise usage
export const enterpriseApi = new RestApiAdapter(config.api);
