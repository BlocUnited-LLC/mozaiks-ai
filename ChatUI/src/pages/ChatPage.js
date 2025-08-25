import React, { useEffect, useState, useRef, useCallback } from "react";
import Header from "../components/layout/Header";
import Footer from "../components/layout/Footer";
import ChatInterface from "../components/chat/ChatInterface";
import ArtifactPanel from "../components/chat/ArtifactPanel";
import { useParams } from "react-router-dom";
import { useChatUI } from "../context/ChatUIContext";
// agentManager removed - using workflow system
import workflowConfig from '../config/workflowConfig';
import { dynamicUIHandler } from '../core/dynamicUIHandler';

// Lightweight debug toggle for logging all agent outputs
const DEBUG_LOG_ALL_AGENT_OUTPUT = true;
const shouldDebugAllAgents = () => {
  try {
    const v = localStorage.getItem('mozaiks.debug_all_agents');
    if (v != null) return v === '1' || v === 'true';
  } catch {}
  return DEBUG_LOG_ALL_AGENT_OUTPUT;
};
const logAgentOutput = (phase, agentName, content, meta = {}) => {
  if (!shouldDebugAllAgents()) return;
  try {
    const preview = typeof content === 'string' ? content.slice(0, 2000) : JSON.stringify(content);
    console.log(`🛰️ [${phase}]`, { agent: agentName || 'Unknown', content: preview, ...meta });
  } catch {
    console.log(`🛰️ [${phase}]`, { agent: agentName || 'Unknown', content });
  }
};

const ChatPage = () => {
  const [messages, setMessages] = useState([]);
  const [ws, setWs] = useState(null);
  // Removed unnecessary streaming refs - AG2 handles streaming natively
  const [loading, setLoading] = useState(true);
  const [agentsInitialized, setAgentsInitialized] = useState(false);
  
  // Add logging to track message state changes
  const setMessagesWithLogging = useCallback((updater) => {
    setMessages(prev => {
      const newMessages = typeof updater === 'function' ? updater(prev) : updater;
      // Optional debug: enable if you need to trace state transitions
      // console.debug('Messages state update', { prev: prev.length, next: newMessages.length });
      return newMessages;
    });
  }, []);
  
  // Connection status tracking
  const [connectionStatus, setConnectionStatus] = useState('disconnected');
  const [transportType, setTransportType] = useState(null);
  const [currentChatId, setCurrentChatId] = useState(null); // Store the current chat ID
  const LOCAL_STORAGE_KEY = 'mozaiks.current_chat_id';
  const LOCAL_STORAGE_WORKFLOW_KEY = 'mozaiks.current_workflow_name';
  const [connectionInitialized, setConnectionInitialized] = useState(false); // Prevent duplicate connections
  const [workflowConfigLoaded, setWorkflowConfigLoaded] = useState(false); // Track workflow config loading
  const connectionInProgressRef = useRef(false); // Additional guard against React double-execution
  const { enterpriseId, workflowName: urlWorkflowName } = useParams();
  const { user, api, config } = useChatUI();
  const [isSidePanelOpen, setIsSidePanelOpen] = useState(false);
  const [forceOverlay, setForceOverlay] = useState(false); // landscape/short-height overlay

  // Use workflowName from URL params first, then config (no hardcoded defaults)
  const currentEnterpriseId = enterpriseId || config?.chat?.defaultEnterpriseId || '68542c1109381de738222350';
  const currentUserId = user?.id || config?.chat?.defaultUserId || '56132';
  // Preserve original case; backend keys can be case sensitive, we resolve case-insensitively in workflowConfig
  const defaultWorkflow = (urlWorkflowName || config?.chat?.defaultWorkflow || workflowConfig.getDefaultWorkflow() || '');
  const [currentWorkflowName, setCurrentWorkflowName] = useState(defaultWorkflow); // Dynamic workflow detection
  const [tokensExhausted, setTokensExhausted] = useState(false); // Track token exhaustion state
  
  // Dynamic UI updates state - disabled eslint warning as this is used for debugging
  // eslint-disable-next-line no-unused-vars
  const [dynamicUIUpdates, setDynamicUIUpdates] = useState([]);

  // Track recently seen messages to avoid duplicates from both chat_message and ag2_event
  const messagesSeenRef = useRef(new Set());
  const contentsSeenRef = useRef(new Set()); // content-based dedupe across event types
  const uiToolEventIdsSeenRef = useRef(new Set()); // dedupe ui_tool_event insertions
  const dedupeLimit = 500; // cap to avoid unbounded growth
  const fingerprintMessage = (content, agentName) => {
    try {
      const normContent = (content || '').toString().trim();
      const normAgent = (agentName || 'Agent').toString().trim();
      // Use a bounded slice to keep the key stable but not too large
      return `${normAgent}|${normContent.slice(0, 1000)}`;
    } catch {
      return `${agentName}|${String(content)}`;
    }
  };
  const normalizeAgent = (name) => {
    try {
      if (!name) return '';
      return String(name)
        .toLowerCase()
        .replace(/agent$/i, '')
        .replace(/\s+/g, '')
        .trim();
    } catch { return String(name || '').toLowerCase(); }
  };
  const addMessageIfNew = useCallback((chatMessage) => {
  // Always log raw agent output even if we later filter it from UI
  logAgentOutput('UI_ADD_ATTEMPT', chatMessage?.agentName, chatMessage?.content, { sender: chatMessage?.sender, filtered: false });
    // Enforce visual_agents filtering from workflow config if present
    try {
      // Always allow user/system or special system notices
  if (chatMessage?.sender === 'user' || chatMessage?.sender === 'system' || chatMessage?.isTokenMessage || chatMessage?.isWarningMessage || chatMessage?.uiToolEvent) {
        // proceed without filtering
        logAgentOutput('BYPASS_FILTERING', chatMessage?.agentName, null, { reason: 'user/system/special', sender: chatMessage?.sender });
      } else {
      // If currentWorkflowName not yet set, try fallback default
      const wfName = currentWorkflowName || workflowConfig.getDefaultWorkflow();
      const wfCfg = workflowConfig?.getWorkflowConfig(wfName);
      const visualAgents = wfCfg?.visual_agents;
      logAgentOutput('FILTERING_DEBUG', chatMessage?.agentName, null, { 
        workflowName: wfName, 
        visualAgents, 
        agentName: chatMessage?.agentName,
        hasConfig: !!wfCfg
      });
      if (Array.isArray(visualAgents) && chatMessage?.agentName) {
        // agentName in UI is formatted; compare case-insensitively against raw list
        const target = normalizeAgent(chatMessage.agentName);
        const allow = visualAgents.some(a => normalizeAgent(a) === target);
        logAgentOutput('VISUAL_AGENTS_CHECK', chatMessage?.agentName, null, { 
          target, 
          visualAgents, 
          normalizedVisualAgents: visualAgents.map(a => normalizeAgent(a)),
          allow 
        });
        if (!allow) {
          logAgentOutput('FILTERED_BY_VISUAL_AGENTS', chatMessage?.agentName, chatMessage?.content, { workflow: currentWorkflowName });
          return; // drop non-visual agent message
        }
      }
      
      // Filter out initial workflow kickoff from UserProxy only when AgentDriven (workflow-agnostic)
      if (messages.length === 0) {
        const wfCfg = workflowConfig?.getWorkflowConfig(currentWorkflowName);
        const startupMode = wfCfg?.startup_mode;
        const cfgInitialToUser = (wfCfg?.initial_message_to_user || '').toString().trim();
        const cfgInitialKickoff = (wfCfg?.initial_message || '').toString().trim();

        const agent = (chatMessage?.agentName || '').toLowerCase();
        const content = (chatMessage?.content || '').toString().trim();
        const isUserProxySender = (
          agent === 'user' || agent === 'userproxy' || agent === 'userproxyagent' ||
          /sender=['"]?(user|UserProxy)['"]?/.test(content)
        );

        // UserDriven: don't suppress the configured initial_message_to_user
        if (startupMode === 'UserDriven') {
          // Pass through; if the backend sends initial_message_to_user, the UI will show it
        } else if (startupMode === 'AgentDriven') {
          // Suppress only the UserProxy kickoff; if an explicit initial_message is configured, match it; otherwise suppress any first UserProxy text
          const matchesCfgKickoff = !!cfgInitialKickoff && (
            content === cfgInitialKickoff || content.startsWith(cfgInitialKickoff.slice(0, 64))
          );
          if (isUserProxySender && (matchesCfgKickoff || !cfgInitialKickoff)) {
            logAgentOutput('FILTERED_INITIAL_SYSTEM_MESSAGE', chatMessage?.agentName, chatMessage?.content, { reason: 'agentDriven_userproxy_kickoff' });
            return;
          }
        }
      }
      }
    } catch (e) {
      logAgentOutput('FILTERING_ERROR', chatMessage?.agentName, null, { error: e.message });
    }

    const key = fingerprintMessage(chatMessage.content, chatMessage.agentName);
    if (!messagesSeenRef.current.has(key)) {
      // Maintain set size cap
      if (messagesSeenRef.current.size > dedupeLimit) {
        messagesSeenRef.current.clear();
        contentsSeenRef.current.clear();
      }
      messagesSeenRef.current.add(key);

      // Content-based dedupe as a second layer (helps when agentName differs)
      const normContent = (chatMessage?.content || '').toString().trim();
      if (normContent) {
        // Use a more resilient content key by slicing and normalizing
        const contentKey = normContent.slice(0, 1000).replace(/\s+/g, ' ');
        if (contentsSeenRef.current.has(contentKey)) {
          logAgentOutput('DUPLICATE_CONTENT', chatMessage?.agentName, chatMessage?.content, { contentKey });
          return; // already showed this textual content recently
        }
        contentsSeenRef.current.add(contentKey);
      }
      
      setMessages(prev => [...prev, chatMessage]);
      logAgentOutput('UI_ADDED', chatMessage?.agentName, chatMessage?.content, { id: chatMessage?.id });
    } else {
        logAgentOutput('DUPLICATE_FINGERPRINT', chatMessage?.agentName, chatMessage?.content, { key });
    }
  }, [currentWorkflowName]);

  // After workflow configs load, if we don't have a current workflow name set, adopt default
  useEffect(() => {
    if (workflowConfigLoaded) {
      if (!currentWorkflowName && workflowConfig.getDefaultWorkflow()) {
        setCurrentWorkflowName(workflowConfig.getDefaultWorkflow());
        console.log('🔁 Synchronized currentWorkflowName to default after configs load:', workflowConfig.getDefaultWorkflow());
      }
    }
  }, [workflowConfigLoaded, currentWorkflowName]);

  // Fallback: if workflow configs never load (backend down), proceed after timeout
  useEffect(() => {
    if (workflowConfigLoaded) return; // already loaded
    const timeout = setTimeout(() => {
      if (!workflowConfigLoaded) {
        console.warn('⏱️ Workflow config fetch fallback timeout reached – proceeding with stored or default workflow.');
        // Mark as loaded so resume/start logic can continue
        setWorkflowConfigLoaded(true);
      }
    }, 4000);
    return () => clearTimeout(timeout);
  }, [workflowConfigLoaded]);

  // Helper: extract clean text from AG2 stringified payloads or objects
  const extractCleanContent = (raw) => {
    try {
      if (raw == null) return '';
      if (typeof raw === 'object') {
        if ('content' in raw) return raw.content ?? '';
        return '';
      }
      const text = String(raw).trim();
      if (!text || text === 'None') return '';
      if (text.includes('content=')) {
        let m = text.match(/content='([^']*)'/s) || text.match(/content="([^"]*)"/s);
        if (m) return m[1];
        m = text.match(/content=([^,)]+)/s);
        if (m) {
          let extracted = m[1].trim();
          if ((extracted.startsWith("'") && extracted.endsWith("'")) || (extracted.startsWith('"') && extracted.endsWith('"'))) {
            extracted = extracted.slice(1, -1);
          }
          return extracted === 'None' ? '' : extracted;
        }
      }
      return text;
    } catch {
      return String(raw ?? '');
    }
  };

  // Subscribe to dynamic UI updates
  useEffect(() => {
    const unsubscribe = dynamicUIHandler.onUIUpdate((updateData) => {
  // console.debug('Dynamic UI update:', updateData);
      
      // Handle different types of UI updates
      switch (updateData.type) {
        case 'open_artifact_panel':
          setIsSidePanelOpen(true);
          break;
          
        case 'show_notification':
          // console.debug('Notification:', updateData.message);
          break;
          
        case 'component_update':
          // console.debug('Component update for:', updateData.componentId);
          break;
          
        case 'status_update':
          // Could update connection status or other UI elements
          // console.debug('Status:', updateData.status);
          break;
          
    case 'ui_tool_event': {
          // Insert a synthetic chat message that carries the UI tool info to render inline
          const evtId = updateData.eventId || updateData.ui_tool_id;
          if (evtId) {
            if (uiToolEventIdsSeenRef.current.has(evtId)) {
              break; // already rendered
            }
            if (uiToolEventIdsSeenRef.current.size > dedupeLimit) {
              uiToolEventIdsSeenRef.current.clear();
            }
            uiToolEventIdsSeenRef.current.add(evtId);
          }
          const toolMsg = {
            id: `${updateData.eventId || Date.now()}-ui-tool`,
            sender: 'agent',
            agentName: updateData?.payload?.agent_name || 'Assistant',
            content: updateData?.payload?.description || 'Please provide the requested information.',
            timestamp: Date.now(),
            isStreaming: false,
            uiToolEvent: updateData
          };
          addMessageIfNew(toolMsg);
          break;
        }

        default:
          // console.debug('Unknown UI update type:', updateData.type);
      }
      
      // Store update for debugging/history
      setDynamicUIUpdates(prev => [...prev.slice(-10), updateData]);
    });

    return unsubscribe;
  }, [addMessageIfNew]);

  // Token handling functions
  const handleTokenExhausted = useCallback((data) => {
    console.log('💰 Handling token exhausted:', data);
    
    // Set token exhausted state to disable input
    setTokensExhausted(true);
    
    // Add system message about token exhaustion
    const tokenMessage = {
      id: Date.now().toString(),
      sender: 'system',
      agentName: 'System',
      content: data.data?.message || 'You have run out of tokens. Please purchase more to continue.',
      timestamp: Date.now(),
      isStreaming: false,
      isTokenMessage: true
    };
    
    setMessagesWithLogging(prev => [...prev, tokenMessage]);
    
    // Show upgrade modal or redirect to billing
    if (data.data?.upgrade_available) {
      console.log('🚀 Showing upgrade prompt...');
      // TODO: Implement upgrade modal
      // For now, show an alert
      setTimeout(() => {
        alert(`🚀 ${tokenMessage.content}\n\nUpgrade your plan to continue using MozaiksAI!`);
      }, 500);
    }
  }, [setMessagesWithLogging]);

  const handleTokenWarning = useCallback((data) => {
    console.log('⚠️ Handling token warning:', data);
    
    // Add system warning message
    const warningMessage = {
      id: Date.now().toString(),
      sender: 'system',
      agentName: 'System',
      content: data.data?.message || 'Your token balance is running low.',
      timestamp: Date.now(),
      isStreaming: false,
      isWarningMessage: true
    };
    
    setMessagesWithLogging(prev => [...prev, warningMessage]);
  }, [setMessagesWithLogging]);

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

  // Resume or auto-start workflow based on startup_mode
  useEffect(() => {
    const attemptResumeOrStart = async () => {
      if (currentChatId) return; // already have a chat
      if (attemptResumeOrStart.inFlight) {
        console.log('🛑 attemptResumeOrStart skipped (in-flight)');
        return;
      }
      attemptResumeOrStart.inFlight = true;

      let workflowName = urlWorkflowName || null;
      if (!workflowName) {
        try { workflowName = localStorage.getItem(LOCAL_STORAGE_WORKFLOW_KEY) || null; } catch {}
      }
      if (!workflowName) workflowName = workflowConfig.getDefaultWorkflow();
      if (!workflowName) workflowName = 'Generator';
      console.log('🧪 attemptResumeOrStart: resolved workflowName =', workflowName, 'workflowConfigLoaded=', workflowConfigLoaded);
      const cfg = workflowConfig.getWorkflowConfig(workflowName) || {};
      const startupMode = cfg?.startup_mode;

      // 1. Try localStorage resume
      let storedId = null;
      try { storedId = localStorage.getItem(LOCAL_STORAGE_KEY); } catch {}
      if (storedId) {
        try {
          console.log('🔄 Attempting resume for stored chat_id:', storedId);
          const resumeController = new AbortController();
          const resumeTimeout = setTimeout(()=> resumeController.abort(), 5000);
          const resp = await fetch(`http://localhost:8000/api/chats/${currentEnterpriseId}/${workflowName}/${storedId}/resume`, { signal: resumeController.signal });
          clearTimeout(resumeTimeout);
          if (resp.ok) {
            const data = await resp.json();
            console.log('🧪 Resume endpoint response:', data);
            if (data.success && data.can_resume) {
              console.log('✅ Resumed existing chat:', storedId);
              setCurrentChatId(storedId);
              try { localStorage.setItem(LOCAL_STORAGE_WORKFLOW_KEY, workflowName); } catch {}
              // Hydrate prior messages (convert to internal shape)
              const hydrated = (data.messages || []).map(m => ({
                id: m.event_id || Date.now().toString(),
                sender: m.role === 'user' ? 'user' : 'agent',
                agentName: m.name || 'Agent',
                content: m.content,
                timestamp: m.timestamp ? new Date(m.timestamp).getTime() : Date.now(),
                isStreaming: false
              }));
              console.log('🧪 Hydrated messages count:', hydrated.length);
              if (hydrated.length) setMessagesWithLogging(prev => [...prev, ...hydrated]);
              return; // done, websocket effect will connect later
            } else {
              console.log('ℹ️ Stored chat not resumable:', data.status, 'starting new.');
            }
          }
        } catch (e) {
          console.warn('Resume attempt failed, starting new chat:', e.message);
        }
      }

      // 2. Start new chat if startup mode requires WebSocket
  const shouldStart = startupMode === 'UserDriven' || startupMode === 'AgentDriven' || !startupMode; // force if unknown
      if (shouldStart) {
        console.log('🚀 Starting new chat for workflow:', workflowName, 'mode:', startupMode);
        try {
          const startController = new AbortController();
          const startTimeout = setTimeout(()=> startController.abort(), 5000);
          const result = await api.startChat(currentEnterpriseId, workflowName, currentUserId, { signal: startController.signal });
          clearTimeout(startTimeout);
          if (result && result.chat_id) {
            console.log('✅ New chat created:', result.chat_id);
            setCurrentChatId(result.chat_id);
            try { localStorage.setItem(LOCAL_STORAGE_KEY, result.chat_id); } catch {}
            try { localStorage.setItem(LOCAL_STORAGE_WORKFLOW_KEY, workflowName); } catch {}
          } else {
            console.error('❌ Failed to start chat:', result);
          }
        } catch (error) {
          console.error('❌ Chat start failed:', error);
        }
      } else if (startupMode === 'BackendOnly') {
        console.log('⚙️ Backend-only workflow - no chat start needed');
      }
      attemptResumeOrStart.inFlight = false;
    };
    attemptResumeOrStart();
    const retryTimer = setTimeout(() => {
      if (!currentChatId) {
        console.log('⛑️ Fallback retry: forcing chat start/resume attempt');
        attemptResumeOrStart.inFlight = false; // allow retry
        attemptResumeOrStart();
      }
    }, 2000);
    return () => clearTimeout(retryTimer);
  }, [workflowConfigLoaded, currentChatId, urlWorkflowName, currentEnterpriseId, currentUserId, api]);

  // Unified incoming message handler for WebSocket only
  const handleIncoming = useCallback((data) => {
  // console.debug('Stream message:', data?.type);
    try {
      const type = data?.type || 'unknown';
      const agentName = data?.agent_name || data?.data?.agent_name || 'Agent';
      const raw = data?.data?.message || data?.message || data?.content || data?.data || data;
      logAgentOutput('INCOMING', agentName, raw, { type });
    } catch {}
    
    // Handle dynamic UI event types from backend
    switch (data.type) {
      case 'route_to_artifact':
      case 'ROUTE_TO_ARTIFACT':
  // console.debug('Routing to artifact');
        dynamicUIHandler.processUIEvent(data);
        return;
        
      case 'ui_tool_action':
      case 'UI_TOOL_ACTION':
  // console.debug('UI Tool Action');
        dynamicUIHandler.processUIEvent(data);
        return;
        
      case 'status':
      case 'STATUS':
  // console.debug('Status Update');
        dynamicUIHandler.processUIEvent(data);
        return;
        
      case 'error':
      case 'ERROR':
        console.error('❌ Error Event:', data.data);
        dynamicUIHandler.processUIEvent(data);
        return;
        
      case 'route_to_chat':
      case 'ROUTE_TO_CHAT':
  // console.debug('Routing to chat');
        dynamicUIHandler.processUIEvent(data);
        return;
        
      case 'component_update':
      case 'COMPONENT_UPDATE':
  // console.debug('Component Update');
        dynamicUIHandler.processUIEvent(data);
        return;
        
      case 'ui_tool_event':
      case 'UI_TOOL_EVENT':
  // console.debug('UI Tool Event received');
        // Handle UI tool events from the backend (DYNAMIC_UI_COMPLETE_GUIDE.md specification)
        dynamicUIHandler.processUIEvent(data);
        return;
        
      case 'ui_tool':
      case 'UI_TOOL':
  // console.debug('UI Tool received');
        // Handle direct UI tool messages (e.g., user_input_request)
        dynamicUIHandler.processUIEvent(data);
        return;
        
      case 'token_exhausted':
      case 'TOKEN_EXHAUSTED':
  // console.debug('Token exhausted event received');
        handleTokenExhausted(data);
        return;
        
      case 'token_warning':
      case 'TOKEN_WARNING':
  // console.debug('Token warning event received');
        handleTokenWarning(data);
        return;
        
      case 'simple_text':
        // Handle simple text messages following AG2's official approach (reduced logging)
        const maybeContent = data.content;
        const agentNameFromData = data.agent_name || 'Agent';
        let agentName = agentNameFromData;
        let isUserProxy = false;
        // Extract agent if embedded in stringified payload
        if (typeof maybeContent === 'string') {
          const senderMatch = maybeContent.match(/sender='([^']+)'|sender="([^"]+)"/);
          if (senderMatch) {
            const sender = senderMatch[1] || senderMatch[2];
            if (sender === 'user' || sender === 'UserProxy') {
              isUserProxy = true;
            } else {
              agentName = sender || agentNameFromData;
            }
          }
        }
        const cleanContent = extractCleanContent(maybeContent);
        // Skip empty/system or user proxy messages
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
          logAgentOutput('PARSED_SIMPLE_TEXT', agentName, cleanContent);
          addMessageIfNew(textMessage);
        return;
        
      case 'chat_message':
  // console.debug('Chat message received');
        // Handle chat messages (including UUID-formatted AG2 messages)
  const messageContent = data.data?.message || data.message || '';
        
        // Check if this is a UUID-formatted AG2 message that needs parsing
    const extracted = extractCleanContent(messageContent);
    if (extracted && extracted.trim() !== '') {
          // Handle regular chat messages
  const chatMessage = {
            id: data.timestamp || Date.now(),
      content: extracted,
            sender: 'agent',
            agentName: data.data?.agent_name || data.agent_name || 'Agent',
            timestamp: data.timestamp || Date.now(),
            isStreaming: false
          };
  logAgentOutput('PARSED_CHAT_MESSAGE', chatMessage.agentName, chatMessage.content);
      addMessageIfNew(chatMessage);
        }
        return;
        
      case 'agent_message':
  // console.debug('Agent message received');
        // Handle parsed AG2 messages directly
  const agentMessage = {
          id: data.timestamp || Date.now(),
          content: data.content,
          sender: 'agent',
          agentName: data.agent_name || 'Agent',
          timestamp: data.timestamp || Date.now(),
          isStreaming: false
        };
  logAgentOutput('AGENT_MESSAGE', agentMessage.agentName, agentMessage.content);
  addMessageIfNew(agentMessage);
        return;
      
      case 'ag2_event': {
        // Fallback: render AG2 events directly when they contain TextEvent
        const payload = data.data || {};
        const eventType = payload.event_type || payload.type;
        if (eventType === 'TextEvent') {
          let raw = payload.content;
          let extractedContent = '';
          let agentName = data.data?.agent_name || data.agent_name || 'Agent';
          extractedContent = extractCleanContent(raw);
          // Extract agent if available in stringified payload
          if (typeof raw === 'string') {
            const senderMatch = raw.match(/sender='([^']+)'|sender="([^"]+)"/);
            if (senderMatch) agentName = senderMatch[1] || senderMatch[2] || agentName;
          } else if (raw && typeof raw === 'object' && raw.sender) {
            agentName = raw.sender || agentName;
          }
          // Early duplicate suppression using same normalization as addMessageIfNew
          try {
            const normContent = (extractedContent || '').toString().trim();
            if (normContent) {
              const contentKey = normContent.slice(0, 1000).replace(/\s+/g, ' ');
              if (contentsSeenRef.current.has(contentKey)) {
                logAgentOutput('DROPPED_AG2_DUPLICATE', agentName, extractedContent, { contentKey });
                return; // Skip adding duplicate from ag2_event when chat_message already handled it
              }
            }
          } catch {}
          if (extractedContent && extractedContent !== 'None' && extractedContent.trim() !== '') {
            const chatMessage = {
              id: data.timestamp || Date.now(),
              content: extractedContent,
              sender: 'agent',
              agentName: agentName || 'Agent',
              timestamp: data.timestamp || Date.now(),
              isStreaming: false
            };
            logAgentOutput('PARSED_AG2_TEXTEVENT', chatMessage.agentName, chatMessage.content);
            addMessageIfNew(chatMessage);
          }
        } else {
          // console.debug('Non-TextEvent ag2_event received, ignoring for chat render:', eventType);
        }
        return;
      }

      case 'user_input_request':
        // Route user input requests to the dynamic UI handler
  // console.debug('User input request received');
        dynamicUIHandler.processUIEvent(data);
        return;
        
      default:
  // console.debug('Unhandled message type:', data.type);
        break;
    }
    
    // Handle standard message format (fallback for other message types)
    const content = data.content || data.message;
    if (content) {
      const newMessage = { 
        id: data.message_id || Date.now().toString(),
        sender: data.sender || 'agent', 
        agentName: data.agent_name || 'Agent',
        content, 
        agentUI: data.agentUI, 
        timestamp: Date.now(),
        isStreaming: false
      };
      // Use unified path so visual_agents filtering and dedupe always apply
      addMessageIfNew(newMessage);
    }
  }, [messages.length, setMessagesWithLogging, addMessageIfNew, handleTokenExhausted, handleTokenWarning]);

  // Connect to streaming when API becomes available and chat ID exists
  useEffect(() => {
    if (!api) return;
    
    // Wait for workflow configuration to be loaded before connecting
    if (!workflowConfigLoaded) {
  // console.debug('Waiting for workflow configuration to load...');
      return;
    }
    
    // Require chat ID to connect
    if (!currentChatId) {
  // console.debug('Waiting for chat ID to be available...');
      return;
    }
    
    // Prevent duplicate connections
    if (connectionInitialized || connectionInProgressRef.current) {
  // console.debug('Connection already initialized or in progress, skipping...');
      return;
    }
    
  // console.debug('Establishing WebSocket connection');
    
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

      const workflowName = urlWorkflowName || workflowConfig.getDefaultWorkflow();
      if (!workflowName) {
        console.warn('⚠️ No workflow available to connect');
        return () => {};
      }
      
  const connection = api.createWebSocketConnection(
        currentEnterpriseId,
        currentUserId,
        {
          onOpen: () => {
            // console.debug('WebSocket connection established');
            setConnectionStatus('connected');
            setLoading(false);
    try { localStorage.setItem(LOCAL_STORAGE_KEY, currentChatId); } catch {}
          },
          onMessage: handleIncoming,
          onError: (error) => {
            console.error("WebSocket error:", error);
            setConnectionStatus('error');
            setLoading(false);
          },
          onClose: () => {
            // console.debug('WebSocket connection closed');
            setConnectionStatus('disconnected');
          }
        },
        workflowName,
        currentChatId // Pass the existing chat ID
      );

      setWs(connection);
  // console.debug('WebSocket connection established:', !!ws);
      return () => {
        if (connection) {
          connection.close();
          // console.debug('WebSocket connection closed');
        }
      };
    };

    // Query the workflow transport type and use WebSocket connection
    const connectWithCorrectTransport = async () => {
      try {
        // Use URL workflow name first, then fall back to dynamic discovery or default
        const workflowName = urlWorkflowName || workflowConfig.getDefaultWorkflow();
        if (!workflowName) {
          throw new Error('No workflow available');
        }
  // console.debug('Using workflow name:', workflowName);
        
        // eslint-disable-next-line no-unused-vars
        const transportInfo = await api.getWorkflowTransport(workflowName);
  // console.debug('Transport info for', workflowName);
        
        // Always use WebSocket transport
  // console.debug('Using WebSocket transport for', workflowName);
        setTransportType('websocket');
        setCurrentWorkflowName(workflowName);
        return connectWebSocket();
      } catch (error) {
        console.error('Error querying workflow transport:', error);
        // Fallback to WebSocket
        const fallbackWf = workflowConfig.getDefaultWorkflow();
        if (!fallbackWf) {
          console.warn('⚠️ No default workflow available for fallback');
          return () => {};
        }
        setTransportType('websocket');
        setCurrentWorkflowName(fallbackWf);
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
  }, [api, currentEnterpriseId, currentUserId, handleIncoming, workflowConfigLoaded, currentChatId, connectionInitialized, urlWorkflowName, ws]);

  // Retry connection function
  const retryConnection = useCallback(() => {
  // console.debug('Retrying connection...');
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
    console.log('🚀 [SEND] Workflow name:', currentWorkflowName);
    
    // Create a properly structured user message
    const userMessage = {
      id: Date.now().toString(),
      sender: 'user',  // Use 'user' to align message to the right
      agentName: 'You',
      content: messageContent.content,
      timestamp: Date.now(),
      isStreaming: false
    };
    
    // Optimistic add: add user message to chat immediately
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
        currentWorkflowName,
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
          event_id: action.eventId || action.ui_tool_id, // Use eventId for tracking, fallback to ui_tool_id
          response_data: action.response
        };
        
        // Send the UI tool response to the backend
        const response = await fetch('http://localhost:8000/api/ui-tool/submit', {
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
    // console.debug('Agent action handled through workflow system');
      // Other response types will come through WebSocket from backend
    } catch (error) {
      console.error('❌ Error handling agent action:', error);
    }
  };

  const handleMyAppsClick = () => {
  // console.debug('Navigate to My Apps');
  };

  const handleCommunityClick = () => {
  // console.debug('Navigate to community');
  };

  const handleNotificationClick = () => {
  // console.debug('Show notifications');
  };

  const handleDiscoverClick = () => {
  // console.debug('Discovery clicked');
  };

  const toggleSidePanel = () => {
    setIsSidePanelOpen((open) => !open);
  };

  // Decide when to force overlay (mobile landscape or short height)
  useEffect(() => {
    const compute = () => {
      try {
        const w = window.innerWidth;
        const h = window.innerHeight;
        const isSmallWidth = w < 768; // md breakpoint
        const isShort = h < 500; // landscape phones/tablets
        setForceOverlay(isSmallWidth || isShort);
      } catch {}
    };
    compute();
    window.addEventListener('resize', compute);
    window.addEventListener('orientationchange', compute);
    return () => {
      window.removeEventListener('resize', compute);
      window.removeEventListener('orientationchange', compute);
    };
  }, []);

  // Lock body scroll when overlay is open
  useEffect(() => {
    if (isSidePanelOpen && forceOverlay) {
      const { overflow } = document.body.style;
      document.body.style.overflow = 'hidden';
      return () => { document.body.style.overflow = overflow; };
    }
  }, [isSidePanelOpen, forceOverlay]);

  return (
    <div className="flex flex-col h-screen overflow-hidden relative">
      <img
        src="/existing-flow-bg.png"
        alt=""
        className="z-[-10] fixed sm:-w-auto w-full h-full top-0 object-cover"
      />
      <Header 
        user={user}
        workflowName={currentWorkflowName}
        onMyAppsClick={handleMyAppsClick}
        onCommunityClick={handleCommunityClick}
        onNotificationClick={handleNotificationClick}
        onDiscoverClick={handleDiscoverClick}
      />
      
      {/* Main content area that fills remaining screen height - no scrolling */}
      <div className="flex-1 flex flex-col min-h-0 overflow-hidden pt-16 sm:pt-20 md:pt-16">{/* Extra padding on mobile for cleaner spacing */}
  <div className={`flex flex-col md:flex-row flex-1 w-full min-h-0 overflow-hidden transition-all duration-300`}>
          {/* Chat Pane - 50% width when artifact is open, 100% when closed */}
          <div className={`flex flex-col px-4 flex-1 min-h-0 overflow-hidden transition-all duration-300 ${isSidePanelOpen ? 'md:w-1/2' : 'w-full'}`}>
            
            <ChatInterface 
              messages={messages} 
              onSendMessage={sendMessage} 
              loading={loading}
              onAgentAction={handleAgentAction}
              onArtifactToggle={toggleSidePanel}
              connectionStatus={connectionStatus}
              transportType={transportType}
              workflowName={currentWorkflowName}
              startupMode={workflowConfig?.getWorkflowConfig(currentWorkflowName)?.startup_mode}
              initialMessageToUser={workflowConfig?.getWorkflowConfig(currentWorkflowName)?.initial_message_to_user}
              onRetry={retryConnection}
              tokensExhausted={tokensExhausted}
            />
          </div>
          
          {/* Artifact Panel - 50% width, slides in from right (desktop only when not forcing overlay) */}
          {isSidePanelOpen && !forceOverlay && (
            <div className="hidden md:flex md:w-1/2 min-h-0 h-full px-4">
              <ArtifactPanel onClose={toggleSidePanel} />
            </div>
          )}
        </div>
      </div>

      {/* Mobile full-screen Artifact modal (md:hidden handled inside component) */}
      {isSidePanelOpen && forceOverlay && (
        <ArtifactPanel onClose={toggleSidePanel} isMobile={true} />
      )}

      {/* Footer - positioned at bottom without affecting flex layout */}
      <div className="flex-shrink-0">
        <Footer />
      </div>

    </div>
  );
};

export default ChatPage;
