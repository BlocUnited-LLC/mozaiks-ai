import React from 'react';
import UIToolRenderer from '../../core/ui/UIToolRenderer';

const ArtifactPanel = ({ onClose, isMobile = false, messages = [] }) => {
  const containerClasses = isMobile 
    ? "fixed inset-0 z-50" 
    : "flex flex-col w-full transition-all duration-500 ease-in-out";
    
  const contentClasses = isMobile
    ? "relative w-full h-full flex flex-col"
  : "flex flex-col h-full rounded-2xl border border-[rgba(var(--color-primary-light-rgb),0.3)] overflow-hidden shadow-2xl bg-gradient-to-br from-white/5 to-[rgba(var(--color-primary-rgb),0.05)] backdrop-blur-sm cosmic-ui-module artifact-panel animate-in slide-in-from-right";

  return (
    <div className={containerClasses}>
      {/* Mobile backdrop */}
      {isMobile && (
        <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
      )}

      {/* Panel Content */}
      <div className={contentClasses}>
        {/* Artifact Header */}
  <div className="flex-shrink-0 px-4 py-3 border-b border-[rgba(var(--color-primary-light-rgb),0.2)] bg-gradient-to-r from-[rgba(var(--color-primary-rgb),0.05)] to-[rgba(var(--color-secondary-rgb),0.05)] backdrop-blur-xl shadow-lg rounded-2xl mx-2 mt-2 mb-1 min-h-[80px]">
          <div className="flex items-center justify-between h-full">
            <div className="flex-1">
              <div className="cosmic-module-header">
                <span className="text-[var(--color-primary-light)]">🎨</span>
                Artifact Canvas
              </div>
            </div>
            <div className="flex flex-col items-end gap-2">
              <button 
                onClick={onClose}
                className="group relative p-3 rounded-lg bg-gradient-to-r from-[rgba(var(--color-primary-rgb),0.1)] to-[rgba(var(--color-secondary-rgb),0.1)] border border-[rgba(var(--color-primary-light-rgb),0.2)] hover:border-[rgba(var(--color-primary-light-rgb),0.4)] transition-all duration-300 backdrop-blur-sm"
                title={`Close${isMobile ? '' : ' Artifact Canvas'}`}
              >
                <svg className="w-5 h-5 group-hover:rotate-90 transition-transform duration-300 text-[var(--color-text-primary)] text-white group-hover:text-[var(--color-primary-light)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
                <div className="absolute inset-0 bg-[rgba(var(--color-primary-light-rgb),0.1)] rounded-lg blur opacity-0 group-hover:opacity-100 transition-opacity duration-300 -z-10"></div>
              </button>
            </div>
          </div>
        </div>
        
        {/* Artifact Content Area - ONLY THIS SCROLLS */}
        <div className="flex-1 relative overflow-hidden">
          <div className="absolute inset-0 overflow-y-auto p-6 space-y-4 my-scroll1">
            {/* If no structured messages, show welcome state */}
            {(!messages || messages.length === 0) ? (
              <div className="text-center space-y-6 mt-8">
                <div className="flex items-center justify-center h-full min-h-[400px]">
                  <div className="w-32 h-32 bg-gradient-to-br from-[rgba(var(--color-primary-rgb),0.1)] to-[rgba(var(--color-secondary-rgb),0.1)] rounded-2xl border border-[rgba(var(--color-primary-light-rgb),0.3)] flex items-center justify-center backdrop-blur-sm shadow-lg">
                    <img 
                      src="/mozaik_logo.svg" 
                      alt="Mozaik Logo" 
                      className="w-16 h-16 opacity-60"
                    />
                  </div>
                </div>
                <div className="text-sm text-gray-300">No structured artifacts yet. Agent structured outputs will appear here.</div>
              </div>
            ) : (
              <div className="space-y-6">
                {messages.map((m, idx) => {
                  // If message has uiToolEvent, render the actual UI component (OUTER BOX REMOVED PER REQUEST)
                  if (m.uiToolEvent && m.uiToolEvent.ui_tool_id) {
                    return (
                      <div key={m.id || idx} className="artifact-tool-wrapper">
                        <UIToolRenderer
                          event={m.uiToolEvent}
                          onResponse={m.uiToolEvent.onResponse}
                          className="artifact-ui-tool"
                        />
                      </div>
                    );
                  }
                  
                  // Fallback: render as structured JSON (legacy behavior)
                  let parsed = null;
                  try {
                    const jsonMatch = (typeof m.content === 'string') ? m.content.match(/\{[\s\S]*\}/) : null;
                    if (jsonMatch) parsed = JSON.parse(jsonMatch[0]);
                    else if (typeof m.content === 'object') parsed = m.content;
                  } catch (e) { parsed = null; }

                  return (
                    <div key={m.id || idx} className="bg-black/20 border border-gray-700 rounded-lg p-4">
                      <div className="flex items-start justify-between mb-2">
                        <div>
                          <div className="text-xs text-[var(--color-primary-light)]">{m.agentName || 'Agent'}</div>
                          <div className="text-sm text-gray-200 font-semibold">Structured Output</div>
                        </div>
                        <div className="flex items-center gap-2">
                          <button onClick={() => { if (navigator.clipboard && parsed) { navigator.clipboard.writeText(JSON.stringify(parsed, null, 2)); } }} className="text-xs px-2 py-1 bg-gray-800/50 rounded text-gray-200">Copy JSON</button>
                        </div>
                      </div>
                      {parsed ? (
                        <pre className="text-xs text-gray-300 bg-black/30 p-3 rounded overflow-auto max-h-72">{JSON.stringify(parsed, null, 2)}</pre>
                      ) : (
                        <div className="text-sm text-gray-400">Could not parse structured output for this artifact.</div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ArtifactPanel;