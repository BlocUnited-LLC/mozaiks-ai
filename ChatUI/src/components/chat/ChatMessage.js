import React from "react";
import { marked } from "marked";
import DOMPurify from "dompurify";

// Local debug flag helper (duplicated intentionally to avoid cross-file import churn)
const debugFlag = (k) => { try { return ['1','true','on','yes'].includes((localStorage.getItem(k)||'').toLowerCase()); } catch { return false; } };

function ChatMessage({ message, message_from, agentName, isTokenMessage, isWarningMessage, isLatest = false, isStructuredCapable = false, structuredOutput = null, structuredSchema = null }) {
  // No local state needed: always show pretty structured output
  
  // Debug (disabled by default): uncomment to trace renders
  if (debugFlag('mozaiks.debug_render')) {
    try {
      console.log('[RENDER] ChatMessage component', {
        from: message_from,
        agent: agentName,
        len: (message||'').length,
        structured: isStructuredCapable,
        latest: isLatest
      });
    } catch {}
  }

  // Structured output detection – strict: only use explicit structuredOutput prop
  const detectStructuredOutput = (text) => {
    if (structuredOutput && typeof structuredOutput === 'object') {
      return { type: 'json', data: structuredOutput, raw: JSON.stringify(structuredOutput), textBefore: '', textAfter: '' };
    }
    return null; // Do not attempt heuristic parsing
  };

  const renderStructuredData = (structuredData) => {
    if (!structuredData) return null;

    // Order fields using structuredSchema if provided (object of field -> typeName)
    const root = structuredData.data || {};
    const schemaOrder = structuredSchema ? Object.keys(structuredSchema) : Object.keys(root);

    const renderPrimitive = (val) => <span className="text-emerald-300">{String(val)}</span>;

    const renderAny = (val, depth = 0) => {
      if (depth > 4) return <span className="text-gray-500">…</span>;
      if (val === null) return <span className="text-gray-400">null</span>;
      if (Array.isArray(val)) {
        if (!val.length) return <span className="text-gray-400">[]</span>;
        return (
          <div className="flex flex-col gap-1 mt-1">
            {val.slice(0, 25).map((item, i) => (
              <div key={i} className="pl-2 border-l border-gray-600/50 text-xs">
                <span className="text-blue-300">[{i}]</span> {renderAny(item, depth + 1)}
              </div>
            ))}
            {val.length > 25 && <span className="text-gray-500 text-xs">… {val.length - 25} more</span>}
          </div>
        );
      }
      if (typeof val === 'object') {
        const entries = Object.entries(val);
        if (!entries.length) return <span className="text-gray-400">{{}}</span>;
        return (
          <div className="flex flex-col gap-1 mt-1">
            {entries.slice(0, 50).map(([k, v]) => (
              <div key={k} className="pl-2 border-l border-gray-600/50">
                <span className="text-purple-300 mr-1 text-xs font-medium">{k}:</span>
                <span className="text-xs">{renderAny(v, depth + 1)}</span>
              </div>
            ))}
            {entries.length > 50 && <span className="text-gray-500 text-xs">… {entries.length - 50} more</span>}
          </div>
        );
      }
      return renderPrimitive(val);
    };

    return (
      <div className="mt-3 rounded-md border border-gray-600/60 bg-gray-800/40 overflow-hidden">
        <div className="px-3 py-2 bg-gray-800/60 border-b border-gray-600/40 flex items-center gap-2">
          <span className="text-xs text-blue-300 font-mono tracking-wide">STRUCTURED OUTPUT</span>
          {structuredSchema && (
            <span className="text-[10px] text-gray-400 font-mono">{schemaOrder.length} fields</span>
          )}
        </div>
        <div className="p-3 flex flex-col gap-2">
          {schemaOrder.map((field) => {
            if (!(field in root)) return null;
            const value = root[field];
            const typeName = structuredSchema ? structuredSchema[field] : typeof value;
            return (
              <div key={field} className="bg-gray-900/30 rounded-md px-2 py-1">
                <div className="flex flex-col w-full">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-xs font-semibold text-purple-200 font-mono">{field}</span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-gray-700/60 text-gray-300 font-mono">{typeName}</span>
                  </div>
                  <div className="text-[11px] leading-4 text-gray-200 break-words">
                    {renderAny(value)}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  };
 
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

  // Main message content with structured output support
  const renderMessageContent = (text) => {
    const structuredData = detectStructuredOutput(text);
    if (structuredData) {
      return (
        <div className="w-full">
          {structuredData.textBefore && (
            <div className="mb-3" dangerouslySetInnerHTML={renderMarkdown(structuredData.textBefore)} />
          )}
          {renderStructuredData(structuredData)}
          {structuredData.textAfter && (
            <div className="mt-3" dangerouslySetInnerHTML={renderMarkdown(structuredData.textAfter)} />
          )}
        </div>
      );
    }
    return <div className="w-full" dangerouslySetInnerHTML={renderMarkdown(text)} />;
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
                  {renderMessageContent(message)}
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
                  {renderMessageContent(message)}
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
                  {renderMessageContent(message)}
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
