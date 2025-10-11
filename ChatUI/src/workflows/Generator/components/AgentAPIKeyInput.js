// ==============================================================================
// FILE: ChatUI/src/workflows/generator/components/AgentAPIKeyInput.js
// DESCRIPTION: Generator workflow component for secure API key collection with AG2 integration
// ==============================================================================

import React, { useState } from 'react';
import { createToolsLogger } from '../../../core/toolsLogger';
import { components as designComponents, colors as designColors, typography as designTypography } from '../../../styles/artifactDesignSystem';

/**
 * AgentAPIKeyInput - Production AG2 component for secure API key collection
 * 
 * Handles secure API key collection for ANY service within the AG2 workflow system.
 * Fully integrated with chat.* event protocol and WebSocket communication.
 */
const AgentAPIKeyInput = ({
  payload = {},
  onResponse,
  ui_tool_id,
  eventId,
  sourceWorkflowName,
  generatedWorkflowName,
  componentId = 'AgentAPIKeyInput'
}) => {
  const service = String(payload.service || 'openai').trim().toLowerCase();
  const agentMessageId = payload.agent_message_id;
  const resolvedWorkflowName = generatedWorkflowName || sourceWorkflowName || payload.generatedWorkflowName || payload.sourceWorkflowName || null;
  const agentMessage = payload.agent_message || payload.description || `Enter your ${service.toUpperCase()} API key to continue.`;
  const config = {
    service,
    label: payload.label || `${service.toUpperCase()} API Key`,
    description: agentMessage,
    placeholder: payload.placeholder || `Enter your ${service.toUpperCase()} API key...`,
    required: payload.required !== undefined ? payload.required : true,
    maskInput: payload.maskInput !== undefined ? payload.maskInput : true
  };
  const tlog = createToolsLogger({ tool: ui_tool_id || componentId, eventId, workflowName: resolvedWorkflowName, agentMessageId });
  const [apiKey, setApiKey] = useState('');
  const [isVisible, setIsVisible] = useState(!config.maskInput);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  // Validate API key - simple validation
  const validateApiKey = (key) => {
    if (!key.trim()) {
      return config.required ? 'API key is required' : null;
    }
    return null;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    const validationError = validateApiKey(apiKey);
    if (validationError) {
      setError(validationError);
      return;
    }

    setIsSubmitting(true);
    setError('');
    
    try {
      tlog.event('submit', 'start', { service: config.service });
      const response = {
        status: 'success',
        action: 'submit',
        data: {
          service: config.service,
          apiKey: apiKey.trim(), // This will be securely handled by backend
          hasApiKey: true,
          keyLength: apiKey.length,
          submissionTime: new Date().toISOString(),
          ui_tool_id,
          eventId,
          workflowName: resolvedWorkflowName,
          sourceWorkflowName,
          generatedWorkflowName,
          agent_message_id: agentMessageId
        }
      };

      // Send response back to backend via event dispatcher
      if (onResponse) {
        await onResponse(response);
      }
      
      setApiKey(''); // Clear input after successful submission
      tlog.event('submit', 'done', { service: config.service, ok: true });
    } catch (error) {
      setError('Failed to submit API key. Please try again.');
      tlog.error('submit failed', { service: config.service, error: error?.message });
      if (onResponse) {
        onResponse({
          status: 'error',
          action: 'submit',
          error: error.message,
          data: { service: config.service, ui_tool_id, eventId, agent_message_id: agentMessageId }
        });
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = async () => {
    try {
      tlog.event('cancel', 'start', { service: config.service });
      const response = {
        status: 'cancelled',
        action: 'cancel',
        data: {
          service: config.service,
          cancelTime: new Date().toISOString(),
          ui_tool_id,
          eventId,
          workflowName: resolvedWorkflowName,
          sourceWorkflowName,
          generatedWorkflowName,
          agent_message_id: agentMessageId
        }
      };

      if (onResponse) {
        await onResponse(response);
      }
      
      setApiKey('');
      setError('');
      tlog.event('cancel', 'done', { service: config.service, ok: true });
    } catch (error) {
      tlog.error('cancel failed', { service: config.service, error: error?.message });
    }
  };

  const toggleVisibility = () => {
    setIsVisible(!isVisible);
  };

  return (
  <div
    className={`${designComponents.panel.inline} agent-api-key-input max-w-md mx-auto`}
    data-agent-message-id={agentMessageId || undefined}
  >
      <div className="header mb-4">
        <h3 className={`${designTypography.heading.lg} ${designColors.brand.primaryLight.text} mb-2 flex items-center gap-2`}>
          <span>🔑</span>
          {config.label}
          {config.required && <span className={`${designColors.status.error.text} ml-1`}>*</span>}
        </h3>
        {config.description && (
          <p className={`${designTypography.body.md} ${designColors.text.secondary}`}>{config.description}</p>
        )}
        <div className="flex justify-between items-center mt-2">
          <p className={`${designTypography.body.sm} ${designColors.text.muted}`}>Service: {config.service}</p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="api-key-form space-y-4">
        <div className="input-group">
          <div className="input-wrapper relative">
            <input
              id="api-key-input"
              type={isVisible ? "text" : "password"}
              value={apiKey}
              onChange={(e) => {
                setApiKey(e.target.value);
                if (error) setError(''); // Clear error when user types
              }}
              placeholder={config.placeholder}
              required={config.required}
              disabled={isSubmitting}
              className={[
                designComponents.input.base,
                config.maskInput ? designComponents.input.withIcon : '',
                error ? designComponents.input.error : '',
                isSubmitting ? designComponents.input.disabled : '',
              ].filter(Boolean).join(' ')}
            />
            
            {config.maskInput && (
              <button
                type="button"
                onClick={toggleVisibility}
                className={[
                  'absolute right-3 top-1/2 -translate-y-1/2 transform',
                  designColors.text.secondary,
                  'hover:text-[var(--color-text-primary)] hover:text-slate-100 transition-colors',
                ].join(' ')}
                disabled={isSubmitting}
              >
                {isVisible ? '🙈' : '👁️'}
              </button>
            )}
          </div>

          {error && (
            <p className={`${designColors.status.error.text} ${designTypography.body.md} mt-2`}>⚠️ {error}</p>
          )}
        </div>
        
        <div className="button-group flex gap-3">
          <button
            type="button"
            onClick={handleCancel}
            disabled={isSubmitting}
            className={[designComponents.button.secondary, 'flex flex-1 items-center justify-center'].join(' ')}
          >
            Cancel
          </button>
          
          <button
            type="submit"
            disabled={!apiKey.trim() || isSubmitting}
            className={[designComponents.button.primary, 'flex flex-1 items-center justify-center'].join(' ')}
          >
            {isSubmitting ? '⏳ Submitting...' : '🔑 Submit'}
          </button>
        </div>
      </form>

      {/* Debug info (only in development) */}
      {process.env.NODE_ENV === 'development' && (
        <div
          className={[
            'debug-info mt-4 rounded-lg border p-3',
            designColors.border.subtle,
            designColors.surface.raisedOverlay,
            designTypography.body.sm,
            designColors.text.muted,
          ].join(' ')}
        >
          <div>Tool: {ui_tool_id} | Event: {eventId} | Workflow: {resolvedWorkflowName}</div>
          <div>Service: {config.service} | Required: {config.required.toString()} | Component: {componentId}</div>
        </div>
      )}
    </div>
  );
};

// Add display name for better debugging
AgentAPIKeyInput.displayName = 'AgentAPIKeyInput';

// Component metadata for the dynamic UI system
export default AgentAPIKeyInput;
