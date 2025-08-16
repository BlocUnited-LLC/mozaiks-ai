import React from "react";
import { marked } from "marked";
import DOMPurify from "dompurify";

function ChatMessage({ message, message_from, agentName, isTokenMessage, isWarningMessage, isLatest = false }) {
  // Debug (disabled by default): uncomment to trace renders
  // console.debug('ChatMessage render:', { message: message?.substring(0, 50) + '...', message_from, agentName, hasMessage: !!message, isTokenMessage, isWarningMessage });
 
  // Special styling for token and warning messages
  const getSystemMessageStyles = () => {
    if (isTokenMessage) {
      return {
        container: "bg-gradient-to-r from-red-500/20 to-orange-500/20 border border-red-400/40",
        text: "text-red-200",
        icon: "💰"
      };
    }
    if (isWarningMessage) {
      return {
        container: "bg-gradient-to-r from-yellow-500/20 to-orange-500/20 border border-yellow-400/40",
        text: "text-yellow-200",
        icon: "⚠️"
      };
    }
    return null;
  };

  const systemStyles = getSystemMessageStyles();

  const renderMarkdown = (text) => {
    try {
      const html = marked.parse(String(text || ""), { breaks: true });
      return { __html: DOMPurify.sanitize(html) };
    } catch {
      return { __html: DOMPurify.sanitize(String(text || "")) };
    }
  };

  return (
    <>
  {message_from === "user" ? (
  <div className="flex justify-end px-0 message-container">
          <div
            className={`mt-1 user-message message ${isLatest ? 'latest' : ''}`}
          >
            <div className="flex flex-col">
              {/* In-bubble header for name (right-aligned for user) */}
              <div className="message-header justify-end">
                <span className="name-pill user"><span className="pill-avatar" aria-hidden>🧑</span> You</span>
              </div>
              {message && (
                <div className="message-body w-full flex justify-end text-right">
                  <div className="w-full" dangerouslySetInnerHTML={renderMarkdown(message)} />
                </div>
              )}
            </div>
          </div>
        </div>
      ) : systemStyles ? (
        // Special styling for system messages (token/warning)
  <div className="flex justify-center mr-3 message-container">
          <div className={`md:rounded-[10px] rounded-[10px] w-4/5 mt-1 leading-4 techfont px-[12px] py-[6px] ${systemStyles.container}`}>
            <div className="flex flex-col">
              <div className={`text-xs mb-1 opacity-75 flex items-center gap-2 ${systemStyles.text}`}>
                <span>{systemStyles.icon}</span>
                <span>System Notice</span>
              </div>
              {message && (
                <div className={`sm:w-full flex pr-2 oxanium md:text-[16px] text-[10px] font-bold ${systemStyles.text}`}>
                  <div className="w-full" dangerouslySetInnerHTML={renderMarkdown(message)} />
                </div>
              )}
            </div>
          </div>
        </div>
    ) : (
  <div className="flex justify-start px-0 message-container">
          {message && (
            <div
              className={`mt-1 agent-message message ${isLatest ? 'latest' : ''}`}
            >
              <div className="flex flex-col">
                {/* In-bubble header for name (left-aligned for agent) */}
                <div className="message-header">
                  <span className="name-pill agent"><span className="pill-avatar" aria-hidden>🤖</span> {agentName || 'Agent'}</span>
                </div>
                <div className="message-body w-full flex">
                  <div className="w-full" dangerouslySetInnerHTML={renderMarkdown(message)} />
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </>
  );
}
export default ChatMessage;
