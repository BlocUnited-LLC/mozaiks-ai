import React, { useEffect, useState, useRef, useCallback } from "react";
import Header from "../../../shared/components/header";
import Footer from "../../../shared/components/footer";
import ModernChatInterface from "../components/interface/ModernChatInterface";
import ArtifactInterface from "../components/interface/ArtifactInterface";
import { useParams } from "react-router-dom";
import { useChatUI } from "../../../context/ChatUIContext";
import agentManager from '../../../core/agentManager';
import workflowConfig from '../../../config/workflowConfig';
import { dynamicUIHandler } from '../../../core/dynamicUIHandler';

const ChatPage = () => {
  const [messages, setMessages] = useState([]);
  const [ws, setWs] = useState(null);
  // Track pending user messages to filter out echoed messages
  const pendingMessagesRef = useRef([]);
  // Track streaming messages by message ID
  const streamingMessagesRef = useRef(new Map());
  const [loading, setLoading] = useState(true);
  const [agentsInitialized, setAgentsInitialized] = useState(false);
  
  // Add logging to track message state changes
  const setMessagesWithLogging = useCallback((updater) => {
    setMessages(prev => {
      const newMessages = typeof updater === 'function' ? updater(prev) : updater;
      console.log('🔄 MESSAGES STATE UPDATE:');
      console.log('  Previous count:', prev.length);
      console.log('  New count:', newMessages.length);
      console.log('  Previous messages:', prev.map(m => ({ id: m.id, sender: m.sender, content: m.content?.substring(0, 30) + '...' })));
      console.log('  New messages:', newMessages.map(m => ({ id: m.id, sender: m.sender, content: m.content?.substring(0, 30) + '...' })));
      return newMessages;
    });
  }, []);
  
  // Connection status tracking
  const [connectionStatus, setConnectionStatus] = useState('disconnected');
  const [transportType, setTransportType] = useState(null);
  const [currentChatId, setCurrentChatId] = useState(null); // Store the current chat ID
  const [connectionInitialized, setConnectionInitialized] = useState(false); // Prevent duplicate connections
  const [workflowConfigLoaded, setWorkflowConfigLoaded] = useState(false); // Track workflow config loading
  const connectionInProgressRef = useRef(false); // Additional guard against React double-execution
  const { enterpriseId, workflowType: urlWorkflowType } = useParams();
  const { user, api, config } = useChatUI();
  const [isSidePanelOpen, setIsSidePanelOpen] = useState(false);

  // Use workflowType from URL params first, then config, then discovery
  const currentEnterpriseId = enterpriseId || config?.chat?.defaultEnterpriseId || '68542c1109381de738222350';
  const currentUserId = user?.id || config?.chat?.defaultUserId || '56132';
  const defaultWorkflow = urlWorkflowType || config?.chat?.defaultWorkflow || null; // Let workflowConfig.getDefaultWorkflow() handle discovery
  const [currentWorkflowType, setCurrentWorkflowType] = useState(defaultWorkflow?.toLowerCase() || null); // Dynamic workflow detection
  
  // Dynamic UI updates state
  const [dynamicUIUpdates, setDynamicUIUpdates] = useState([]);

  // Subscribe to dynamic UI updates
  useEffect(() => {
    const unsubscribe = dynamicUIHandler.onUIUpdate((updateData) => {
      console.log('🔔 Received dynamic UI update:', updateData);
      
      // Handle different types of UI updates
      switch (updateData.type) {
        case 'open_artifact_panel':
          setIsSidePanelOpen(true);
          break;
          
        case 'show_notification':
          console.log('📢 Notification:', updateData.message);
          break;
          
        case 'component_update':
          console.log('🔄 Component update for:', updateData.componentId);
          break;
          
        case 'status_update':
          // Could update connection status or other UI elements
          console.log('📊 Status:', updateData.status);
          break;
          
        default:
          console.log('🔔 Unknown UI update type:', updateData.type);
      }
      
      // Store update for debugging/history
      setDynamicUIUpdates(prev => [...prev.slice(-10), updateData]);
    });

    return unsubscribe;
  }, []);

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
        setWorkflowConfigLoaded(true);
      } catch (error) {
        console.warn('⚠️ Failed to load workflow configurations:', error);
        setWorkflowConfigLoaded(true); // Still allow connection attempt
      }
    };
    
    initializeWorkflowConfig();
  }, []);

  // Unified incoming message handler for WS and SSE
  const handleIncoming = useCallback((data) => {
    console.log("Received stream message:", data);
    console.log("Message type:", data.type, "Data:", data.data);
    console.log("Current messages count:", messages.length);
    console.log("Current streaming messages:", streamingMessagesRef.current.size);
    
    // Handle dynamic UI event types from backend
    switch (data.type) {
      case 'route_to_artifact':
      case 'ROUTE_TO_ARTIFACT':
        console.log('🎯 Routing to artifact:', data.data);
        dynamicUIHandler.processUIEvent(data);
        return;
        
      case 'ui_tool_action':
      case 'UI_TOOL_ACTION':
        console.log('🔧 UI Tool Action:', data.data);
        dynamicUIHandler.processUIEvent(data);
        return;
        
      case 'status':
      case 'STATUS':
        console.log('📊 Status Update:', data.data);
        dynamicUIHandler.processUIEvent(data);
        return;
        
      case 'error':
      case 'ERROR':
        console.error('❌ Error Event:', data.data);
        dynamicUIHandler.processUIEvent(data);
        return;
        
      case 'route_to_chat':
      case 'ROUTE_TO_CHAT':
        console.log('💬 Routing to chat:', data.data);
        dynamicUIHandler.processUIEvent(data);
        return;
        
      case 'component_update':
      case 'COMPONENT_UPDATE':
        console.log('🔄 Component Update:', data.data);
        dynamicUIHandler.processUIEvent(data);
        return;
    }
    
    // Handle streaming text message types (existing logic)
    if (data.type === 'TEXT_MESSAGE_START' || data.type === 'text_stream_start') {
      // Start of a new message - initialize streaming message
      const messageId = data.data?.messageId || data.data?.message_id || data.data?.stream_id || data.timestamp || Date.now();
      if (messageId) {
        console.log('📝 Starting new message:', messageId);
        const friendlyAgentName = (data.agent_name || data.data?.agent_name) ? 
          (data.agent_name || data.data?.agent_name).replace('Agent', '').replace(/([A-Z])/g, ' $1').trim() || (data.agent_name || data.data?.agent_name) : 
          'Agent';
        streamingMessagesRef.current.set(messageId, {
          id: messageId,
          content: '',
          sender: 'agent',
          agentName: friendlyAgentName,
          timestamp: Date.now(),
          isStreaming: true
        });
      }
      return;
    }
    
    if (data.type === 'TEXT_MESSAGE_CONTENT' || data.type === 'text_stream_chunk') {
      // Streaming content - append to existing message
      const messageId = data.data?.messageId || data.data?.message_id || data.data?.stream_id || data.timestamp;
      const delta = data.data?.delta || data.data?.content || data.data?.chunk || data.content || '';
      
      console.log('🔍 Processing chunk - messageId:', messageId, 'delta:', delta);
      
      if (messageId && delta) {
        let streamingMessage = streamingMessagesRef.current.get(messageId);
        
        // If no existing message found, create a new one (auto-start scenario)
        if (!streamingMessage) {
          console.log('🔄 Auto-creating message for stream_id:', messageId);
          const friendlyAgentName = data.agent_name ? 
            data.agent_name.replace('Agent', '').replace(/([A-Z])/g, ' $1').trim() || data.agent_name : 
            'Agent';
          streamingMessage = {
            id: messageId,
            content: '',
            sender: data.agent_name === 'user' ? 'user' : 'agent',
            agentName: friendlyAgentName,
            timestamp: Date.now(),
            isStreaming: true
          };
          streamingMessagesRef.current.set(messageId, streamingMessage);
          console.log('✅ Created new streaming message:', streamingMessage);
        } else {
          // Update agent name if we have it and it's not set
          if (data.agent_name && (!streamingMessage.agentName || streamingMessage.agentName === 'Agent')) {
            const friendlyAgentName = data.agent_name.replace('Agent', '').replace(/([A-Z])/g, ' $1').trim() || data.agent_name;
            streamingMessage.agentName = friendlyAgentName;
          }
        }
        
        // Update the streaming message content
        streamingMessage.content += delta;
        console.log('📝 Updated message content to:', streamingMessage.content.substring(0, 50) + '...');
        
        // Update the messages array with the current content
        setMessagesWithLogging(prev => {
          const existingIndex = prev.findIndex(msg => msg.id === messageId);
          if (existingIndex >= 0) {
            // Update existing message
            const updated = [...prev];
            updated[existingIndex] = { ...streamingMessage };
            console.log('🔄 Updated existing message at index:', existingIndex);
            console.log('🔍 Updated message data:', updated[existingIndex]);
            return updated;
          } else {
            // Add new streaming message
            console.log('➕ Adding new message to array, current length:', prev.length);
            console.log('🔍 New message data:', streamingMessage);
            const newArray = [...prev, { ...streamingMessage }];
            console.log('📊 New array length:', newArray.length);
            return newArray;
          }
        });
      } else {
        console.warn('⚠️ Received chunk with no messageId or content:', data);
      }
      return;
    }
    
    if (data.type === 'TEXT_MESSAGE_END' || data.type === 'text_stream_end') {
      // End of message - mark as complete
      const messageId = data.data?.messageId || data.data?.message_id || data.data?.stream_id || data.timestamp;
      if (messageId) {
        console.log('✅ Message completed:', messageId);
        const streamingMessage = streamingMessagesRef.current.get(messageId);
        if (streamingMessage) {
          streamingMessage.isStreaming = false;
          setMessagesWithLogging(prev => {
            const updated = [...prev];
            const index = updated.findIndex(msg => msg.id === messageId);
            if (index >= 0) {
              updated[index] = { ...streamingMessage };
              console.log('✅ Finalized message at index:', index);
            }
            return updated;
          });
          streamingMessagesRef.current.delete(messageId);
        }
      }
      return;
    }
    
    // Handle standard message format
    const content = data.content || data.message;
    if (content) {
      const idx = pendingMessagesRef.current.indexOf(content);
      if (idx > -1) { 
        pendingMessagesRef.current.splice(idx, 1); 
        return; 
      }
      
      const newMessage = { 
        id: data.message_id || Date.now().toString(),
        sender: data.sender || 'agent', 
        agentName: data.agent_name || 'Agent',
        content, 
        agentUI: data.agentUI, 
        timestamp: Date.now(),
        isStreaming: false
      };
      setMessagesWithLogging(prev => [...prev, newMessage]);
    }
  }, []);

  // Connect to streaming when API becomes available
  useEffect(() => {
    if (!api) return;
    
    // Wait for workflow configuration to be loaded before connecting
    if (!workflowConfigLoaded) {
      console.log('⏳ Waiting for workflow configuration to load...');
      return;
    }
    
    // Prevent duplicate connections
    if (connectionInitialized || connectionInProgressRef.current) {
      console.log('🔄 Connection already initialized or in progress, skipping...');
      return;
    }
    
    // Mark connection as in progress immediately to prevent duplicates
    connectionInProgressRef.current = true;
    setConnectionInitialized(true);
    
    // Define connection functions inside useEffect to avoid dependency issues
    const connectWebSocket = () => {
      // WebSocket requires an existing chat ID, so we can't use it for initial connections
      if (!currentChatId) {
        console.warn('WebSocket requires existing chat ID, use SSE first');
        return () => {};
      }
      
      setConnectionStatus('connecting');
      setTransportType('websocket');

      const workflowType = urlWorkflowType || workflowConfig.getDefaultWorkflow();
      
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
        },
        workflowType,
        currentChatId // Pass the existing chat ID
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
      // Reset connection flags on error so user can retry
      setConnectionInitialized(false);
      connectionInProgressRef.current = false;
    });
    
    return () => {
      if (cleanup) cleanup();
      // Reset the in-progress flag when component unmounts
      connectionInProgressRef.current = false;
    };
  }, [api, currentEnterpriseId, currentUserId, handleIncoming, workflowConfigLoaded]); // Include workflowConfigLoaded

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
    setMessagesWithLogging(prevMessages => [...prevMessages, userMessage]);
    
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
      const response = await agentManager.handleAction(action);
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
