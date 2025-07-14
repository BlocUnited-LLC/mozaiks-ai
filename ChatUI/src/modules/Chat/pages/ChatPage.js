import React, { useEffect, useState, useRef, useCallback } from "react";
import Header from "../../../shared/components/header";
import Footer from "../../../shared/components/footer";
import ModernChatInterface from "../components/interface/ModernChatInterface";
import ArtifactInterface from "../components/interface/ArtifactInterface";
import { useParams } from "react-router-dom";
import { useChatUI } from "../../../context/ChatUIContext";
import agentManager from '../../../core/agentManager';
import workflowConfig from '../../../config/workflowConfig';
import { setActiveWorkflow } from '../../../agents/components/WorkflowComponentLoader';

const ChatPage = () => {
  const [messages, setMessages] = useState([]);
  const [ws, setWs] = useState(null);
  // Track pending user messages to filter out echoed messages
  const pendingMessagesRef = useRef([]);
  // Track streaming messages by message ID
  const streamingMessagesRef = useRef(new Map());
  const [loading, setLoading] = useState(true);
  const [agentsInitialized, setAgentsInitialized] = useState(false);
  // Connection status tracking
  const [connectionStatus, setConnectionStatus] = useState('disconnected');
  const [transportType, setTransportType] = useState(null);
  const [currentChatId, setCurrentChatId] = useState(null); // Store the current chat ID
  const [connectionInitialized, setConnectionInitialized] = useState(false); // Prevent duplicate connections
  const { enterpriseId, workflowType: urlWorkflowType } = useParams();
  const { user, api, config } = useChatUI();
  const [isSidePanelOpen, setIsSidePanelOpen] = useState(false);

  // Use workflowType from URL params first, then config, then discovery
  const currentEnterpriseId = enterpriseId || config?.chat?.defaultEnterpriseId || '68542c1109381de738222350';
  const currentUserId = user?.id || config?.chat?.defaultUserId || '56132';
  const defaultWorkflow = urlWorkflowType || config?.chat?.defaultWorkflow || null; // Let workflowConfig.getDefaultWorkflow() handle discovery
  const [currentWorkflowType, setCurrentWorkflowType] = useState(defaultWorkflow?.toLowerCase() || null); // Dynamic workflow detection

  // Initialize agents on page load
  useEffect(() => {
    if (agentsInitialized) return;
    
    // Agent system is already initialized by the ChatUIProvider
    console.log('📱 ChatPage: Agent system ready');
    
    // No hardcoded welcome message - let the backend/workflow provide initial messages
    setAgentsInitialized(true);
  }, [agentsInitialized]);

  // Initialize workflow configuration on component mount
  useEffect(() => {
    const initializeWorkflowConfig = async () => {
      try {
        await workflowConfig.fetchWorkflowConfigs();
        console.log('✅ Workflow configurations loaded');
      } catch (error) {
        console.warn('⚠️ Failed to load workflow configurations:', error);
      }
    };
    
    initializeWorkflowConfig();
  }, []);

  // Unified incoming message handler for WS and SSE
  const handleIncoming = useCallback((data) => {
    console.log("Received stream message:", data);
    
    // Handle different message types
    if (data.type === 'TEXT_MESSAGE_START') {
      // Start of a new message - initialize streaming message
      const messageId = data.data?.messageId;
      if (messageId) {
        console.log('📝 Starting new message:', messageId);
        streamingMessagesRef.current.set(messageId, {
          id: messageId,
          content: '',
          sender: 'agent',
          agentName: data.agent_name || 'Agent',
          timestamp: Date.now(),
          isStreaming: true
        });
      }
      return;
    }
    
    if (data.type === 'TEXT_MESSAGE_CONTENT') {
      // Streaming content - append to existing message
      const messageId = data.data?.messageId;
      const delta = data.data?.delta;
      
      if (messageId && delta) {
        const streamingMessage = streamingMessagesRef.current.get(messageId);
        if (streamingMessage) {
          // Update the streaming message content
          streamingMessage.content += delta;
          
          // Update the messages array with the current content
          setMessages(prev => {
            const existingIndex = prev.findIndex(msg => msg.id === messageId);
            if (existingIndex >= 0) {
              // Update existing message
              const updated = [...prev];
              updated[existingIndex] = { ...streamingMessage };
              return updated;
            } else {
              // Add new streaming message
              return [...prev, { ...streamingMessage }];
            }
          });
        }
      }
      return;
    }
    
    if (data.type === 'TEXT_MESSAGE_END') {
      // End of message - mark as complete
      const messageId = data.data?.messageId;
      if (messageId) {
        console.log('✅ Message completed:', messageId);
        const streamingMessage = streamingMessagesRef.current.get(messageId);
        if (streamingMessage) {
          streamingMessage.isStreaming = false;
          setMessages(prev => {
            const updated = [...prev];
            const index = updated.findIndex(msg => msg.id === messageId);
            if (index >= 0) {
              updated[index] = { ...streamingMessage };
            }
            return updated;
          });
          streamingMessagesRef.current.delete(messageId);
        }
      }
      return;
    }
    
    // Handle legacy agent_message format
    if (data.type === 'agent_message') {
      const agentName = data.agent_name || data.data?.agent_name || 'Agent';
      const content = data.data?.content || data.content;
      const messageId = data.data?.message_id || data.message_id || Date.now().toString();
      
      if (content) {
        const newMessage = {
          id: messageId,
          sender: 'agent',
          agentName,
          content,
          timestamp: Date.now(),
          isStreaming: false
        };
        setMessages(prev => [...prev, newMessage]);
      }
      return;
    }
    
    // Handle legacy message format or other types
    const content = data.content || data.message;
    if (content) {
      const idx = pendingMessagesRef.current.indexOf(content);
      if (idx > -1) { pendingMessagesRef.current.splice(idx, 1); return; }
      const newMessage = { 
        id: Date.now().toString(),
        sender: data.sender || 'agent', 
        agentName: data.agent_name || 'Agent',
        content, 
        agentUI: data.agentUI, 
        timestamp: Date.now(),
        isStreaming: false
      };
      setMessages(prev => [...prev, newMessage]);
    }
  }, []);

  // Connect to streaming when API becomes available
  useEffect(() => {
    if (!api) return;
    
    // Prevent duplicate connections
    if (connectionInitialized) {
      console.log('🔄 Connection already initialized, skipping...');
      return;
    }
    
    // Mark connection as initialized immediately to prevent duplicates
    setConnectionInitialized(true);
    
    // Define connection functions inside useEffect to avoid dependency issues
    const connectWebSocket = () => {
      setConnectionStatus('connecting');
      setTransportType('websocket');

      const connection = api.createWebSocketConnection(
        currentEnterpriseId,
        currentUserId,
        {
          onOpen: () => {
            console.log("WebSocket connection established");
            setConnectionStatus('connected');
            setLoading(false);
          },
          onMessage: handleIncoming,
          onError: (error) => {
            console.error("WebSocket error:", error);
            setConnectionStatus('error');
            setLoading(false);
          },
          onClose: () => {
            console.log("WebSocket connection closed");
            setConnectionStatus('disconnected');
          }
        }
      );

      setWs(connection);
      return () => {
        if (connection) {
          connection.close();
        }
      };
    };

    const connectSSE = async () => {
      if (!api.createSSEConnection) return () => {};
      
      setConnectionStatus('connecting');
      setTransportType('sse');
      
      try {
        const connection = await api.createSSEConnection(
          currentEnterpriseId, currentUserId,
          { 
            onOpen: () => {
              setConnectionStatus('connected');
              setLoading(false);
            }, 
            onMessage: handleIncoming, 
            onError: e => {
              console.error('SSE error:', e);
              setConnectionStatus('error');
            }, 
            onClose: () => {
              console.log('SSE closed');
              setConnectionStatus('disconnected');
            }
          }
        );
        
        if (connection && connection.chatId) {
          setCurrentChatId(connection.chatId);
          console.log('💬 Chat ID set:', connection.chatId);
        }
        
        return () => {
          if (connection && connection.close) {
            connection.close();
          }
        };
      } catch (error) {
        console.error('Failed to establish SSE connection:', error);
        setConnectionStatus('error');
        return () => {};
      }
    };
    
    // Query the workflow transport type and use appropriate connection
    const connectWithCorrectTransport = async () => {
      try {
        // Use URL workflow type first, then fall back to dynamic discovery
        const workflowType = urlWorkflowType || workflowConfig.getDefaultWorkflow();
        console.log(`🎯 Using workflow type: ${workflowType} (from ${urlWorkflowType ? 'URL' : 'discovery'})`);
        
        const transportInfo = await api.getWorkflowTransport(workflowType);
        
        if (transportInfo && transportInfo.transport === 'sse') {
          console.log('Using SSE transport for', workflowType);
          setTransportType('sse');
          setCurrentWorkflowType(workflowType);
          return await connectSSE();
        } else if (transportInfo && transportInfo.transport === 'websocket') {
          console.log('Using WebSocket transport for', workflowType);
          setTransportType('websocket');
          setCurrentWorkflowType(workflowType);
          return connectWebSocket();
        } else {
          // Fallback to previous behavior
          console.log('Transport info not available, falling back to default behavior');
          if (api.createSSEConnection) {
            setTransportType('sse');
            setCurrentWorkflowType(workflowType);
            return await connectSSE();
          } else if (api.createWebSocketConnection) {
            setTransportType('websocket');
            setCurrentWorkflowType(workflowType);
            return connectWebSocket();
          }
        }
      } catch (error) {
        console.error('Error querying workflow transport:', error);
        // Fallback to previous behavior
        if (api.createSSEConnection) {
          const defaultWorkflow = workflowConfig.getDefaultWorkflow();
          setTransportType('sse');
          setCurrentWorkflowType(defaultWorkflow);
          return await connectSSE();
        } else if (api.createWebSocketConnection) {
          const defaultWorkflow = workflowConfig.getDefaultWorkflow();
          setTransportType('websocket');
          setCurrentWorkflowType(defaultWorkflow);
          return connectWebSocket();
        }
      }
      return () => {}; // Return empty cleanup function if no connection is made
    };
    
    // Execute the async function and handle cleanup
    let cleanup;
    connectWithCorrectTransport().then(cleanupFn => {
      cleanup = cleanupFn;
    }).catch(error => {
      console.error('Failed to connect with transport:', error);
      // Reset connection initialized flag on error so user can retry
      setConnectionInitialized(false);
    });
    
    return () => {
      if (cleanup) cleanup();
    };
  }, [api, currentEnterpriseId, currentUserId, handleIncoming]); // Only essential dependencies

  const sendMessage = async (messageContent) => {
    console.log('🚀 [SEND] Sending message:', messageContent);
    console.log('🚀 [SEND] Current chat ID:', currentChatId);
    console.log('🚀 [SEND] Transport type:', transportType);
    console.log('🚀 [SEND] Enterprise ID:', currentEnterpriseId);
    console.log('🚀 [SEND] User ID:', currentUserId);
    console.log('🚀 [SEND] Workflow type:', currentWorkflowType);
    
    // Create a properly structured user message
    const userMessage = {
      id: Date.now().toString(),
      sender: 'user',  // Use 'user' to align message to the right
      agentName: 'You',
      content: messageContent.content,
      timestamp: Date.now(),
      isStreaming: false
    };
    
    // Optimistic add: add user message to chat and mark pending
    pendingMessagesRef.current.push(messageContent.content);
    setMessages(prevMessages => [...prevMessages, userMessage]);
    
    // Send directly to backend workflow (skip frontend agent processing)
    // Send to appropriate transport
    if (transportType && transportType.toLowerCase() === 'sse') {
      // For SSE, send via HTTP to the workflow input endpoint
      try {
        if (!currentChatId) {
          console.error('❌ [SEND] No chat ID available for sending message');
          return;
        }
        
        console.log('📤 [SEND] Sending via SSE to workflow...');
        const success = await api.sendMessageToWorkflow(
          messageContent.content, 
          currentEnterpriseId, 
          currentUserId, 
          currentWorkflowType,
          currentChatId // Pass the chat ID
        );
        console.log('📤 [SEND] SSE send result:', success);
        if (success) {
          setLoading(true);
        }
      } catch (error) {
        console.error('❌ [SEND] Failed to send message via SSE:', error);
      }
    } else if (transportType && transportType.toLowerCase() === 'websocket' && ws && ws.send) {
      // For WebSocket, send directly through the connection
      console.log('📤 [SEND] Sending via WebSocket...');
      const success = ws.send(messageContent.content);
      console.log('📤 [SEND] WebSocket send result:', success);
      if (success) {
        setLoading(true);
      }
    } else {
      console.warn('⚠️ [SEND] No transport available for sending message');
      console.log('🔍 [SEND] Debug - transportType:', transportType, 'ws:', ws);
    }
  };

  // Handle agent UI actions
  const handleAgentAction = async (action) => {
    console.log('Agent action received in chat page:', action);
    
    try {
      const response = await agentManager.handleAgentAction(action);
      if (response) {
        setMessages(prevMessages => [...prevMessages, response]);
      }
    } catch (error) {
      console.error('Error handling agent action:', error);
    }
  };

  const handleMyAppsClick = () => {
    console.log("Navigate to My Apps");
  };

  const handleCommunityClick = () => {
    console.log('Navigate to community');
  };

  const handleNotificationClick = () => {
    console.log('Show notifications');
  };

  const handleDiscoverClick = () => {
    console.log("Discovery clicked");
  };

  const toggleSidePanel = () => {
    setIsSidePanelOpen(!isSidePanelOpen);
  };

  return (
    <div className="flex flex-col h-screen overflow-hidden relative">
      <img
        src="/existing-flow-bg.png"
        alt=""
        className="z-[-10] fixed sm:-w-auto w-full h-full top-0 object-cover"
      />
      <Header 
        user={user}
        onMyAppsClick={handleMyAppsClick}
        onCommunityClick={handleCommunityClick}
        onNotificationClick={handleNotificationClick}
        onDiscoverClick={handleDiscoverClick}
      />
      
      {/* Main content area that fills remaining screen height - no scrolling */}
      <div className="flex-1 flex flex-col min-h-0 overflow-hidden pt-16">
        <div className={`flex flex-col md:flex-row flex-1 w-full min-h-0 overflow-hidden transition-all duration-300`}>
          {/* Chat Pane - 50% width when artifact is open, 100% when closed */}
          <div className={`flex flex-col px-4 flex-1 min-h-0 overflow-hidden transition-all duration-300 ${isSidePanelOpen ? 'md:w-1/2' : 'w-full'}`}>
            <ModernChatInterface 
              messages={messages} 
              onSendMessage={sendMessage} 
              loading={loading}
              onAgentAction={handleAgentAction}
              onArtifactToggle={toggleSidePanel}
            />
          </div>
          
          {/* Artifact Panel - 50% width, slides in from right */}
          {isSidePanelOpen && (
            <ArtifactInterface onClose={toggleSidePanel} />
          )}
        </div>
      </div>

      {/* Footer - positioned at bottom without affecting flex layout */}
      <div className="flex-shrink-0">
        <Footer />
      </div>
    </div>
  );
};

export default ChatPage;
