import React, { useEffect, useState, useRef } from "react";
import ChatMessage from "./ChatMessage";
import LoadingSpinner from "../../utils/LoadingSpinner";
import ConnectionStatus from "./ConnectionStatus";
import { useNavigate, useParams } from "react-router-dom";
import UIToolRenderer from "../../core/ui/UIToolRenderer";

// UI Tool Renderer - handles workflow-agnostic UI tool events
// NOTE: Hooks must run unconditionally; define state first, then early-return.
const UIToolEventRenderer = React.memo(({ uiToolEvent, onResponse, submitInputRequest }) => {
  // Local completion indicator for inline components only
  const [completed, setCompleted] = React.useState(false);

  // Early return AFTER hook so hook order is stable
  if (!uiToolEvent || !uiToolEvent.ui_tool_id) {
    return null;
  }

  const handleResponse = async (resp) => {
    try {
      if (onResponse) {
        await onResponse(resp);
      }
    } finally {
      // Non-clickable "Completed" state for inline tools
      const displayMode = uiToolEvent.display || uiToolEvent.payload?.display || uiToolEvent.payload?.mode || 'inline';
      if (displayMode === 'inline') {
        setCompleted(true);
      }
    }
  };

  // Extract agent message from payload
  const agentMessage = uiToolEvent.payload?.agent_message || uiToolEvent.payload?.description;

  return (
    <div>
      {/* Agent message displayed above UI tool */}
      {agentMessage && (
        <div className="flex justify-start px-0 message-container mb-2">
          <div className="mt-1 agent-message message">
            <div className="flex flex-col">
              <div className="message-header">
                <span className="name-pill agent">
                  <span className="pill-avatar" aria-hidden>🤖</span> Agent
                </span>
              </div>
              <div className="message-body w-full flex">
                <div className="w-full">
                  {agentMessage}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* UI Tool Component */}
      <div className="my-4 p-4 border border-cyan-400/20 rounded-lg bg-gradient-to-r from-cyan-500/5 to-purple-500/5">
        {/* Inline-only completion chip */}
        {completed && ((uiToolEvent.display || uiToolEvent.payload?.display || uiToolEvent.payload?.mode || 'inline') === 'inline') && (
          <div className="mb-2">
            <span
              aria-label="Completed"
              className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-semibold rounded-full bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 select-none"
            >
              ✓ Completed
            </span>
          </div>
        )}
        <UIToolRenderer
          event={uiToolEvent}
          onResponse={handleResponse}
          submitInputRequest={submitInputRequest}
          className="ui-tool-in-chat"
        />
      </div>
    </div>
  );
});

const ModernChatInterface = ({ 
  messages, 
  onSendMessage, 
  loading, 
  onAgentAction, 
  onArtifactToggle,
  connectionStatus,
  transportType,
  workflowName,
  structuredOutputs = {},
  startupMode,
  initialMessageToUser,
  onRetry,
  tokensExhausted = false,
  submitInputRequest // F5: WebSocket input submission function
}) => {
  const [message, setMessage] = useState('');
  const [hasUserInteracted, setHasUserInteracted] = useState(false);
  const chatEndRef = useRef(null);
  const chatContainerRef = useRef(null);
  const [buttonText, setButtonText] = useState('SEND');
  const [isScrolledUp, setIsScrolledUp] = useState(false);
  const navigate = useNavigate();
  // const renderCountRef = useRef(0); // For debugging renders if needed
  
  // Optional debug: enable to trace renders
  // renderCountRef.current += 1;
  // console.debug(`ModernChatInterface render #${renderCountRef.current} with ${messages?.length || 0} messages`);
  // useEffect(() => {
  //   console.debug('ModernChatInterface received messages:', messages?.length || 0);
  // }, [messages]);
  
  // Chat flow UI tool event handling
  // This keeps the main chat interface clean and avoids hook violations.
  
  const scrollToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleScroll = () => {
    if (chatContainerRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = chatContainerRef.current;
      const isAtBottom = scrollHeight - scrollTop - clientHeight < 50;
      const hasScrolledUp = scrollTop > 100;
      setIsScrolledUp(!isAtBottom && hasScrolledUp);
    }
  };
  
  const { enterpriseId } = useParams();

  // Agent action handler - used by UI tool event responses
  const handleAgentAction = (action) => {
    console.log('Agent action received:', action);
    if (onAgentAction) {
      onAgentAction(action);
    }
  };

  const onSubmitClick = (event) => {
    event.preventDefault();
    if (buttonText === 'NEXT') {
      const currentEnterpriseId = enterpriseId || "68542c1109381de738222350";
      navigate("/chat/blueprint/" + currentEnterpriseId);
      return;
    }
    
    if (message.trim() === '') return;
    
    // Don't allow sending if tokens are exhausted
    if (tokensExhausted) {
      alert('💰 Unable to send message - your tokens have been exhausted. Please upgrade your plan to continue.');
      return;
    }
    
    const newMessage = { "sender": "user", "content": message };
    onSendMessage(newMessage);
    setMessage('');
  };

  const handleKeyPress = (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      onSubmitClick(event);
    }
  };

  useEffect(() => {
    const isCompleted = messages.find(x => x.VerificationChatStatus === 1);
    if (isCompleted !== undefined) {
      setButtonText('NEXT');
    }
  }, [messages, loading]);

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    const chatContainer = chatContainerRef.current;
    if (chatContainer) {
      chatContainer.addEventListener('scroll', handleScroll);
      handleScroll();
      
      return () => {
        chatContainer.removeEventListener('scroll', handleScroll);
      };
    }
  }, []);

  return (
    <div className="flex flex-col h-full rounded-2xl border border-cyan-400/30 md:overflow-hidden overflow-visible shadow-2xl bg-gradient-to-br from-white/5 to-cyan-500/5 backdrop-blur-sm cosmic-ui-module">
      {loading && <LoadingSpinner />}
      
      {/* Fixed Command Center Header - Never moves */}
  <div className="flex-shrink-0 px-3 py-1 md:px-4 md:py-2 border-b border-cyan-400/20 bg-gradient-to-r from-cyan-500/5 to-purple-500/5 backdrop-blur-xl shadow-lg rounded-lg md:rounded-xl mx-1 md:mx-2 mt-1 md:mt-2 mb-1">
        <div className="flex items-center justify-between">
          <div className="flex-1">
            <div className="cosmic-module-header text-sm md:text-base leading-tight">
              <span className="text-cyan-300">🚀</span>
              {workflowName ? workflowName.charAt(0).toUpperCase() + workflowName.slice(1) : 'Command Center Interface'}
            </div>
            {connectionStatus && (
              <div className="relative mt-1 w-full flex items-center gap-2 pr-24">
                <ConnectionStatus
                  status={connectionStatus}
                  transportType={transportType}
                  workflowName={workflowName}
                  onRetry={onRetry}
                  onArtifactToggle={onArtifactToggle}
                  className="connection-status-compact connection-status-tight-mobile text-xs"
                />
                {/* Mobile-only artifact button rendered as a separate, prominent control, absolutely positioned so it doesn't add height */}
                {onArtifactToggle && (
                  <button
                    onClick={onArtifactToggle}
                    className="md:hidden absolute right-1 top-[calc(50%-18px)] -translate-y-1/2 w-14 h-14 rounded-2xl border bg-gradient-to-r from-cyan-500/15 to-purple-500/15 backdrop-blur-sm artifact-hover-glow artifact-cta flex items-center justify-center transition-all duration-300 z-10"
                    title="Artifact Canvas"
                    aria-label="Open Artifact Canvas"
                  >
                    <img 
                      src="/mozaik_logo.svg" 
                      className="w-8 h-8 opacity-95 -mt-0.5" 
                      alt="Artifact"
                    />
                  </button>
                )}
              </div>
            )}
            {/* Initial Message - only show for UserDriven workflows and if message exists */}
            {startupMode === 'UserDriven' && initialMessageToUser && (
              <div className="mt-2 flex justify-center">
                <div className="relative px-3 py-1.5 rounded-lg bg-gradient-to-r from-fuchsia-500/20 to-purple-500/20 border border-fuchsia-500/30 flex items-center justify-center space-x-2 backdrop-blur-sm max-w-md">
                  <div className="absolute inset-0 bg-gradient-to-r from-fuchsia-500/10 to-purple-500/10 rounded-lg blur-sm"></div>
                  {/* Animated pulse dot - aligned to left */}
                  <div className="relative w-2 h-2 bg-fuchsia-400 rounded-full animate-pulse shadow-sm shadow-fuchsia-400/50 flex-shrink-0"></div>
                  <span className="relative text-fuchsia-300 text-xs font-semibold tracking-wide oxanium text-center">
                    {initialMessageToUser}
                  </span>
                </div>
              </div>
            )}
          </div>
          
          {/* Right side: Artifact Canvas Toggle Button and Connection Status */}
          <div className="flex flex-col items-end gap-2">
            {/* Artifact Canvas Toggle Button */}
            {onArtifactToggle && (
              <>
                {/* 
                  ARTIFACT TRIGGER LOGIC:
                  The button below manually triggers the artifact panel visibility via the `onArtifactToggle` prop,
                  which is connected to the `toggleSidePanel` function in `ChatPage.js`.

                  FUTURE ENHANCEMENT:
                  To make the artifact panel appear automatically based on an agent's output,
                  you would call the `onArtifactToggle` function programmatically. This could be done
                  by listening for a specific type of agent message in `ChatPage.js` and then
                  calling `toggleSidePanel()` when that message is received. This is the central
                  point for controlling the artifact panel's state.
                */}
                <button
                  onClick={onArtifactToggle}
                  className="hidden md:block group relative p-3 rounded-lg bg-gradient-to-r from-cyan-500/10 to-purple-500/10 border transition-all duration-300 backdrop-blur-sm artifact-hover-glow artifact-cta"
                  title="Toggle Artifact Canvas"
                >
                  <img 
                    src="/mozaik_logo.svg" 
                    className="w-10 h-10 opacity-70 group-hover:opacity-100 transition-all duration-300 group-hover:scale-105" 
                    alt="Artifact Canvas" 
                  />
                  <div className="absolute inset-0 bg-cyan-400/10 rounded-lg blur opacity-0 group-hover:opacity-100 transition-opacity duration-300 -z-10"></div>
                </button>
              </>
            )}
          </div>
        </div>
      </div>
      
    {/* Chat Messages Area - ONLY THIS SCROLLS */}
    <div className="flex-1 relative overflow-hidden" role="log" aria-live="polite" aria-relevant="additions">
        {/* Dim the galaxy background slightly for readability across the entire scroll area */}
        <div className="absolute inset-0 pointer-events-none bg-[rgba(0,0,0,0.45)] z-0" />
        <div 
          ref={chatContainerRef}
  className="absolute inset-0 overflow-y-auto px-2 py-2 md:p-6 space-y-3 md:space-y-4 my-scroll1 z-10"
        >
        <div className="relative">
      {/* Messages render below */}
          {(() => {
            // Determine the last chat index with a primary content message
            let lastContentIndex = -1;
            if (Array.isArray(messages)) {
              messages.forEach((m, i) => {
                if (m && m.content && !m.isTokenMessage && !m.isWarningMessage) {
                  lastContentIndex = i;
                }
              });
            }

            return messages?.map((chat, index) => {
            // console.debug('Rendering message', index, chat?.id);
            if (!chat) {
              // console.warn(`Message at index ${index} is null/undefined`);
              return null;
            }
            
            // annotate message with workflow mapping if missing
            const isStructuredCapable = typeof chat.isStructuredCapable === 'boolean' 
              ? chat.isStructuredCapable 
              : !!(chat.agentName && structuredOutputs[chat.agentName]);

            try {
              if (['1','true','on','yes'].includes((localStorage.getItem('mozaiks.debug_render')||'').toLowerCase())) {
                console.log('[RENDER] ChatMessage', {
                  index,
                  id: chat.id,
                  agent: chat.agentName,
                  visual: chat.isVisual,
                  structured: isStructuredCapable,
                  streaming: chat.isStreaming,
                  preview: (chat.content||'').slice(0,80)
                });
              }
            } catch {}

            return (
              <div key={index}>
                <ChatMessage
                  message={chat.content}
                  message_from={chat.sender}
                  agentName={chat.agentName}
                  isTokenMessage={chat.isTokenMessage}
                  isWarningMessage={chat.isWarningMessage}
                  isLatest={index === lastContentIndex}
                  isStructuredCapable={isStructuredCapable}
                  structuredOutput={chat.structuredOutput}
                  structuredSchema={chat.structuredSchema}
                />
                
                {/* Render UI Tool Events */}
                {chat.uiToolEvent && (
                  <UIToolEventRenderer 
                    uiToolEvent={chat.uiToolEvent}
                    submitInputRequest={submitInputRequest}
                    onResponse={(response) => {
                      // console.debug('UI tool response from chat');
                      // Use the handleAgentAction function to process the response
                      handleAgentAction({
                        type: 'ui_tool_response',
                        ui_tool_id: chat.uiToolEvent.ui_tool_id,
                        eventId: chat.uiToolEvent.eventId, // Include eventId for proper tracking
                        response: response
                      });
                    }}
                  />
                )}
              </div>
            );
            });
          })()}
          {/* Typing indicator slot (rendered when loading without messages updating) */}
          {loading && (
            <div className="flex justify-start px-0 message-container">
              <div className="agent-message message">
                <div className="flex items-center gap-2">
                  <span className="typing-dot" />
                  <span className="typing-dot delay-150" />
                  <span className="typing-dot delay-300" />
                </div>
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>
        </div>

        {/* Jump to Present Button - Positioned over the messages area */}
        {isScrolledUp && (
      <div className="absolute bottom-6 left-1/2 transform -translate-x-1/2 z-10">
            <button
              onClick={scrollToBottom}
        className="jump-present"
            >
              Jump to Present
            </button>
          </div>
        )}
      </div>

  {/* Fixed Transmission Input Area - Never moves */}
            <div className={`flex-shrink-0 p-1.5 md:p-3 border-t border-cyan-400/20 bg-gradient-to-r from-cyan-500/5 to-purple-500/5 backdrop-blur-xl shadow-lg transition-all duration-500 transmission-input-tight`}> 
        <form onSubmit={onSubmitClick} className="flex gap-3 flex-row items-center">
          <div className="flex-1 relative min-w-0 flex items-center">
            <textarea
              value={message}
              onChange={(e) => {
                setMessage(e.target.value);
                if (!hasUserInteracted) setHasUserInteracted(true);
                // Auto-resize textarea
                e.target.style.height = 'auto';
                e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px';
              }}
              onKeyPress={handleKeyPress}
              onFocus={() => setHasUserInteracted(true)}
              placeholder={tokensExhausted ? "Tokens exhausted - please upgrade to continue..." : "Transmit your message..."}
              disabled={buttonText === 'NEXT' || tokensExhausted}
              rows={1}
              className={`w-full bg-white/10 border-2 rounded-xl px-3 py-2 mt-0.5 text-cyan-50 placeholder-cyan-400/80 focus:outline-none resize-none transition-all duration-300 transmission-typing-font min-h-[40px] max-h-[120px] my-scroll1 backdrop-blur-sm ${
                hasUserInteracted 
                  ? 'border-cyan-400/50 focus:border-cyan-400/80 focus:bg-white/15 focus:shadow-[0_0_25px_rgba(51,240,250,0.4)]' 
                  : 'border-cyan-400/30 focus:border-cyan-400/70 focus:bg-white/15 focus:shadow-[0_0_30px_rgba(51,240,250,0.5)] shadow-[0_0_15px_rgba(51,240,250,0.2)]'
              }`}
              style={{ 
                height: '40px',
                overflowY: message.split('\n').length > 2 || message.length > 100 ? 'auto' : 'hidden'
              }}
            />
            {!hasUserInteracted && (
              <div className="absolute -top-1 -right-1 md:-top-2 md:-right-2 input-prompt-ping rounded-full subtle-ping" aria-hidden="true"></div>
            )}
          </div>
          
          {/* Command Button - icon-only for simplicity */}
          <button
            type="submit"
            disabled={!message.trim() || tokensExhausted}
            className={`
              px-2 py-1.5 rounded-md transition-all duration-300 min-w-[40px] w-auto h-9 oxanium font-bold text-[13px] flex items-center justify-center letter-spacing-wide border-2
              ${(!message.trim() || tokensExhausted)
                ? 'bg-gray-800/50 text-gray-400 cursor-not-allowed border-gray-600/50' 
                : 'bg-gradient-to-r from-cyan-500/80 to-blue-500/80 hover:from-cyan-400/90 hover:to-blue-400/90 text-white border-cyan-400/50 hover:border-cyan-300/70 shadow-sm shadow-cyan-500/10 hover:shadow-cyan-400/20 hover:scale-105 active:scale-95'
              }
            `}
          >
            {tokensExhausted ? (
              <span className="text-lg" aria-label="Upgrade required" role="img">💰</span>
            ) : buttonText === 'NEXT' ? (
              <span className="text-lg" aria-label="Launch" role="img">🚀</span>
            ) : (
              <span className="text-lg" aria-label="Transmit" role="img">📡</span>
            )}
          </button>
        </form>
      </div>

  {/* Mobile artifact button now lives in ConnectionStatus row */}
    </div>
  );
};

export default ModernChatInterface;
