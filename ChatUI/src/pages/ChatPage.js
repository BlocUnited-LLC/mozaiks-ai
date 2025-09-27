import { useEffect, useState, useRef, useCallback } from "react";
import Header from "../components/layout/Header";
import Footer from "../components/layout/Footer";
import ChatInterface from "../components/chat/ChatInterface";
import ArtifactPanel from "../components/chat/ArtifactPanel";
import { useParams } from "react-router-dom";
import { useChatUI } from "../context/ChatUIContext";
import workflowConfig from '../config/workflowConfig';
import { getLoadedWorkflows, getWorkflow } from '../workflows/index';
import { dynamicUIHandler } from '../core/dynamicUIHandler';
import LoadingSpinner from '../utils/AgentChatLoadingSpinner';

// Debug utilities
const DEBUG_LOG_ALL_AGENT_OUTPUT = true;
const shouldDebugAllAgents = () => { try { const v = localStorage.getItem('mozaiks.debug_all_agents'); if (v!=null) return v==='1'||v==='true'; } catch{} return DEBUG_LOG_ALL_AGENT_OUTPUT; };
const logAgentOutput = (phase, agentName, content, meta={}) => { if(!shouldDebugAllAgents()) return; try { const prev = typeof content==='string'?content.slice(0,400):JSON.stringify(content); console.log(`🛰️ [${phase}]`, {agent:agentName||'Unknown', content:prev, ...meta}); } catch { console.log(`🛰️ [${phase}]`, {agent:agentName||'Unknown', content}); } };
// Generic localStorage gated debug flag helper (used for pipeline + render tracing)
const debugFlag = (k) => {
  try { return ['1','true','on','yes'].includes((localStorage.getItem(k)||'').toLowerCase()); } catch { return false; }
};

const ChatPage = () => {
  // Core state
  const [messages, setMessages] = useState([]);
  // Ref mirror to access latest messages inside callbacks without stale closure
  const messagesRef = useRef([]);
  useEffect(() => { messagesRef.current = messages; }, [messages]);
  const [ws, setWs] = useState(null);
  const [loading, setLoading] = useState(true);
  const setMessagesWithLogging = useCallback(updater => setMessages(prev => typeof updater==='function'?updater(prev):updater), []);
  const [connectionStatus, setConnectionStatus] = useState('disconnected');
  const [transportType, setTransportType] = useState(null);
  const [currentChatId, setCurrentChatId] = useState(null); // set via start/resume flow below
  const LOCAL_STORAGE_KEY = 'mozaiks.current_chat_id';
  const [connectionInitialized, setConnectionInitialized] = useState(false);
  const [workflowConfigLoaded, setWorkflowConfigLoaded] = useState(false); // becomes true once workflow config resolved
  const [cacheSeed, setCacheSeed] = useState(null); // per-chat cache seed for unified backend/frontend caching
  const [chatExists, setChatExists] = useState(null); // tri-state: null=unknown, true=exists, false=new
  const connectionInProgressRef = useRef(false);
  // Guard to prevent overlapping start logic (used by preflight existence effect)
  const pendingStartRef = useRef(false);
  const { enterpriseId, workflowName: urlWorkflowName } = useParams();
  const { user, api, config } = useChatUI();
  const [isSidePanelOpen, setIsSidePanelOpen] = useState(false);
  const [forceOverlay, setForceOverlay] = useState(false);
  // Current artifact messages rendered inside ArtifactPanel (not in chat messages)
  const [currentArtifactMessages, setCurrentArtifactMessages] = useState([]);
  // Track the most recent artifact-mode UI event id to manage auto-collapse
  const lastArtifactEventRef = useRef(null);
  // Prevent duplicate restores per connection
  const artifactRestoredOnceRef = useRef(false);
  const currentEnterpriseId = enterpriseId || config?.chat?.defaultEnterpriseId || '68542c1109381de738222350';
  const currentUserId = user?.id || config?.chat?.defaultUserId || '56132';
  // Helper function to get default workflow from registry
  const getDefaultWorkflowFromRegistry = () => {
    const workflows = getLoadedWorkflows();
    return workflows.length > 0 ? workflows[0].name : null;
  };

  const defaultWorkflow = (urlWorkflowName || config?.chat?.defaultWorkflow || getDefaultWorkflowFromRegistry() || '');
  const [currentWorkflowName, setCurrentWorkflowName] = useState(defaultWorkflow);
  const [tokensExhausted, setTokensExhausted] = useState(false);
  // One-time initial spinner: show after websocket connects, hide after first agent chat.text message
  const [showInitSpinner, setShowInitSpinner] = useState(false);
  // Refs for race-free spinner control
  const initSpinnerShownRef = useRef(false);
  const initSpinnerHiddenOnceRef = useRef(false);
  // Track whether we suppressed the synthetic first instruction message (when no initial message configured)
  const firstAgentMessageSuppressedRef = useRef(false);
  // Removed legacy dynamic UI accumulation & dedupe refs (no longer needed with chat.* events)


  // Helper function to extract agent name from nested message structure
  const extractAgentName = useCallback((data) => {
    try {
      // First try direct agent field
      if (data.agent && data.agent !== 'Unknown') {
        return data.agent;
      }
      if (data.agent_name && data.agent_name !== 'Unknown') {
        return data.agent_name;
      }
      
      // Parse content if it's a JSON string containing nested agent info
      if (data.content && typeof data.content === 'string') {
        const parsed = JSON.parse(data.content);
        if (parsed?.data?.content?.sender) {
          return parsed.data.content.sender;
        }
        if (parsed?.data?.agent) {
          return parsed.data.agent;
        }
      }
      
      return 'Agent'; // fallback
    } catch {
      return data.agent || data.agent_name || 'Agent';
    }
  }, []);

  // Simplified incoming handler (namespaced chat.* only)
  const handleIncoming = useCallback((data) => {
    // Log all incoming events for debugging - you can filter this later if needed
    if (data?.type) {
      try { logAgentOutput('INCOMING', extractAgentName(data), data, { type: data?.type }); } catch {}
    }
    if (!data?.type) return;
    // Robust spinner hide: only once
    try {
      if (initSpinnerShownRef.current && !initSpinnerHiddenOnceRef.current) {
        const outerType = data.type || '';
        const isText = outerType === 'chat.text';
        const isInputRequest = outerType === 'chat.input_request';
        const serializedText = !isText && !isInputRequest && typeof data.content === 'string' && 
          (data.content.includes('"type":"chat.text"') || data.content.includes('"type":"chat.input_request"'));
        if (isText || isInputRequest || serializedText) {
          initSpinnerHiddenOnceRef.current = true;
          if (showInitSpinner) console.log('🧹 [SPINNER] Hiding spinner (interactive event). text?', isText, 'input?', isInputRequest, 'serialized?', serializedText);
          setShowInitSpinner(false);
        }
      }
    } catch {}
    if (debugFlag('mozaiks.debug_pipeline')) {
      const agentDbg = data.agent || data.agent_name;
      console.log('[PIPELINE] raw event', {
        type: data.type,
        agent: agentDbg,
        visual: data.is_visual,
        structuredCapable: data.is_structured_capable,
        hasStructuredOutput: !!data.structured_output,
        contentPreview: (data.content||'').slice(0,120)
      });
      if ((data.type === 'chat.print' || data.type === 'chat.text') && data.is_visual === false) {
        console.warn('[PIPELINE] Non-visual agent message received (unexpected?)', agentDbg);
      }
    }
    // Minimal legacy passthrough for still-emitted dynamic UI events until backend fully migrated
    if (data.type === 'ui_tool_event' || data.type === 'UI_TOOL_EVENT') {
      // Create a response callback that uses the WebSocket connection
      const sendResponse = (responseData) => {
        console.log('🔌 ChatPage: Sending WebSocket response:', responseData);
        if (ws && ws.send) {
          return ws.send(responseData);
        } else {
          console.warn('⚠️ No WebSocket connection available for UI tool response');
          return false;
        }
      };
      
      console.debug('🔌 ChatPage: Passing sendResponse callback type:', typeof sendResponse, 'event:', data);
      try {
        dynamicUIHandler.processUIEvent(data, sendResponse);
      } catch (err) {
        console.error('🔌 ChatPage: dynamicUIHandler.processUIEvent threw', err, data);
      }
      return;
    }
    
    // Handle chat_meta events (which may not have chat. prefix)
    if (data.type === 'chat_meta' || data.type === 'chat.chat_meta') {
      // Initial metadata handshake from backend
      console.log('🧬 [META] Received chat_meta event:', data);
      if (data.cache_seed !== undefined && data.cache_seed !== null) {
        setCacheSeed(data.cache_seed);
        if (currentChatId) {
          try { localStorage.setItem(`${LOCAL_STORAGE_KEY}.cache_seed.${currentChatId}`, String(data.cache_seed)); } catch {}
        }
        console.log('🧬 [META] Received cache_seed', data.cache_seed, 'for chat', currentChatId);
      }
      if (data.chat_exists === false) {
        // Backend indicates this chat_id had no persisted session (fresh after client-side reuse)
        setChatExists(false);
        console.log('🧬 [META] Backend reports chat did NOT previously exist. Suppressing artifact restore. chat_id=', currentChatId);
        try {
          // Purge any stale local artifacts for this chat to avoid ghost UI
          localStorage.removeItem(`mozaiks.last_artifact.${currentChatId}`);
          localStorage.removeItem(`mozaiks.current_artifact.${currentChatId}`);
          console.log('🧼 [META] Purged stale artifacts for non-existent chat');
        } catch {}
        // Reset any prior artifact state
        setCurrentArtifactMessages([]);
        lastArtifactEventRef.current = null;
        artifactRestoredOnceRef.current = true; // prevent later restore effect
      } else if (data.chat_exists === true) {
        setChatExists(true);
        console.log('🧬 [META] Backend confirms chat exists. Artifact restore allowed.');
        // If backend already sent last_artifact and we have not restored yet, cache it for restore effect
        if (!artifactRestoredOnceRef.current && data.last_artifact && data.last_artifact.ui_tool_id) {
          try {
            const key = `mozaiks.last_artifact.${currentChatId}`;
            localStorage.setItem(key, JSON.stringify({
              ui_tool_id: data.last_artifact.ui_tool_id,
              eventId: data.last_artifact.event_id || null,
              workflow_name: data.last_artifact.workflow_name || currentWorkflowName,
              payload: data.last_artifact.payload || {},
              display: data.last_artifact.display || 'artifact',
              ts: Date.now(),
            }));
            console.log('🧬 [META] Cached last_artifact from server meta event');
          } catch (e) { console.warn('Failed to cache server last_artifact', e); }
        }
      }
      return;
    }
    
    // Some backends double-serialize the envelope: outer {type, content: JSON-stringified {type:"chat.text", data:{...}}}
    // Detect and unwrap once so downstream logic always works with a flat object.
    // Do this BEFORE checking for chat. prefix so we can unwrap "unknown" events that contain chat events.
    try {
      if (typeof data.content === 'string' && data.content.startsWith('{') && data.content.includes('"type":"')) {
        const inner = JSON.parse(data.content);
        if (inner && inner.type) {
          if (debugFlag('mozaiks.debug_pipeline')) {
            console.log('[PIPELINE] unwrapped nested envelope', { originalType: data.type, innerType: inner.type });
          }
          // If this is chat_meta, handle it directly
          if (inner.type === 'chat_meta') {
            console.log('🧬 [META] Received chat_meta event (unwrapped):', inner);
            const metaData = inner.data || {};
            if (metaData.cache_seed !== undefined && metaData.cache_seed !== null) {
              setCacheSeed(metaData.cache_seed);
              if (currentChatId) {
                try { localStorage.setItem(`${LOCAL_STORAGE_KEY}.cache_seed.${currentChatId}`, String(metaData.cache_seed)); } catch {}
              }
              console.log('🧬 [META] Received cache_seed', metaData.cache_seed, 'for chat', currentChatId);
            }
            if (metaData.chat_exists === false) {
              setChatExists(false);
              console.log('🧬 [META] Backend reports chat did NOT previously exist. Suppressing artifact restore. chat_id=', currentChatId);
              try {
                localStorage.removeItem(`mozaiks.last_artifact.${currentChatId}`);
                localStorage.removeItem(`mozaiks.current_artifact.${currentChatId}`);
                console.log('🧼 [META] Purged stale artifacts for non-existent chat');
              } catch {}
              setCurrentArtifactMessages([]);
              lastArtifactEventRef.current = null;
              artifactRestoredOnceRef.current = true;
            } else if (metaData.chat_exists === true) {
              setChatExists(true);
              console.log('🧬 [META] Backend confirms chat exists. Artifact restore allowed.');
              if (!artifactRestoredOnceRef.current && metaData.last_artifact && metaData.last_artifact.ui_tool_id) {
                try {
                  const key = `mozaiks.last_artifact.${currentChatId}`;
                  localStorage.setItem(key, JSON.stringify({
                    ui_tool_id: metaData.last_artifact.ui_tool_id,
                    eventId: metaData.last_artifact.event_id || null,
                    workflow_name: metaData.last_artifact.workflow_name || currentWorkflowName,
                    payload: metaData.last_artifact.payload || {},
                    display: metaData.last_artifact.display || 'artifact',
                    ts: Date.now(),
                  }));
                  console.log('🧬 [META] Cached last_artifact from server meta event');
                } catch (e) { console.warn('Failed to cache server last_artifact', e); }
              }
            }
            return;
          }
          // For other events, unwrap and continue processing
          const innerData = inner.data || {};
          data.type = inner.type; // Use the inner type (could be chat.*, unknown, etc.)
          if (typeof innerData.content === 'string') data.content = innerData.content;
          if (innerData.agent) data.agent = innerData.agent;
          if (innerData.agent_name) data.agent_name = innerData.agent_name;
          if (innerData.sender && !innerData.agent && !innerData.agent_name) data.agent = innerData.sender;
          // Capability flags
          data.is_structured_capable = !!innerData.is_structured_capable;
          if (innerData.is_visual !== undefined) data.is_visual = innerData.is_visual;
          if (innerData.is_tool_agent !== undefined) data.is_tool_agent = innerData.is_tool_agent;
          // Preserve structured output payloads if present
          if (innerData.structured_output !== undefined) data.structured_output = innerData.structured_output;
          if (innerData.structured_schema !== undefined) data.structured_schema = innerData.structured_schema;
          if (debugFlag('mozaiks.debug_pipeline')) {
            console.log('[PIPELINE] unwrap summary', {
              finalType: data.type,
              agent: data.agent || data.agent_name,
              visual: data.is_visual,
              structuredCapable: data.is_structured_capable,
              contentPreview: (data.content||'').slice(0,120)
            });
          }
        }
      }
    } catch (e) {
      if (debugFlag('mozaiks.debug_pipeline')) console.warn('[PIPELINE] failed to unwrap nested envelope', e);
    }
    
    // Allow chat.* events and other known event types (like input_request, unknown, etc.)
    if (!data.type.startsWith('chat.') && !['input_request', 'unknown'].includes(data.type)) return; // ignore unrecognized legacy

    // Some events may arrive already as { type:'chat.text', data:{ ...actualFields... } } (no double-serialization)
    // or after the above unwrap we can still retain an inner data object we need to promote.
    try {
      if (data.data && typeof data.data === 'object') {
        const inner = data.data;
        // Promote only if target field missing or clearly placeholder
        const promote = (k, aliasArr=[]) => {
          if (inner[k] === undefined) return;
          if (data[k] === undefined || data[k] === 'Unknown' || data[k] === null) data[k] = inner[k];
          // Apply aliases (e.g. sender -> agent) if primary absent
          aliasArr.forEach(alias => {
            if (data[alias] === undefined && inner[k] !== undefined) data[alias] = inner[k];
          });
        };
        promote('agent');
        promote('agent_name');
        // sender can act as agent fallback
        if (!data.agent && !data.agent_name && inner.sender) data.agent = inner.sender;
        // Core textual content (avoid overwriting if we already have a non-empty string)
        if (inner.content && (!data.content || !String(data.content).trim())) data.content = inner.content;
        // Capability / classification flags
        ['is_visual','is_structured_capable','is_tool_agent'].forEach(f => { if (inner[f] !== undefined && data[f] === undefined) data[f] = inner[f]; });
        // Structured output payload + schema
        if (inner.structured_output !== undefined && data.structured_output === undefined) data.structured_output = inner.structured_output;
        if (inner.structured_schema !== undefined && data.structured_schema === undefined) data.structured_schema = inner.structured_schema;
        // UI tool / component hints (input_request etc.)
        ['component_type','ui_tool_id','tool_name','tool_call_id','request_id','progress_percent','prompt'].forEach(f => {
          if (inner[f] !== undefined && data[f] === undefined) data[f] = inner[f];
        });
      }
    } catch (e) {
      if (debugFlag('mozaiks.debug_pipeline')) console.warn('[PIPELINE] failed to promote data.data fields', e);
    }

    // Final resolution / fallback normalization before dispatch
    try {
      if (typeof data.content === 'object' && data.content !== null) {
        // Some backends might leave content object like { content: 'text' }
        if (data.content.content && typeof data.content.content === 'string') {
          data.content = data.content.content;
        } else if (data.content.text && typeof data.content.text === 'string') {
          data.content = data.content.text;
        } else if (data.content.message && typeof data.content.message === 'string') {
          data.content = data.content.message;
        }
      }
      if (!data.agent && !data.agent_name && data.sender) data.agent = data.sender;
      if (debugFlag('mozaiks.debug_pipeline')) {
        console.log('[PIPELINE] resolved event pre-dispatch', {
          type: data.type,
          agent: data.agent || data.agent_name,
          visual: data.is_visual,
          structuredCapable: data.is_structured_capable,
          hasStructuredOutput: !!data.structured_output,
          contentPreview: (typeof data.content === 'string' ? data.content : JSON.stringify(data.content || '')).slice(0,120)
        });
      }
    } catch {}

    const evt = data.type.slice(5);
    switch (evt) {
      case 'print': {
        // Suppress very first auto-generated instruction style message if workflow has no explicit initial_message_to_user
        try {
          if (!firstAgentMessageSuppressedRef.current) {
            const wfCfg = workflowConfig?.getWorkflowConfig(currentWorkflowName);
            const hasInitial = !!(wfCfg && wfCfg.initial_message_to_user && wfCfg.initial_message_to_user.trim());
            const seq = data.sequence || data.data?.sequence;
            if (!hasInitial && (seq === 1 || seq === '1')) {
              if (debugFlag('mozaiks.debug_pipeline')) console.log('[PIPELINE] suppressing first agent print message (no initial_message_to_user configured)');
              firstAgentMessageSuppressedRef.current = true; // one-time action
              if (showInitSpinner) setShowInitSpinner(false); // still hide spinner even if we suppress message
              return; // skip rendering
            }
          }
        } catch {}
        const agentName = extractAgentName(data);
        const chunk = data.content || '';
        if (!chunk) return;
        setMessagesWithLogging(prev => {
          const updated = [...prev];
            for (let i = updated.length -1; i>=0; i--) {
              const m = updated[i];
              if (m.__streaming && m.agentName === agentName) {
                m.content += chunk;
                if (debugFlag('mozaiks.debug_pipeline')) {
                  console.log('[PIPELINE] appended chunk to existing stream', { agent: agentName, newLength: m.content.length });
                }
                return updated;
              }
            }
          // Capability flags (new schema) from backend event data
          const isStructuredCapable = !!data.is_structured_capable;
          const isVisual = !!data.is_visual;
          const isToolAgent = !!data.is_tool_agent;
          updated.push({
            id:`stream-${Date.now()}`,
            sender:'agent',
            agentName,
            content:chunk,
            isStreaming:true,
            __streaming:true,
            isStructuredCapable,
            isVisual,
            isToolAgent
          });
          if (debugFlag('mozaiks.debug_pipeline')) {
            console.log('[PIPELINE] created new streaming message', { agent: agentName, chunkLen: chunk.length, isStructuredCapable, isVisual });
          }
          return updated;
        });
        return;
      }
      case 'text': {
        // Suppress very first auto-generated instruction style message if workflow has no explicit initial_message_to_user
        try {
          if (!firstAgentMessageSuppressedRef.current) {
            const wfCfg = workflowConfig?.getWorkflowConfig(currentWorkflowName);
            const hasInitial = !!(wfCfg && wfCfg.initial_message_to_user && wfCfg.initial_message_to_user.trim());
            const seq = data.sequence || data.data?.sequence;
            if (!hasInitial && (seq === 1 || seq === '1')) {
              if (debugFlag('mozaiks.debug_pipeline')) console.log('[PIPELINE] suppressing first agent text message (no initial_message_to_user configured)');
              firstAgentMessageSuppressedRef.current = true; // one-time action
              if (showInitSpinner) {
                console.log('🧹 [SPINNER] Hiding spinner due to suppressed first message');
                setShowInitSpinner(false); // hide spinner even if message suppressed
              }
              return; // skip rendering
            }
          }
        } catch {}
        const content = data.content || '';
        // Enhanced suppression for assistant parroting user input (including minor variation)
        try {
          if (content) {
            const msgs = messagesRef.current;
            if (msgs.length) {
              const lastUserIdx = [...msgs].reverse().findIndex(m => m && m.sender === 'user');
              if (lastUserIdx !== -1) {
                const actualIndex = msgs.length - 1 - lastUserIdx;
                const lastUser = msgs[actualIndex];
                if (lastUser) {
                  const normUser = String(lastUser.content||'').trim();
                  const normContent = String(content).trim();
                  // Simple fuzzy: treat as echo if one contains the other and length difference small
                  const shorter = normUser.length <= normContent.length ? normUser : normContent;
                  const longer = normUser.length > normContent.length ? normUser : normContent;
                  const lengthDiff = Math.abs(normUser.length - normContent.length);
                  const containsRel = longer.includes(shorter);
                  const smallDiff = lengthDiff <= 3; // allow small typos / spacing differences
                  const identical = normUser === normContent;
                  if (normUser && (identical || (containsRel && smallDiff))) {
                    if (debugFlag('mozaiks.debug_pipeline')) console.log('[PIPELINE] suppressing assistant echo/fuzzy repeat of user content');
                    return; // skip echo-like repetition
                  }
                }
              }
            }
          }
        } catch {}
        if (!content.trim()) return;
        const agentName = extractAgentName(data);
        setMessagesWithLogging(prev => {
          const updated = [...prev];
          if (updated.length) {
            const last = updated[updated.length-1];
            if (last.__streaming && last.agentName === agentName) {
              last.isStreaming = false; delete last.__streaming; if(!last.content.endsWith(content)) last.content+=content; return updated;
            }
          }
          
          // Capability + structured output payload (if any) from new unified dispatcher
          const isStructuredCapable = !!data.is_structured_capable;
          const structuredOutput = data.structured_output || null; // actual structured content (if produced)
          const structuredSchema = data.structured_schema || null; // schema describing structuredOutput
          const isVisual = !!data.is_visual;
          const isToolAgent = !!data.is_tool_agent;
          updated.push({
            id:`text-${Date.now()}`,
            sender:'agent',
            agentName,
            content,
            isStreaming:false,
            isStructuredCapable,
            structuredOutput,
            structuredSchema,
            isVisual,
            isToolAgent
          });
          if (debugFlag('mozaiks.debug_pipeline')) {
            console.log('[PIPELINE] appended final text message', { agent: agentName, len: content.length, isStructuredCapable, hasStructuredOutput: !!structuredOutput });
          }
          return updated;
        });
        // Hide the one-time initialization spinner after the first successfully rendered chat.text
        if (showInitSpinner) {
          setShowInitSpinner(false);
        }
        return;
      }
      case 'input_request': {
        const componentType = data.component_type || data.ui_tool_id || null;
        if (componentType) {
          console.debug('🧩 [UI_EVENT] input_request -> processUIEvent payload:', {
            type: 'user_input_request',
            data: {
              input_request_id: data.request_id,
              chat_id: currentChatId,
              payload: {
                prompt: data.prompt,
                ui_tool_id: componentType,
                workflow_name: currentWorkflowName
              }
            }
          });
          try {
            dynamicUIHandler.processUIEvent({
            type: 'user_input_request',
            data: {
              input_request_id: data.request_id,
              chat_id: currentChatId,
              payload: {
                prompt: data.prompt,
                ui_tool_id: componentType,
                workflow_name: currentWorkflowName
              }
            }
            });
          } catch (err) {
            console.error('🧩 [UI_EVENT] dynamicUIHandler.processUIEvent threw for input_request', err, data);
          }
        }
        return;
      }
      case 'chat.input_request': {
        console.log('📥 [INPUT_REQUEST] Received chat.input_request:', data);
        const componentType = data.component_type || data.ui_tool_id || null;
        if (componentType) {
          console.debug('🧩 [UI_EVENT] chat.input_request -> processUIEvent payload:', {
            type: 'user_input_request',
            data: {
              input_request_id: data.request_id,
              chat_id: currentChatId,
              payload: {
                prompt: data.prompt,
                ui_tool_id: componentType,
                workflow_name: currentWorkflowName
              }
            }
          });
          try {
            dynamicUIHandler.processUIEvent({
              type: 'user_input_request',
              data: {
                input_request_id: data.request_id,
                chat_id: currentChatId,
                payload: {
                  prompt: data.prompt,
                  ui_tool_id: componentType,
                  workflow_name: currentWorkflowName
                }
              }
            });
          } catch (err) {
            console.error('🧩 [UI_EVENT] dynamicUIHandler.processUIEvent threw for chat.input_request', err, data);
          }
        } else {
          // Fallback: show as a simple input request
          console.log('📝 [INPUT_REQUEST] Simple input request:', data.prompt);
          // You could add UI logic here to show an input dialog
        }
        return;
      }
      case 'tool_call': {
        if (data.component_type || (data.data && data.data.component_type)) {
          const envelope = data || {};
          const detail = envelope.data || {};
          const toolName = envelope.tool_name || detail.tool_name || detail.tool || envelope.ui_tool_id || 'UnknownTool';
          const componentType = envelope.component_type || detail.component_type || detail.component || toolName;
          const basePayload = detail.payload || envelope.payload || {};
          const payloadKeys = Object.keys(basePayload);
          console.log('🛠️ [TOOL_CALL] Processing UI tool event:', toolName, 'component:', componentType);
          console.log('🛠️ [TOOL_CALL] Raw tool_call data:', envelope);
          console.log('🛠️ [TOOL_CALL] Payload keys received:', payloadKeys);
          const derivedDisplay = envelope.display || envelope.display_type || envelope.mode || detail.display || detail.display_type || detail.mode || basePayload.display || basePayload.mode || null;
          const eventId = envelope.tool_call_id || envelope.corr || detail.tool_call_id || detail.corr || null;
          const awaiting = envelope.awaiting_response !== undefined ? envelope.awaiting_response : detail.awaiting_response;
          dynamicUIHandler.processUIEvent({
            type: 'ui_tool_event',
            ui_tool_id: toolName,
            eventId: eventId || undefined,
            workflow_name: currentWorkflowName,
            display: derivedDisplay,
            payload: {
              ...basePayload,
              tool_name: toolName,
              component_type: componentType,
              workflow_name: currentWorkflowName,
              awaiting_response: awaiting,
              ...(derivedDisplay ? { display: derivedDisplay } : {})
            }
          });
        } else {
          setMessagesWithLogging(prev => [...prev, { id: data.tool_call_id || `tool-call-${Date.now()}`, sender:'system', agentName:'System', content:`🔧 Tool Call: ${data.tool_name}`, isStreaming:false }]);
        }
        return;
      }
      case 'tool_response': {
        const responseContent = data.success ? `✅ Tool Response: ${data.content || 'Success'}` : `❌ Tool Failed: ${data.content || 'Error'}`;
        setMessagesWithLogging(prev => [...prev, { id: data.tool_call_id || `tool-response-${Date.now()}`, sender:'system', agentName:'System', content: responseContent, isStreaming:false }]);
        return;
      }
      case 'usage_summary': {
        setMessagesWithLogging(prev => [...prev, { id:`usage-${Date.now()}`, sender:'system', agentName:'System', content:`📊 Usage: tokens=${data.total_tokens} prompt=${data.prompt_tokens} completion=${data.completion_tokens}${data.cost?` cost=$${data.cost}`:''}`, isStreaming:false }]);
        return;
      }
      case 'select_speaker': {
        // Speaker selection often marks a new turn/run start. If we have an open artifact
        // from a prior sequence, collapse it now and clear the cache.
        if (lastArtifactEventRef.current && isSidePanelOpen) {
          try {
            console.log('🧹 [UI] New sequence detected; collapsing ArtifactPanel (event:', lastArtifactEventRef.current, ')');
          } catch {}
          setIsSidePanelOpen(false);
          lastArtifactEventRef.current = null;
          setCurrentArtifactMessages([]);
          // Clear artifact cache on new conversation turn
          try {
            if (currentChatId) {
              localStorage.removeItem(`mozaiks.current_artifact.${currentChatId}`);
              localStorage.removeItem(`mozaiks.last_artifact.${currentChatId}`);
            }
          } catch {}
        }
        return;
      }
      case 'tool_progress': {
        // Update or append progress for a long-running tool
        const progress = data.progress_percent;
        const tool = data.tool_name || 'tool';
        setMessagesWithLogging(prev => {
          const updated = [...prev];
          for (let i = updated.length - 1; i >=0; i--) {
            const m = updated[i];
            if (m.metadata && m.metadata.event_type === 'tool_call' && m.metadata.tool_name === tool) {
              m.content = `🔧 ${tool} progress: ${progress}%`;
              m.metadata.progress_percent = progress;
              return updated;
            }
          }
          updated.push({ id:`tool-progress-${Date.now()}`, sender:'system', agentName:'System', content:`🔧 ${tool} progress: ${progress}%`, isStreaming:false, metadata:{ event_type:'tool_progress', tool_name: tool, progress_percent: progress }});
          return updated;
        });
        return;
      }
      case 'input_timeout': {
        setMessagesWithLogging(prev => [...prev, { id:`timeout-${Date.now()}`, sender:'system', agentName:'System', content:`⏱️ Input request timed out.`, isStreaming:false }]);
        return;
      }
      case 'token_warning': {
        setMessagesWithLogging(prev => [...prev, { id:`warn-${Date.now()}`, sender:'system', agentName:'System', content:`⚠️ Approaching token limit`, isStreaming:false }]);
        return;
      }
      case 'token_exhausted': {
        setTokensExhausted(true);
        setMessagesWithLogging(prev => [...prev, { id:`exhaust-${Date.now()}`, sender:'system', agentName:'System', content:`⛽ Token limit reached. Upgrade or start a new session.`, isStreaming:false }]);
        return;
      }
      case 'run_complete': {
        setMessagesWithLogging(prev => [...prev, { id:`run-complete-${Date.now()}`, sender:'system', agentName:'System', content:`✅ Run complete (${data.reason||'finished'})`, isStreaming:false }]);
        return;
      }
      case 'error': {
        setMessagesWithLogging(prev => [...prev, { id:`err-${Date.now()}`, sender:'system', agentName:'System', content:`❌ Error: ${data.message||'Unknown error'}`, isStreaming:false }]);
        return;
      }
      case 'input_ack':
        // Acknowledgment: no UI mutation needed
        return;
      case 'resume_boundary':
  // Replay boundary marker: insert a divider system note
  setMessagesWithLogging(prev => [...prev, { id:`resume-${Date.now()}`, sender:'system', agentName:'System', content:`🔄 Session replay complete. Live events resumed.`, isStreaming:false }]);
        return;
      default:
        return;
    }
  }, [currentChatId, currentWorkflowName, setMessagesWithLogging, extractAgentName, ws, isSidePanelOpen, showInitSpinner]);

  // Debug: Log spinner state changes
  useEffect(() => {
    console.log('🧹 [SPINNER] State changed to:', showInitSpinner);
  }, [showInitSpinner]);

  // Workflow configuration & resume bootstrap (no direct startChat here; handled by preflight existence effect)
  useEffect(() => {
    if (!api) return;
    setWorkflowConfigLoaded(true);
    if (!currentChatId) {
      let stored = null;
      try { stored = localStorage.getItem(LOCAL_STORAGE_KEY); } catch {}
      if (stored) {
        setCurrentChatId(stored);
        try {
          const seedStored = localStorage.getItem(`${LOCAL_STORAGE_KEY}.cache_seed.${stored}`);
          if (seedStored) {
            setCacheSeed(Number(seedStored));
            console.log('🧬 [RESUME] Loaded cached cache_seed for resumed chat', stored, seedStored);
          }
        } catch {}
      }
    }
  }, [api, currentChatId]);

  // NEW: Preflight chat existence + cache clearing logic
useEffect(() => {
  if (!api) return;
  if (!workflowConfigLoaded) return; // wait until registry is ready
  if (currentChatId) return; // existing logic handles resume or already started
  if (pendingStartRef.current) return;

  pendingStartRef.current = true;
  (async () => {
    try {
      const urlParams = new URLSearchParams(window.location.search);
      const chatIdParam = urlParams.get('chat_id');
      let reuseChatId = chatIdParam;

      if (reuseChatId) {
        console.log('[EXISTS] Checking existence of chat', reuseChatId);
        try {
          const wfName = currentWorkflowName;
          const resp = await fetch(`http://localhost:8000/api/chats/exists/${currentEnterpriseId}/${wfName}/${reuseChatId}`);
          if (resp.ok) {
            const data = await resp.json();
            if (data.exists) {
              console.log('[EXISTS] Chat exists; adopting chat_id and skipping startChat');
              setCurrentChatId(reuseChatId);
              setChatExists(true);
              pendingStartRef.current = false;
              return;
            } else {
              console.log('[EXISTS] Chat does NOT exist; clearing any cached artifacts for that id');
              try {
                localStorage.removeItem(`mozaiks.last_artifact.${reuseChatId}`);
                localStorage.removeItem(`mozaiks.current_artifact.${reuseChatId}`);
              } catch {}
            }
          }
        } catch (e) {
          console.warn('[EXISTS] Existence check failed:', e);
        }
      }

      console.log('[INIT] Creating new chat via startChat');
      const result = await api.startChat(currentEnterpriseId, currentWorkflowName, currentUserId);
      if (result && (result.chat_id || result.id)) {
        const newId = result.chat_id || result.id;
        const reused = !!result.reused;
        setCurrentChatId(newId);
        setChatExists(reused);
        try { localStorage.setItem(LOCAL_STORAGE_KEY, newId); } catch {}
        if (!reused) {
          try {
            localStorage.removeItem(`mozaiks.last_artifact.${newId}`);
            localStorage.removeItem(`mozaiks.current_artifact.${newId}`);
          } catch {}
        }
        console.log('[INIT] startChat complete', { newId, reused });
      }
    } catch (e) {
      console.error('[INIT] Failed to initialize chat:', e);
    } finally {
      pendingStartRef.current = false;
    }
  })();
}, [api, workflowConfigLoaded, currentChatId, currentWorkflowName, currentEnterpriseId, currentUserId]);

  // Expose a helper to force-reset the current chat client-side (can be wired to a debug button later)
  const forceResetChat = useCallback(() => {
    try {
      const current = localStorage.getItem(LOCAL_STORAGE_KEY);
      if (current) {
        [
          `mozaiks.last_artifact.${current}`,
          `mozaiks.current_artifact.${current}`,
          `${LOCAL_STORAGE_KEY}.cache_seed.${current}`,
        ].forEach(k => { try { localStorage.removeItem(k); } catch {} });
      }
      console.log('🧼 [CACHE] Manual force reset invoked; clearing in-memory state');
    } catch {}
    setCurrentArtifactMessages([]);
    lastArtifactEventRef.current = null;
    artifactRestoredOnceRef.current = false;
    setCurrentChatId(null);
  }, []);

  // Dev: expose reset helper & read cacheSeed to avoid unused warnings
  useEffect(() => {
    // Use cacheSeed in a benign way (log only when it changes)
    if (cacheSeed !== null) {
      // Minimal, low-noise log – toggle off by removing line if undesired
      console.debug('🧬 Active cacheSeed now', cacheSeed);
    }
    // Expose forceResetChat for manual debugging in console
    try { window.__mozaiksForceResetChat = forceResetChat; } catch {}
    
    // Expose artifact inspection helper
    try {
      window.__mozaiksInspectArtifacts = () => {
        const keys = [];
        const chatId = currentChatId || localStorage.getItem(LOCAL_STORAGE_KEY);
        console.log('🔍 [DEBUG] Inspecting artifact localStorage for chat:', chatId);
        
        for (let i = 0; i < localStorage.length; i++) {
          const key = localStorage.key(i);
          if (!key) continue;
          
          if (key.includes('artifact') || key.includes('cache_seed') || key.includes('current_chat_id')) {
            const value = localStorage.getItem(key);
            keys.push({ key, value: value?.slice(0, 200) + (value?.length > 200 ? '...' : '') });
          }
        }
        
        console.table(keys);
        return keys;
      };
    } catch {}
  }, [cacheSeed, forceResetChat, currentChatId]);

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

      const workflowName = urlWorkflowName || getDefaultWorkflowFromRegistry();
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
            // Show one-time spinner ONLY if it has never been shown and never been hidden
            if (!initSpinnerHiddenOnceRef.current && !initSpinnerShownRef.current) {
              console.log('🧹 [SPINNER] Showing initial spinner on WebSocket connect');
              setShowInitSpinner(true);
              initSpinnerShownRef.current = true;
            } else {
              console.log('🧹 [SPINNER] Skipping show on reconnect (hiddenOnce=', initSpinnerHiddenOnceRef.current, 'shownRef=', initSpinnerShownRef.current, ')');
              // Ensure we never regress into showing again this session
              if (initSpinnerHiddenOnceRef.current) {
                initSpinnerShownRef.current = true; // lock state
              }
            }
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
        const workflowName = urlWorkflowName || getDefaultWorkflowFromRegistry();
        if (!workflowName) {
          throw new Error('No workflow available');
        }
  // console.debug('Using workflow name:', workflowName);
        
        // Query transport info from backend and use it (was previously unused)
        const transportInfo = await api.getWorkflowTransport(workflowName);
        // transportInfo example: { transport: 'websocket' | 'sse' | 'poll', allow_resume: true }
        if (transportInfo && transportInfo.transport) {
          setTransportType(transportInfo.transport);
        } else {
          setTransportType('websocket');
        }
        // Expose transport flags or capabilities if provided
        if (transportInfo && transportInfo.allow_resume === false) {
          console.debug('Transport indicates resume is disabled for', workflowName);
        }
        setCurrentWorkflowName(workflowName);
        return connectWebSocket();
      } catch (error) {
        console.error('Error querying workflow transport:', error);
        // Fallback to WebSocket
        const fallbackWf = getDefaultWorkflowFromRegistry();
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

  // Subscribe to DynamicUIHandler updates and insert UI tool events into chat messages
  useEffect(() => {
    // Bridge dynamic UI events into the chat message stream
    const unsubscribe = dynamicUIHandler.onUIUpdate((update) => {
      try {
        if (!update || !update.type) return;
        // Only handle ui_tool_event here; other updates (status/component updates) are ignored for now
  if (update.type === 'ui_tool_event') {
    const { ui_tool_id, payload = {}, eventId, workflow_name, onResponse, display } = update;
          console.log('🧩 [UI] ChatPage received ui_tool_event -> inserting into messages', { ui_tool_id, eventId, workflow_name });
          // If this UI tool requests artifact display, auto-open the ArtifactPanel like OpenAI/Claude canvases
    const displayMode = (display || payload.display || payload.mode);
    if (displayMode === 'artifact') {
      console.log('🖼️ [UI] Auto-opening ArtifactPanel for artifact-mode event');
      setIsSidePanelOpen(true);
      const agentText = payload.agent_message || payload.description || null;
      if (agentText) {
        setMessagesWithLogging((prev) => {
          const hasExisting = prev.some(msg => msg?.metadata?.eventId === (eventId || ui_tool_id) && msg?.metadata?.type === 'ui_tool_agent_message');
          if (hasExisting) return prev;
          return [
            ...prev,
            {
              id: `ui-msg-${eventId || Date.now()}`,
              sender: 'agent',
              agentName: payload.agentName || 'Agent',
              content: agentText,
              isStreaming: false,
              metadata: { type: 'ui_tool_agent_message', eventId: eventId || ui_tool_id, ui_tool_id }
            }
          ];
        });
      }
      // Create artifact payload for ArtifactPanel to render
      try {
        const artifactMsg = {
          id: `ui-artifact-${eventId || Date.now()}`,
          sender: 'agent',
          agentName: payload.agentName || 'Agent',
          content: payload.structured_output || payload.content || payload || {},
          isStreaming: false,
          uiToolEvent: { ui_tool_id, payload, eventId, workflow_name, onResponse, display: displayMode }
        };
        console.log('🖼️ [UI] Setting currentArtifactMessages', artifactMsg.id);
        setCurrentArtifactMessages([artifactMsg]);
        
        // Also cache to localStorage for persistence across panel open/close
        try {
          if (currentChatId) {
            const cacheKey = `mozaiks.current_artifact.${currentChatId}`;
            // Create a serializable version without the function
            const serializableArtifact = {
              ...artifactMsg,
              uiToolEvent: {
                ...artifactMsg.uiToolEvent,
                onResponse: null // Functions can't be serialized, will be reconstructed on restore
              }
            };
            localStorage.setItem(cacheKey, JSON.stringify(serializableArtifact));
            console.log('🖼️ [UI] Cached artifact to localStorage');
          }
        } catch (e) { console.warn('Failed to cache artifact', e); }
      } catch (e) { console.warn('Failed to set artifact message', e); }
            // Remember this artifact to collapse on next sequence
            lastArtifactEventRef.current = eventId || ui_tool_id || 'artifact';
            // Persist minimal artifact session state for graceful refresh restore
            try {
              if (currentChatId) {
                const key = `mozaiks.last_artifact.${currentChatId}`;
                const cache = {
                  ui_tool_id,
                  eventId: eventId || null,
                  workflow_name,
                  payload,
      display: displayMode || 'artifact',
                  ts: Date.now(),
                };
                localStorage.setItem(key, JSON.stringify(cache));
              }
            } catch {}
  // Don't inject artifact UIs into the chat feed; they'll render in ArtifactPanel only
  return;
          }
          setMessagesWithLogging((prev) => [
            ...prev,
            {
              id: `ui-${eventId || Date.now()}`,
              sender: 'agent',
              agentName: payload.agentName || 'Agent',
              content: (payload.agent_message || payload.description || ''), // Surface agent context alongside inline UI
              isStreaming: false,
              uiToolEvent: {
                ui_tool_id,
                payload,
                eventId,
                workflow_name,
                onResponse,
                // Surface display mode for inline Completed chip logic
    display: displayMode || 'inline',
              },
            },
          ]);
        }
      } catch (err) {
        console.error('❌ Failed to handle DynamicUIHandler update in ChatPage:', err);
      }
    });
    return () => {
      if (typeof unsubscribe === 'function') unsubscribe();
    };
  }, [setMessagesWithLogging, currentChatId]);

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

  // Submit a pending input request via WebSocket control message
  const submitInputRequest = useCallback((input_request_id, text) => {
    if (!ws || !ws.socket || ws.socket.readyState !== WebSocket.OPEN) {
      console.warn('⚠️ Cannot submit input request; socket not open');
      return false;
    }
    return ws.send({
      type: 'user.input.submit',
      input_request_id,
      text
    });
  }, [ws]);

  // Handle agent UI actions
  const handleAgentAction = async (action) => {
    console.log('Agent action received in chat page:', action);
    
    try {
      // Handle UI tool responses for the dynamic UI system
      if (action.type === 'ui_tool_response') {
        console.log('🎯 Processing UI tool response:', action);

        // If this response corresponds to the most recent artifact event, close the panel immediately
        if (lastArtifactEventRef.current && (!action.eventId || action.eventId === lastArtifactEventRef.current)) {
          try { console.log('🧹 [UI] Artifact response received; collapsing ArtifactPanel now'); } catch {}
          setIsSidePanelOpen(false);
            lastArtifactEventRef.current = null;
          console.log('🖼️ [UI] Clearing currentArtifactMessages due to response');
          setCurrentArtifactMessages([]);
          // Clear persisted artifact cache for this chat
          try { if (currentChatId) localStorage.removeItem(`mozaiks.last_artifact.${currentChatId}`); } catch {}
        }
        // If we lack a real eventId (e.g., restored artifact), don't submit to backend; just close locally
        if (!action.eventId) {
          console.log('ℹ️ Skipping backend submission for restored or legacy UI tool response (no eventId)');
          return;
        }

        const payload = {
          event_id: action.eventId,
          response_data: action.response
        };

        // Send the UI tool response to the backend
        try {
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
        } catch (e) {
          console.error('❌ Network error submitting UI tool response:', e);
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
    setIsSidePanelOpen((open) => {
      const next = !open;
      
      if (next && currentArtifactMessages.length === 0) {
        // Panel opening and no current artifact - try to restore from cache
        try {
          const cacheKey = `mozaiks.current_artifact.${currentChatId}`;
          const cached = localStorage.getItem(cacheKey);
          if (cached) {
            const artifactMsg = JSON.parse(cached);
            
            // Reconstruct the onResponse function since it can't be serialized
            if (artifactMsg.uiToolEvent && !artifactMsg.uiToolEvent.onResponse) {
              artifactMsg.uiToolEvent.onResponse = (response) => {
                console.log('🔌 [UI] Cached artifact response (no longer functional):', response);
                console.warn('⚠️ This is a restored artifact - responses may not work until next interaction');
              };
            }
            
            console.log('🖼️ [UI] Restored artifact from cache on panel open');
            setCurrentArtifactMessages([artifactMsg]);
            lastArtifactEventRef.current = artifactMsg.uiToolEvent?.eventId || 'cached';
          }
        } catch (e) { console.warn('Failed to restore artifact from cache', e); }
      }
      
      console.log(`🖼️ [UI] Panel ${next ? 'opening' : 'closing'} - keeping artifact cached`);
      return next;
    });
  };

  // Simplified artifact restore effect: only restore when chatExists === true and connection is open
  // last_artifact semantics:
  //   - Cached locally on each artifact-mode ui_tool_event
  //   - Server persists ONLY the most recent artifact (overwrite strategy)
  //   - On refresh / second user: websocket chat_meta may include last_artifact; if not, we fetch /api/chats/meta
  //   - We avoid speculative restores for brand new chats (chat_exists === false)
  useEffect(() => {
    if (connectionStatus !== 'connected') return;
    if (!currentChatId) return;
    if (!chatExists) return; // only restore for persisted chats
    if (artifactRestoredOnceRef.current) return;

    try {
      const key = `mozaiks.last_artifact.${currentChatId}`;
      const raw = localStorage.getItem(key);
      if (!raw) return;
      const cached = JSON.parse(raw);
      if (!cached || !cached.ui_tool_id) return;

      console.log('[RESTORE] Restoring cached artifact for chat', currentChatId, cached.ui_tool_id);
      setIsSidePanelOpen(true);
      const restoredMsg = {
        id: `ui-restored-${Date.now()}`,
        sender: 'agent',
        agentName: cached.payload?.agentName || 'Agent',
        content: cached.payload?.structured_output || cached.payload || {},
        isStreaming: false,
        uiToolEvent: {
          ui_tool_id: cached.ui_tool_id,
          payload: cached.payload || {},
          eventId: cached.eventId || null,
          workflow_name: cached.workflow_name || currentWorkflowName,
          onResponse: undefined,
          display: cached.display || 'artifact',
          restored: true,
        },
      };
      setCurrentArtifactMessages([restoredMsg]);
      artifactRestoredOnceRef.current = true;
    } catch (e) {
      console.warn('[RESTORE] Failed to restore artifact:', e);
    }
  }, [connectionStatus, currentChatId, chatExists, currentWorkflowName]);

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
      {showInitSpinner && (
        // Make the overlay visually blocking but non-interactive so background UI can still receive events
        <div className="fixed inset-0 flex items-center justify-center bg-black/20 backdrop-blur-sm z-50 pointer-events-none">
          <div className="pointer-events-auto">
            <LoadingSpinner />
          </div>
        </div>
      )}
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
          {/* Chat Pane - lock to 50% width when artifact is open, 100% when closed */}
          <div className={`flex flex-col px-4 min-h-0 overflow-hidden transition-all duration-300 ${isSidePanelOpen ? 'md:w-2/5 md:flex-none' : 'w-full flex-1'}`}>
            
            <ChatInterface 
              messages={messages} 
              onSendMessage={sendMessage} 
              loading={loading}
              onAgentAction={handleAgentAction}
              onArtifactToggle={toggleSidePanel}
              connectionStatus={connectionStatus}
              transportType={transportType}
              workflowName={currentWorkflowName}
              structuredOutputs={getWorkflow(currentWorkflowName)?.structuredOutputs || {}}
              startupMode={workflowConfig?.getWorkflowConfig(currentWorkflowName)?.startup_mode}
              initialMessageToUser={workflowConfig?.getWorkflowConfig(currentWorkflowName)?.initial_message_to_user}
              onRetry={retryConnection}
              tokensExhausted={tokensExhausted}
              submitInputRequest={submitInputRequest}
            />
          </div>
          
          {/* Artifact Panel - 50% width, slides in from right (desktop only when not forcing overlay) */}
          {isSidePanelOpen && !forceOverlay && (
            <div className="hidden md:flex md:w-3/5 md:flex-none min-h-0 h-full px-4">
              <ArtifactPanel onClose={toggleSidePanel} messages={currentArtifactMessages} />
            </div>
          )}
        </div>
      </div>

      {/* Mobile full-screen Artifact modal (md:hidden handled inside component) */}
        {isSidePanelOpen && forceOverlay && (
      <ArtifactPanel onClose={toggleSidePanel} isMobile={true} messages={currentArtifactMessages} />
        )}

      {/* Footer - positioned at bottom without affecting flex layout */}
      <div className="flex-shrink-0">
        <Footer />
      </div>

    </div>
  );
};

export default ChatPage;