// ==============================================================================
// FILE: ChatUI/src/workflows/generator/components/FileDownloadCenter.js
// DESCRIPTION: Generator workflow component for file downloads with AG2 integration
// ==============================================================================

import React, { useState } from 'react';
import { createToolsLogger } from '../../../core/toolsLogger';
import { colors as designColors, typography as designTypography, components as designComponents } from '../../../styles/artifactDesignSystem';

/**
 * FileDownloadCenter - Production AG2 component for file downloads
 * 
 * Handles file downloads with rich agent context feedback within the AG2 workflow system.
 * Fully integrated with chat.* event protocol and provides detailed completion signals.
 */
const FileDownloadCenter = ({
  payload = {},
  onResponse,
  ui_tool_id,
  eventId,
  sourceWorkflowName,
  generatedWorkflowName,
  componentId = 'FileDownloadCenter'
}) => {
  const files = Array.isArray(payload.files) ? payload.files : [];
  const agentMessageId = payload.agent_message_id;
  const resolvedWorkflowName = generatedWorkflowName || sourceWorkflowName || payload.generatedWorkflowName || payload.sourceWorkflowName || null;
  const config = {
    files,
    title: payload.title || 'Workflow Bundle Ready',
    description: payload.agent_message || payload.description || 'Would you like to download the generated workflow bundle now?'
  };
  const tlog = createToolsLogger({ tool: ui_tool_id || componentId, eventId, workflowName: resolvedWorkflowName, agentMessageId });
  const [decision, setDecision] = useState(null); // 'yes' | 'no'

  const containerClasses = [designComponents.panel.inline, 'file-download-center inline-file-download w-full max-w-lg mx-auto'].join(' ');
  const yesInactiveClasses = designComponents.button.primary;
  const yesActiveClasses = [designComponents.button.primary, designColors.status.success.bg, designColors.status.success.text].join(' ');
  const noInactiveClasses = designComponents.button.secondary;
  const noActiveClasses = [designComponents.button.secondary, designColors.status.error.bg, designColors.status.error.text].join(' ');

  const decide = async (answer) => {
    if (decision) return; // idempotent
    const yes = answer === 'yes';
    setDecision(answer);
    tlog.event('decision', 'start', { answer, fileCount: config.files.length });
    const response = yes ? {
      status: 'success',
      action: 'confirm_download',
      data: {
        ui_tool_id,
        eventId,
        workflowName: resolvedWorkflowName,
        sourceWorkflowName,
        generatedWorkflowName,
        agent_message_id: agentMessageId,
        fileCount: config.files.length
      },
      agentContext: { confirmation: 'yes', proceed: true }
    } : {
      status: 'cancelled',
      action: 'decline_download',
      data: {
        ui_tool_id,
        eventId,
        workflowName: resolvedWorkflowName,
        sourceWorkflowName,
        generatedWorkflowName,
        agent_message_id: agentMessageId,
        fileCount: config.files.length
      },
      agentContext: { confirmation: 'no', proceed: false }
    };
    try {
      if (onResponse) await onResponse(response);
      tlog.event('decision', 'done', { answer, ok: true, fileCount: config.files.length });
    } catch (e) {
      tlog.error('decision failed', { error: e?.message });
    }
  };

  return (
  <div
  className={containerClasses}
    data-agent-message-id={agentMessageId || undefined}
    data-display-mode="inline"
    aria-label="Workflow file downloads"
  >
      <div className="download-header mb-2">
        <h3 className={`${designTypography.label.md} ${designColors.brand.primaryLight.text}`}>
          {config.title}
        </h3>
      </div>
      
      {config.description && (
        <p className={`${designTypography.body.md} ${designColors.text.secondary} mb-3 leading-relaxed`}>
          {config.description}
        </p>
      )}

      <div className="flex gap-3 mb-1">
        <button
          onClick={() => decide('yes')}
          disabled={!!decision}
          className={[decision === 'yes' ? yesActiveClasses : yesInactiveClasses, 'flex flex-1 items-center justify-center', !!decision && 'opacity-80 cursor-default'].filter(Boolean).join(' ')}
        >
          {decision === 'yes' ? '✓ Yes' : 'Yes'}
        </button>
        <button
          onClick={() => decide('no')}
          disabled={!!decision}
          className={[decision === 'no' ? noActiveClasses : noInactiveClasses, 'flex flex-1 items-center justify-center', !!decision && 'opacity-80 cursor-default'].filter(Boolean).join(' ')}
        >
          {decision === 'no' ? '✕ No' : 'No'}
        </button>
      </div>

      {decision && (
        <div className={`mt-2 ${designTypography.body.sm} ${designColors.text.muted}`}>
          {decision === 'yes' ? 'Preparing download...' : 'Download skipped.'}
        </div>
      )}

      {/* Original file list UI removed for simplified confirmation flow */}

      {/* Debug info (only in development) */}
      {process.env.NODE_ENV === 'development' && (
        <div
          className={[
            'debug-info mt-3 rounded-lg border p-2 text-[10px] tracking-wide',
            designColors.border.subtle,
            designColors.surface.raisedOverlay,
            designColors.text.muted,
          ].join(' ')}
        >
          <div>Tool: {ui_tool_id} • Event: {eventId} • Flow: {resolvedWorkflowName}</div>
          <div>Files: {config.files.length} • Component: {componentId} • Mode: inline-confirmation</div>
        </div>
      )}
    </div>
  );
};

// Add display name for better debugging
FileDownloadCenter.displayName = 'FileDownloadCenter';

// Component metadata for the dynamic UI system (MASTER_UI_TOOL_AGENT_PROMPT requirement)
export default FileDownloadCenter;
