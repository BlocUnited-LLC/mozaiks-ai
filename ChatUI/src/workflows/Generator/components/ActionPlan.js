// ==============================================================================
// FILE: ChatUI/src/workflows/generator/components/ActionPlan.js
// DESCRIPTION: Generator workflow component for workflow visualization with AG2 integration
// ==============================================================================

import React, { useState, useEffect, useRef } from 'react';
import { FileText, Zap, Settings, AlertCircle, ExternalLink, Eye } from 'lucide-react';
import { createToolsLogger } from '../../../core/toolsLogger';

/**
 * ActionPlan - Production AG2 component for workflow visualization
 * 
 * Displays workflow configuration with rich agent context feedback within the AG2 workflow system.
 * Fully integrated with chat.* event protocol and provides detailed completion signals.
 */
const ActionPlan = ({ 
  payload = {},
  onResponse,
  ui_tool_id,
  eventId,
  workflowName,
  componentId = "ActionPlan"
}) => {
  // Debug logging to understand what we're receiving
  console.log('🎯 ActionPlan: Received props:', {
    payload: payload,
    payloadType: typeof payload,
    payloadIsNull: payload === null,
    onResponse: typeof onResponse,
    ui_tool_id,
    eventId,
    workflowName
  });

  // Ensure payload is always an object
  const safePayload = payload || {};
  
  // DEV NOTE: This component receives the agent's contextual message via the
  // `payload.description` prop. This is the standardized convention for all
  // dynamic UI components in this application.
  const config = {
    workflow_title: safePayload.workflow_title || "Generated Workflow",
    workflow_description: safePayload.workflow_description || "Workflow generated from agent configuration.",
    suggested_features: safePayload.suggested_features || [],
    mermaid_flow: safePayload.mermaid_flow || "sequenceDiagram\n  User->>System: start\n  System-->>User: done",
    third_party_integrations: safePayload.third_party_integrations || [],
    constraints: safePayload.constraints || [],
    description: safePayload.description || null
  };
  
  const agentMessageId = payload.agent_message_id;
  const tlog = createToolsLogger({ tool: ui_tool_id || componentId, eventId, workflowName, agentMessageId });
  const [actionStatus, setActionStatus] = useState({});

  const handleAction = async (action, data = {}) => {
    setActionStatus(prev => ({ ...prev, [action]: 'processing' }));
    
    try {
      tlog.event(action, 'start');
      // Enhanced response with rich agent feedback information
      const response = {
        status: 'success',
        action: action,
        data: {
          action,
          workflow_title: config.workflow_title,
          actionTime: new Date().toISOString(),
          ui_tool_id,
          eventId,
          workflowName,
          agent_message_id: agentMessageId,
          ...data
        },
        agentContext: { 
          action_completed: true, 
          workflow_viewed: true,
          action_type: action 
        }
      };

      // Call the response handler from event dispatcher
      if (onResponse) {
        await onResponse(response);
      }
      
      setActionStatus(prev => ({ ...prev, [action]: 'completed' }));
      
  tlog.event(action, 'done', { ok: true });
      
    } catch (error) {
  tlog.error(`${action} failed`, { error: error?.message });
      setActionStatus(prev => ({ ...prev, [action]: 'error' }));
      
      // Enhanced error response with context
      if (onResponse) {
        onResponse({
          status: 'error',
          action: action,
          error: error.message,
          data: { action, ui_tool_id, eventId, agent_message_id: agentMessageId },
          agentContext: { 
            action_completed: false, 
            workflow_viewed: true,
            action_type: action, 
            error: true 
          }
        });
      }
    }
  };

  const handleCancel = () => {
  tlog.event('cancel', 'start');
  if (onResponse) {
      onResponse({
        status: 'cancelled',
        action: 'cancel',
        data: { ui_tool_id, eventId, workflowName, agent_message_id: agentMessageId },
        agentContext: { 
          action_completed: false, 
          workflow_viewed: true,
          cancelled: true 
        }
      });
  }
  tlog.event('cancel', 'done');
  };

  // Mermaid diagram component
  const MermaidDiagram = ({ chart }) => {
    const mermaidRef = useRef(null);
  const scrollWrapperRef = useRef(null);
    const [isLoaded, setIsLoaded] = useState(false);
  const [needsScroll, setNeedsScroll] = useState(false);
  const [showHint, setShowHint] = useState(false);
  // Removed renderKey force-rerender logic (kept lean per best-practice request)

    useEffect(() => {
      if (!window.mermaid) {
        const script = document.createElement('script');
        script.src = 'https://cdnjs.cloudflare.com/ajax/libs/mermaid/10.6.1/mermaid.min.js';
        script.onload = () => {
          window.mermaid.initialize({ 
            startOnLoad: false,
            theme: 'dark',
            themeVariables: {
              primaryColor: '#06b6d4',
              primaryTextColor: '#ffffff',
              primaryBorderColor: '#0891b2',
              lineColor: '#6b7280',
              sectionBkgColor: '#1f2937',
              altSectionBkgColor: '#374151',
              gridColor: '#4b5563',
              secondaryColor: '#10b981',
              tertiaryColor: '#f59e0b'
            }
          });
          setIsLoaded(true);
        };
        document.head.appendChild(script);
      } else {
        setIsLoaded(true);
      }
    }, []);

    useEffect(() => {
      if (isLoaded && mermaidRef.current && chart) {
        const renderDiagram = async () => {
          try {
            // Defensive normalization: ensure flowchart direction is LR
              let normalized = (chart || '').toString();
              if (/^\s*sequenceDiagram/i.test(normalized)) {
                // strip advanced blocks
                normalized = normalized
                  .split('\n')
                  .filter(l => !/(alt|opt|loop|par|rect|critical)/i.test(l))
                  .join('\n');
              } else if (/^\s*flowchart\s+/i.test(normalized)) {
                // Convert basic flowchart nodes to a simple actor sequence
                const labels = [...normalized.matchAll(/\b([A-Za-z0-9_]+)\[[^\]]+\]/g)].map(m=>m[1]);
                const actors = labels.slice(0,4);
                if (actors.length < 2) actors.push('System');
                let uniq = [];
                actors.forEach(a=>{ if(!uniq.includes(a)) uniq.push(a); });
                const lines = ['sequenceDiagram'];
                for (let i=0;i<uniq.length-1;i++) lines.push(`  ${uniq[i]}->>${uniq[i+1]}: step ${i+1}`);
                if (uniq.length>1) lines.push(`  ${uniq[uniq.length-1]}-->>${uniq[0]}: result`);
                normalized = lines.join('\n');
              } else {
                normalized = 'sequenceDiagram\n  User->>System: step 1\n  System-->>User: result';
              }

            const { svg } = await window.mermaid.render('mermaid-diagram', normalized);
            mermaidRef.current.innerHTML = svg;
            // Post-process SVG to prevent auto shrinking (Mermaid sets max-width:100%)
            const svgEl = mermaidRef.current.querySelector('svg');
            if (svgEl) {
              // Preserve intrinsic width for scroll; remove responsive shrink
              svgEl.style.maxWidth = 'none';
              // If width attr exists, apply as explicit CSS width to retain size
              const wAttr = svgEl.getAttribute('width');
              if (wAttr && !svgEl.style.width) {
                // Ensure numeric values get px suffix
                svgEl.style.width = /px$|%/.test(wAttr) ? wAttr : `${wAttr}px`;
              }
              // Provide a min-height so container stays stable
              svgEl.style.minHeight = '160px';
            }
            // After render, determine if horizontal scroll is needed (mobile especially)
            requestAnimationFrame(() => {
              try {
                const wrapper = scrollWrapperRef.current;
                if (svgEl && wrapper) {
                  const intrinsicWidth = svgEl.scrollWidth; // after removing max-width constraint
                  const needs = intrinsicWidth > wrapper.clientWidth + 8; // small buffer
                  setNeedsScroll(needs);
                  setShowHint(needs && window.innerWidth < 768);
                }
              } catch (_) {}
            });
          } catch (error) {
            mermaidRef.current.innerHTML = `<div class="text-red-400 p-4 border border-red-600 rounded bg-red-900/20">Error rendering diagram: ${error.message}</div>`;
          }
        };
        renderDiagram();
      }
  }, [isLoaded, chart]);

    // Re-evaluate on window resize (mobile orientation changes) — lightweight refresh
    useEffect(() => {
      const onResize = () => {
        if (!mermaidRef.current || !scrollWrapperRef.current) return;
        const svgEl = mermaidRef.current.querySelector('svg');
        if (svgEl) {
          const needs = svgEl.scrollWidth > scrollWrapperRef.current.clientWidth + 8;
          setNeedsScroll(needs);
          setShowHint(needs && window.innerWidth < 768);
        }
      };
      window.addEventListener('resize', onResize);
      return () => window.removeEventListener('resize', onResize);
    }, []);

    return (
      <div className="bg-gray-800 border border-cyan-500/30 rounded-lg p-4">
        <h3 className="text-lg font-semibold mb-2 flex items-center text-cyan-400">
          <FileText className="mr-2 h-5 w-5" />
          Workflow Diagram
        </h3>
        {showHint && (
          <div className="text-xs text-cyan-300 mb-2 opacity-80 select-none">
            Swipe / drag horizontally to view full diagram
          </div>
        )}
        <div className="relative">
          {needsScroll && (
            <div className="pointer-events-none absolute top-0 left-0 h-full w-6 bg-gradient-to-r from-gray-800 to-transparent" />
          )}
          {needsScroll && (
            <div className="pointer-events-none absolute top-0 right-0 h-full w-6 bg-gradient-to-l from-gray-800 to-transparent" />
          )}
          <div
            ref={scrollWrapperRef}
            className={
              "relative w-full overflow-x-auto overflow-y-hidden" +
              " touch-pan-x" +
              (needsScroll ? " border border-cyan-600/30 rounded-md" : "")
            }
            style={{ WebkitOverflowScrolling: 'touch' }}
          >
            <div
              className="inline-block min-h-[200px] px-1 align-top"
              style={{ maxWidth: 'none' }}
            >
              <div ref={mermaidRef} className="inline-block">
                {!isLoaded && (
                  <div className="text-gray-400 p-8">Loading diagram...</div>
                )}
              </div>
            </div>
          </div>
        </div>
        {needsScroll && (
          <div className="mt-2 text-[10px] tracking-wide text-gray-400 flex items-center gap-1">
            <span className="inline-block bg-cyan-700/30 px-2 py-0.5 rounded">Scrollable</span>
            Diagram exceeds mobile width
          </div>
        )}
      </div>
    );
  };

  const FeatureCard = ({ feature }) => (
    <div className="bg-gradient-to-r from-blue-900/50 to-indigo-900/50 border border-blue-500/30 rounded-lg p-4">
      <h4 className="font-semibold text-blue-300 mb-2">{feature.feature_title}</h4>
      <p className="text-blue-200 text-sm">{feature.description}</p>
    </div>
  );

  const IntegrationCard = ({ integration }) => (
    <div className="bg-gradient-to-r from-green-900/50 to-emerald-900/50 border border-green-500/30 rounded-lg p-4">
      <h4 className="font-semibold text-green-300 mb-2 flex items-center">
        <ExternalLink className="mr-2 h-4 w-4" />
        {integration.technology_title}
      </h4>
      <p className="text-green-200 text-sm">{integration.description}</p>
    </div>
  );

  const ConstraintItem = ({ constraint }) => (
    <div className="bg-yellow-900/30 border border-yellow-500/30 rounded-lg p-3 flex items-start">
      <AlertCircle className="mr-2 h-4 w-4 text-yellow-400 mt-0.5 flex-shrink-0" />
      <span className="text-yellow-200 text-sm">{constraint}</span>
    </div>
  );

  const ActionButton = ({ action, icon: Icon, label, variant = "primary" }) => {
    const status = actionStatus[action];
    const baseClasses = "px-4 py-2 rounded transition-colors font-medium flex items-center gap-2";
    
    let classes = baseClasses;
    if (variant === "primary") {
      classes += status === 'processing' 
        ? " bg-yellow-600 text-white cursor-not-allowed" 
        : status === 'completed'
        ? " bg-green-600 text-white"
        : status === 'error'
        ? " bg-red-600 hover:bg-red-700 text-white"
        : " bg-cyan-600 hover:bg-cyan-700 text-white";
    } else {
      classes += " bg-gray-600 hover:bg-gray-700 text-white";
    }

    return (
      <button 
        className={classes}
        onClick={() => handleAction(action)}
        disabled={status === 'processing'}
      >
        <Icon className="h-4 w-4" />
        {status === 'processing' && '⏳ Processing...'}
        {status === 'completed' && '✓ Completed'}
        {status === 'error' && '🔄 Retry'}
        {!status && label}
      </button>
    );
  };

  return (
    <div className="workflow-visualizer bg-gray-900 border border-cyan-500/30 rounded-lg p-6" data-agent-message-id={agentMessageId || undefined}>
      {/* Header */}
      <div className="visualization-header flex justify-between items-start mb-6">
        <div className="flex-1">
          <h1 className="text-3xl font-bold text-white mb-2">
            {config.workflow_title}
          </h1>
          <p className="text-gray-400 max-w-3xl">
            {config.workflow_description}
          </p>
          {config.description && (
            <p className="text-cyan-400 text-sm mt-2 italic">{config.description}</p>
          )}
        </div>
        
        <div className="flex gap-2 ml-4">
          <ActionButton 
            action="accept_workflow" 
            icon={Eye} 
            label="Accept"
            variant="primary"
          />
          <button 
            className="px-3 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded transition-colors text-sm"
            onClick={handleCancel}
          >
            Cancel
          </button>
        </div>
      </div>

      {/* Main Content Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
        <MermaidDiagram chart={config.mermaid_flow} />
        
        <div className="space-y-6">
          {/* Suggested Features */}
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold mb-4 flex items-center text-cyan-400">
              <Zap className="mr-2 h-5 w-5" />
              Suggested Features
            </h3>
            <div className="grid gap-3">
              {config.suggested_features.length === 0 ? (
                <div className="text-gray-400 text-center py-4">
                  No features configured
                </div>
              ) : (
                config.suggested_features.map((feature, index) => (
                  <FeatureCard key={index} feature={feature} />
                ))
              )}
            </div>
          </div>

          {/* Third Party Integrations */}
          <div className="bg-gray-800 border border-gray-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold mb-4 flex items-center text-cyan-400">
              <Settings className="mr-2 h-5 w-5" />
              Third Party Integrations
            </h3>
            <div className="grid gap-3">
              {config.third_party_integrations.length === 0 ? (
                <div className="text-gray-400 text-center py-4">
                  No integrations configured
                </div>
              ) : (
                config.third_party_integrations.map((integration, index) => (
                  <IntegrationCard key={index} integration={integration} />
                ))
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Constraints Section */}
      {config.constraints && config.constraints.length > 0 && (
        <div className="bg-gray-800 border border-gray-700 rounded-lg p-6">
          <h3 className="text-lg font-semibold mb-4 flex items-center text-yellow-400">
            <AlertCircle className="mr-2 h-5 w-5" />
            Constraints & Limitations
          </h3>
          <div className="grid gap-3">
            {config.constraints.map((constraint, index) => (
              <ConstraintItem key={index} constraint={constraint} />
            ))}
          </div>
        </div>
      )}

    </div>
  );
};

// Add display name for better debugging
ActionPlan.displayName = 'ActionPlan';

// Component metadata for the dynamic UI system (MASTER_UI_TOOL_AGENT_PROMPT requirement)
export default ActionPlan;