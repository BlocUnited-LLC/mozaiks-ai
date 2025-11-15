import React from 'react';
import { useNavigate } from 'react-router-dom';

/**
 * PersistentChatWidget - Minimized chat window in bottom-left corner (20% of screen height)
 * 
 * Shows when user is on Discovery/Workflows page.
 * Click to navigate back to full chat and restore previous layout state.
 */
const PersistentChatWidget = ({ 
  chatId, 
  workflowName
}) => {
  const navigate = useNavigate();

  const navigateToChat = () => {
    // Navigate back to chat page - layout will be restored by App.js
    navigate('/chat');
  };

  // Minimized chat window (20% screen height) in bottom-left corner
  return (
    <div 
      className="fixed bottom-0 left-0 z-50 w-80 bg-gradient-to-br from-gray-900/95 via-slate-900/95 to-black/95 backdrop-blur-xl border-t border-r border-[rgba(var(--color-primary-light-rgb),0.3)] rounded-tr-2xl shadow-2xl overflow-hidden"
      style={{ height: '20vh', minHeight: '150px' }}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-gradient-to-r from-[rgba(var(--color-primary-rgb),0.2)] to-[rgba(var(--color-secondary-rgb),0.2)] border-b border-[rgba(var(--color-primary-light-rgb),0.2)]">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-[var(--color-primary)] to-[var(--color-secondary)] flex items-center justify-center p-1.5 border border-[var(--color-primary-light)]/30">
            <img 
              src="/mozaik_logo.svg" 
              alt="MozaiksAI" 
              className="w-full h-full"
              onError={(e) => {
                e.target.onerror = null;
                e.target.src = "/mozaik.png";
              }}
            />
          </div>
          <div>
            <h3 className="text-sm font-bold text-white oxanium">MozaiksAI</h3>
            {workflowName && (
              <p className="text-xs text-[var(--color-primary-light)]/70 oxanium">{workflowName}</p>
            )}
          </div>
        </div>
        
        <button
          onClick={navigateToChat}
          className="w-8 h-8 rounded-lg bg-[var(--color-primary)]/20 hover:bg-[var(--color-primary)]/40 transition-all flex items-center justify-center group border border-[var(--color-primary-light)]/30"
          title="Expand Chat"
        >
          <svg className="w-4 h-4 text-[var(--color-primary-light)] group-hover:scale-110 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
          </svg>
        </button>
      </div>

      {/* Minimized chat preview */}
      <div className="p-4 h-full flex flex-col justify-center items-center text-center">
        <div className="text-gray-400 text-sm mb-2">
          {chatId ? (
            <>
              <svg className="w-6 h-6 mx-auto mb-2 text-[var(--color-primary-light)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
              <p className="oxanium">Active chat session</p>
              <p className="text-xs text-gray-500 mt-1 truncate px-2">{chatId}</p>
            </>
          ) : (
            <>
              <svg className="w-6 h-6 mx-auto mb-2 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
              </svg>
              <p className="oxanium">No active chat</p>
            </>
          )}
        </div>
        <button
          onClick={navigateToChat}
          className="mt-2 px-4 py-2 bg-gradient-to-r from-[var(--color-primary)] to-[var(--color-secondary)] text-white text-xs rounded-lg hover:shadow-lg hover:shadow-[var(--color-primary)]/50 transition-all font-semibold oxanium"
        >
          Open Chat
        </button>
      </div>
    </div>
  );
};

export default PersistentChatWidget;
