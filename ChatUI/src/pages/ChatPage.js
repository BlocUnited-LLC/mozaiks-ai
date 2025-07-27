import React, { useEffect, useState, useRef, useCallback } from "react";
import Header from "../components/layout/Header";
import Footer from "../components/layout/Footer";
import ChatInterface from "../components/chat/ChatInterface";
import ArtifactInterface from "../components/chat/ArtifactInterface";
import { useParams } from "react-router-dom";
import { useChatUI } from "../context/ChatUIContext";
// agentManager removed - using workflow system
import workflowConfig from '../config/workflowConfig';
import { dynamicUIHandler } from '../core/dynamicUIHandler';

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

  // Auto-start workflow based on startup_mode
  useEffect(() => {
    const handleAutoStart = async () => {
      if (!workflowConfigLoaded || currentChatId) {
        return; // Wait for config to load or skip if chat already exists
      }

      const workflowType = urlWorkflowType || workflowConfig.getDefaultWorkflow();
      const config = workflowConfig.getWorkflowConfig(workflowType);
      
      // Check startup_mode to determine if WebSocket chat should start
      const startupMode = config?.startup_mode;
      const shouldStartWebSocket = startupMode === 'UserDriven' || startupMode === 'AgentDriven';
      
      if (shouldStartWebSocket) {
        console.log(`🚀 Starting WebSocket chat for ${startupMode} workflow:`, workflowType);
        
        try {
          const result = await api.startChat(currentEnterpriseId, workflowType, currentUserId);
          
          if (result && result.chat_id) {
            console.log('✅ WebSocket chat created:', result.chat_id);
            setCurrentChatId(result.chat_id);
          } else {
            console.error('❌ Failed to start WebSocket chat:', result);
          }
        } catch (error) {
          console.error('❌ WebSocket chat start failed:', error);
        }
      } else if (startupMode === 'BackendOnly') {
        console.log('⚙️ Backend-only workflow - no WebSocket connection needed:', workflowType);
        // For backend-only workflows, we don't need WebSocket but could still initialize other components
      } else {
        console.log('⏳ Unknown startup_mode or waiting for workflow configuration...', startupMode);
      }
    };

    handleAutoStart();
  }, [workflowConfigLoaded, currentChatId, urlWorkflowType, currentEnterpriseId, currentUserId, api]);

  // Unified incoming message handler for WebSocket only
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
        
      case 'ui_tool_event':
      case 'UI_TOOL_EVENT':
        console.log('🎯 UI Tool Event received:', data);
        // Handle UI tool events from the backend (DYNAMIC_UI_COMPLETE_GUIDE.md specification)
        dynamicUIHandler.processUIEvent(data);
        return;
        
      case 'simple_text':
        // Handle simple text messages following AG2's official approach (reduced logging)
        if (data.content && data.content.trim() !== '') {
          // Get agent name from structured data or parse from raw content
          let cleanContent = data.content;
          let agentName = data.agent_name || 'Agent';
          let isUserProxy = false;
          
          // Check if this is a raw AG2 message object that needs parsing
          if (typeof data.content === 'string' && data.content.includes('uuid=UUID(')) {
            // Extract agent name from sender field
            const senderMatch = data.content.match(/sender='([^']+)'/);
            if (senderMatch) {
              const sender = senderMatch[1];
              if (sender === 'user' || sender === 'UserProxy') {
                isUserProxy = true;
                return; // Skip user proxy messages
              }
              agentName = sender;
            }
            
            // Extract clean content
            const contentMatch = data.content.match(/content='([^']+)'|content="([^"]+)"/);
            if (contentMatch) {
              cleanContent = contentMatch[1] || contentMatch[2];
            }
          }
          
          // Skip empty content, initial system messages, or user proxy messages
          if (!cleanContent || cleanContent.trim() === '' || isUserProxy) {
            return;
          }
          
          const textMessage = {
            id: data.timestamp || Date.now(),
            content: cleanContent,
            sender: 'agent',
            agentName: agentName,
            timestamp: data.timestamp || Date.now(),
            isStreaming: false
          };
          setMessages(prev => [...prev, textMessage]);
        }
        return;
        
      case 'chat_message':
        console.log('💬 Chat message received:', data);
        // Handle chat messages (including UUID-formatted AG2 messages)
        const messageContent = data.data?.message || data.message || '';
        
        // Check if this is a UUID-formatted AG2 message that needs parsing
        if (typeof messageContent === 'string' && messageContent.includes('uuid=UUID(') && messageContent.includes('content=')) {
          console.log('🔧 Parsing UUID-formatted AG2 message:', messageContent);
          const contentMatch = messageContent.match(/content='([^']+)'|content="([^"]+)"/);
          if (contentMatch) {
            const extractedContent = contentMatch[1] || contentMatch[2];
            const agentName = data.data?.agent_name || data.agent_name || 'Agent';
            
            // Skip empty or None content
            if (extractedContent && extractedContent !== 'None' && extractedContent.trim() !== '') {
              const chatMessage = {
                id: data.timestamp || Date.now(),
                content: extractedContent,
                sender: 'agent',
                agentName: agentName,
                timestamp: data.timestamp || Date.now(),
                isStreaming: false
              };
              console.log('✅ Successfully parsed UUID message:', chatMessage);
              setMessages(prev => [...prev, chatMessage]);
            } else {
              console.log('⏭️ Skipping empty/None content message');
            }
          }
        } else if (messageContent && messageContent.trim() !== '' && messageContent !== 'None') {
          // Handle regular chat messages
          const chatMessage = {
            id: data.timestamp || Date.now(),
            content: messageContent,
            sender: 'agent',
            agentName: data.data?.agent_name || data.agent_name || 'Agent',
            timestamp: data.timestamp || Date.now(),
            isStreaming: false
          };
          setMessages(prev => [...prev, chatMessage]);
        }
        return;
        
      case 'agent_message':
        console.log('🤖 Agent message received:', data);
        // Handle parsed AG2 messages directly
        const agentMessage = {
          id: data.timestamp || Date.now(),
          content: data.content,
          sender: 'agent',
          agentName: data.agent_name || 'Agent',
          timestamp: data.timestamp || Date.now(),
          isStreaming: false
        };
        setMessages(prev => [...prev, agentMessage]);
        return;
        
      default:
        console.log('🔍 Unhandled message type:', data.type, data);
        break;
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
  }, [messages.length, setMessagesWithLogging]);

  // Connect to streaming when API becomes available and chat ID exists
  useEffect(() => {
    if (!api) return;
    
    // Wait for workflow configuration to be loaded before connecting
    if (!workflowConfigLoaded) {
      console.log('⏳ Waiting for workflow configuration to load...');
      return;
    }
    
    // Require chat ID to connect
    if (!currentChatId) {
      console.log('⏳ Waiting for chat ID to be available...');
      return;
    }
    
    // Prevent duplicate connections
    if (connectionInitialized || connectionInProgressRef.current) {
      console.log('🔄 Connection already initialized or in progress, skipping...');
      return;
    }
    
    console.log('🔌 Establishing WebSocket connection with chat ID:', currentChatId);
    
    // Mark connection as in progress immediately to prevent duplicates
    connectionInProgressRef.current = true;
    setConnectionInitialized(true);
    
    // Define connection functions inside useEffect to avoid dependency issues
    const connectWebSocket = () => {
      // WebSocket connection for chat communication
      if (!currentChatId) {
        console.error('WebSocket requires existing chat ID');
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
      console.log('🔌 WebSocket connection established:', ws ? 'Active' : 'Inactive');
      return () => {
        if (connection) {
          connection.close();
          console.log('🔌 WebSocket connection closed');
        }
      };
    };

    // Query the workflow transport type and use WebSocket connection
    const connectWithCorrectTransport = async () => {
      try {
        // Use URL workflow type first, then fall back to dynamic discovery
        const workflowType = urlWorkflowType || workflowConfig.getDefaultWorkflow();
        console.log(`🎯 Using workflow type: ${workflowType} (from ${urlWorkflowType ? 'URL' : 'discovery'})`);
        
        const transportInfo = await api.getWorkflowTransport(workflowType);
        console.log('📡 Transport info for', workflowType, ':', transportInfo);
        
        // Always use WebSocket transport
        console.log('Using WebSocket transport for', workflowType);
        setTransportType('websocket');
        setCurrentWorkflowType(workflowType);
        return connectWebSocket();
      } catch (error) {
        console.error('Error querying workflow transport:', error);
        // Fallback to WebSocket
        const defaultWorkflow = workflowConfig.getDefaultWorkflow();
        setTransportType('websocket');
        setCurrentWorkflowType(defaultWorkflow);
        return connectWebSocket();
      }
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
  }, [api, currentEnterpriseId, currentUserId, handleIncoming, workflowConfigLoaded, currentChatId, connectionInitialized, urlWorkflowType, ws]);

  // Retry connection function
  const retryConnection = useCallback(() => {
    console.log('🔄 Retrying connection...');
    setConnectionInitialized(false);
    connectionInProgressRef.current = false;
    setConnectionStatus('disconnected');
    
    // Trigger reconnection by setting up the connection again
    setTimeout(() => {
      if (currentChatId && workflowConfigLoaded) {
        setConnectionStatus('connecting');
      }
    }, 1000);
  }, [currentChatId, workflowConfigLoaded]);

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
    
    // Send directly to backend workflow via WebSocket
    try {
      if (!currentChatId) {
        console.error('❌ [SEND] No chat ID available for sending message');
        return;
      }
      
      console.log('📤 [SEND] Sending via WebSocket to workflow...');
      const success = await api.sendMessageToWorkflow(
        messageContent.content, 
        currentEnterpriseId, 
        currentUserId, 
        currentWorkflowType,
        currentChatId // Pass the chat ID
      );
      console.log('📤 [SEND] WebSocket send result:', success);
      if (success) {
        setLoading(true);
      }
    } catch (error) {
      console.error('❌ [SEND] Failed to send message via WebSocket:', error);
    }
  };

  // Handle agent UI actions
  const handleAgentAction = async (action) => {
    console.log('Agent action received in chat page:', action);
    
    try {
      // Handle UI tool responses for the dynamic UI system
      if (action.type === 'ui_tool_response') {
        console.log('🎯 Processing UI tool response:', action);
        
        const payload = {
          event_id: action.eventId || action.toolId, // Use eventId for tracking, fallback to toolId
          response_data: action.response
        };
        
        // Send the UI tool response to the backend
        const response = await fetch('/api/ui-tool/submit', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(payload)
        });
        
        if (response.ok) {
          const result = await response.json();
          console.log('✅ UI tool response submitted successfully:', result);
        } else {
          console.error('❌ Failed to submit UI tool response:', response.statusText);
        }
        
        return;
      }
      
      // Handle other agent action types
      console.log('🔄 Agent action handled through workflow system:', action);
      // Other response types will come through WebSocket from backend
    } catch (error) {
      console.error('❌ Error handling agent action:', error);
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
            {/* Dynamic UI Updates Debug (only show if there are recent updates) */}
            {process.env.NODE_ENV === 'development' && dynamicUIUpdates.length > 0 && (
              <div className="text-xs px-2 py-1 rounded mb-2 bg-blue-900/50 text-blue-300">
                Recent UI Updates: {dynamicUIUpdates.length}
              </div>
            )}
            
            <ChatInterface 
              messages={messages} 
              onSendMessage={sendMessage} 
              loading={loading}
              onAgentAction={handleAgentAction}
              onArtifactToggle={toggleSidePanel}
              connectionStatus={connectionStatus}
              transportType={transportType}
              workflowType={currentWorkflowType}
              onRetry={retryConnection}
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
