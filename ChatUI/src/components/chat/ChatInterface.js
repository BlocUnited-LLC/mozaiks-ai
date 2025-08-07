import React, { useEffect, useState, useRef } from "react";
import ChatMessage from "./ChatMessage";
import LoadingSpinner from "../../utils/LoadingSpinner";
import ConnectionStatus from "./ConnectionStatus";
import { useNavigate, useParams } from "react-router-dom";
import UIToolRenderer from "../../core/ui/UIToolRenderer";

// UI Tool Renderer - handles workflow-agnostic UI tool events
const UIToolEventRenderer = React.memo(({ uiToolEvent, onResponse }) => {
  if (!uiToolEvent || !uiToolEvent.ui_tool_id) {
    return null;
  }

  console.log('🎯 Rendering UI tool event:', uiToolEvent.ui_tool_id);
  
  return (
    <div className="my-4 p-4 border border-cyan-400/20 rounded-lg bg-gradient-to-r from-cyan-500/5 to-purple-500/5">
      <UIToolRenderer 
        event={uiToolEvent}
        onResponse={onResponse}
        className="ui-tool-in-chat"
      />
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
  startupMode,
  initialMessageToUser,
  onRetry,
  tokensExhausted = false
}) => {
  const [message, setMessage] = useState('');
  const [hasUserInteracted, setHasUserInteracted] = useState(false);
  const chatEndRef = useRef(null);
  const chatContainerRef = useRef(null);
  const [buttonText, setButtonText] = useState('SEND');
  const [isScrolledUp, setIsScrolledUp] = useState(false);
  const navigate = useNavigate();
  const renderCountRef = useRef(0);
  
  // Increment render count and log every render
  renderCountRef.current += 1;
  console.log(`🔄 ModernChatInterface render #${renderCountRef.current} with ${messages?.length || 0} messages`);
  
  // Add logging for messages prop
  useEffect(() => {
    console.log('🖥️ ModernChatInterface received messages:');
    console.log('  Count:', messages?.length || 0);
    console.log('  Messages:', messages?.map(m => ({ id: m.id, sender: m.sender, content: m.content?.substring(0, 30) + '...' })) || []);
  }, [messages]);
  
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
    <div className="flex flex-col h-full rounded-2xl border border-cyan-400/30 overflow-hidden shadow-2xl bg-gradient-to-br from-white/5 to-cyan-500/5 backdrop-blur-sm cosmic-ui-module">
      {loading && <LoadingSpinner />}
      
      {/* Fixed Command Center Header - Never moves */}
      <div className="flex-shrink-0 px-4 py-3 border-b border-cyan-400/20 bg-gradient-to-r from-cyan-500/5 to-purple-500/5 backdrop-blur-xl shadow-lg rounded-2xl mx-2 mt-2 mb-1">
        <div className="flex items-center justify-between">
          <div className="flex-1">
            <div className="cosmic-module-header">
              <span className="text-cyan-300">🚀</span>
              {workflowName ? workflowName.charAt(0).toUpperCase() + workflowName.slice(1) : 'Command Center Interface'}
            </div>
            {/* Connection Status under workflow title */}
            {connectionStatus && (
              <div className="mt-1 w-fit">
                <ConnectionStatus
                  status={connectionStatus}
                  transportType={transportType}
                  workflowName={workflowName}
                  onRetry={onRetry}
                  className="text-xs"
                />
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
                  className="group relative p-3 rounded-lg bg-gradient-to-r from-cyan-500/10 to-purple-500/10 border border-cyan-400/20 hover:border-cyan-400/40 transition-all duration-300 backdrop-blur-sm"
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
      <div className="flex-1 relative overflow-hidden">
        <div 
          ref={chatContainerRef}
          className="absolute inset-0 overflow-y-auto p-6 space-y-4 my-scroll1"
        >
          {messages?.map((chat, index) => {
            console.log(`🎨 Rendering message ${index}:`, { id: chat?.id, sender: chat?.sender, content: chat?.content?.substring(0, 50) + '...' });
            if (!chat) {
              console.warn(`⚠️ Message at index ${index} is null/undefined`);
              return null;
            }
            
            return (
              <div key={index}>
                <ChatMessage
                  message={chat.content}
                  message_from={chat.sender}
                  agentName={chat.agentName}
                  isTokenMessage={chat.isTokenMessage}
                  isWarningMessage={chat.isWarningMessage}
                />
                
                {/* Render UI Tool Events */}
                {chat.uiToolEvent && (
                  <UIToolEventRenderer 
                    uiToolEvent={chat.uiToolEvent}
                    onResponse={(response) => {
                      console.log('📤 UI tool response from chat:', response);
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
          })}
          <div ref={chatEndRef} />
        </div>

        {/* Jump to Present Button - Positioned over the messages area */}
        {isScrolledUp && (
          <div className="absolute bottom-6 left-1/2 transform -translate-x-1/2 z-10">
            <button
              onClick={scrollToBottom}
              className="flex items-center space-x-2 px-4 py-2 bg-cyan-500/95 hover:bg-cyan-400/95 text-white rounded-full shadow-lg hover:shadow-cyan-500/50 transition-all duration-300 techfont font-bold text-sm border border-cyan-400/50 backdrop-blur-sm"
            >
              <span>📩 You're viewing older messages</span>
              <span className="bg-white/20 px-2 py-1 rounded-full text-xs">Jump to Present</span>
            </button>
          </div>
        )}
      </div>

      {/* Fixed Transmission Input Area - Never moves */}
      <div className={`flex-shrink-0 p-4 border-t border-cyan-400/20 bg-gradient-to-r from-cyan-500/5 to-purple-500/5 backdrop-blur-xl shadow-lg transition-all duration-500 ${!hasUserInteracted ? 'ring-2 ring-cyan-400/30 animate-pulse' : ''}`}>
        <form onSubmit={onSubmitClick} className="flex items-center gap-3">
          <div className="flex-1 relative">
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
              placeholder={tokensExhausted ? "Tokens exhausted - please upgrade to continue..." : "Type transmission..."}
              disabled={buttonText === 'NEXT' || tokensExhausted}
              rows={1}
              className={`w-full bg-white/10 border-2 rounded-2xl px-4 py-3 text-cyan-50 placeholder-cyan-400/80 focus:outline-none resize-none transition-all duration-300 oxanium min-h-[48px] max-h-[120px] my-scroll1 backdrop-blur-sm ${
                hasUserInteracted 
                  ? 'border-cyan-400/50 focus:border-cyan-400/80 focus:bg-white/15 focus:shadow-[0_0_25px_rgba(51,240,250,0.4)]' 
                  : 'border-cyan-400/30 focus:border-cyan-400/70 focus:bg-white/15 focus:shadow-[0_0_30px_rgba(51,240,250,0.5)] shadow-[0_0_15px_rgba(51,240,250,0.2)]'
              }`}
              style={{ 
                height: '48px',
                overflowY: message.split('\n').length > 2 || message.length > 100 ? 'auto' : 'hidden'
              }}
            />
            {!hasUserInteracted && (
              <div className="absolute -top-2 -right-2 w-3 h-3 bg-cyan-400 rounded-full animate-ping"></div>
            )}
          </div>
          
          {/* Command Button */}
          <button
            type="submit"
            disabled={!message.trim() || tokensExhausted}
            className={`
              px-6 py-3 rounded-xl transition-all duration-300 min-w-[100px] h-12 oxanium uppercase font-bold text-[14px] flex items-center justify-center letter-spacing-wide border-2
              ${(!message.trim() || tokensExhausted)
                ? 'bg-gray-800/50 text-gray-400 cursor-not-allowed border-gray-600/50' 
                : 'bg-gradient-to-r from-cyan-500/80 to-blue-500/80 hover:from-cyan-400/90 hover:to-blue-400/90 text-white border-cyan-400/50 hover:border-cyan-300/70 shadow-lg shadow-cyan-500/20 hover:shadow-cyan-400/30 hover:scale-105 active:scale-95'
              }
            `}
          >
            {tokensExhausted ? '💰 UPGRADE' : (buttonText === 'NEXT' ? '🚀 LAUNCH' : '📡 TRANSMIT')}
          </button>
        </form>
      </div>
    </div>
  );
};

export default ModernChatInterface;
