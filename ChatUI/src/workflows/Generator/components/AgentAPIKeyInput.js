// ==============================================================================
// FILE: ChatUI/src/workflows/Generator/components/AgentAPIKeyInput.js
// DESCRIPTION: Refined API key intake component aligned with artifact design system
// ==============================================================================

import React, { useState } from 'react';
import { typography, colors, components, spacing } from '../../../styles/artifactDesignSystem';
import { createToolsLogger } from '../../../core/toolsLogger';

const AgentAPIKeyInput = ({
  payload = {},
  onResponse,
  ui_tool_id,
  eventId,
  sourceWorkflowName,
  generatedWorkflowName,
  componentId = 'AgentAPIKeyInput'
}) => {
  // ---------------------------------------------------------------------------
  // 1. HOOKS
  // ---------------------------------------------------------------------------
  const [apiKey, setApiKey] = useState('');
  const [isVisible, setIsVisible] = useState(() => {
    const shouldMask = payload.maskInput !== undefined ? Boolean(payload.maskInput) : true;
    return !shouldMask;
  });
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  // ---------------------------------------------------------------------------
  // 2. DERIVED VALUES
  // ---------------------------------------------------------------------------
  const service = String(payload.service || 'openai').trim().toLowerCase();
  const friendlyServiceName = service
    .split(/[_\s-]+/)
    .filter(Boolean)
    .map((segment) => segment.charAt(0).toUpperCase() + segment.slice(1))
    .join(' ');
  const agentMessageId = payload.agent_message_id;
  const resolvedWorkflowName =
    generatedWorkflowName ||
    sourceWorkflowName ||
    payload.generatedWorkflowName ||
    payload.sourceWorkflowName ||
    null;

  const requiresKey = payload.required !== undefined ? Boolean(payload.required) : true;
  const maskInput = payload.maskInput !== undefined ? Boolean(payload.maskInput) : true;
  const description =
    payload.agent_message ||
    payload.description ||
    `Connect your ${friendlyServiceName} account so the workflow can continue.`;
  const placeholder =
    payload.placeholder || `Enter your ${service.toUpperCase()} API key...`;

  const tlog = createToolsLogger({
    tool: ui_tool_id || componentId,
    eventId,
    workflowName: resolvedWorkflowName,
    agentMessageId
  });

  const containerClasses = 'w-full';
  const cardClasses =
    'w-full max-w-sm rounded-2xl border border-[rgba(var(--color-primary-rgb),0.18)] bg-[rgba(10,16,38,0.92)] px-6 py-5 shadow-[0_18px_38px_rgba(8,15,40,0.45)] space-y-5';
  const headingClasses = `${typography.display.xs} ${colors.text.primary}`;
  const descriptionClasses = `${typography.body.sm} ${colors.text.secondary}`;
  const inputClasses = [
    components.input.base,
    maskInput ? components.input.withIcon : '',
    error ? components.input.error : '',
    isSubmitting ? components.input.disabled : ''
  ]
    .filter(Boolean)
    .join(' ');
  const assistiveTextClasses = `${typography.body.sm} ${colors.text.muted}`;
  const errorTextClasses = `${typography.body.sm} ${colors.status.error.text}`;
  const buttonGroup = 'flex items-center gap-3';
  const secondaryButtonClasses = `${components.button.ghost} flex-1`;
  const primaryButtonClasses = `${components.button.primary} flex-1`;

  // ---------------------------------------------------------------------------
  // 3. EVENT HANDLERS
  // ---------------------------------------------------------------------------
  const validateApiKey = (key) => {
    if (!key.trim()) {
      return requiresKey ? 'API key is required.' : null;
    }
    return null;
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    const validationError = validateApiKey(apiKey);
    if (validationError) {
      setError(validationError);
      return;
    }

    setIsSubmitting(true);
    setError('');

    try {
      tlog.event('submit', 'start', { service });
      const response = {
        status: 'success',
        action: 'submit',
        data: {
          service,
          apiKey: apiKey.trim(),
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
      if (onResponse) await onResponse(response);
      setApiKey('');
      tlog.event('submit', 'done', { service, ok: true });
    } catch (submitError) {
      const fallbackMessage = 'Unable to submit the API key. Please try again.';
      setError(fallbackMessage);
      tlog.error('submit failed', { service, error: submitError?.message });
      if (onResponse) {
        onResponse({
          status: 'error',
          action: 'submit',
          error: submitError?.message || fallbackMessage,
          data: { service, ui_tool_id, eventId, agent_message_id: agentMessageId }
        });
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = async () => {
    try {
      tlog.event('cancel', 'start', { service });
      const response = {
        status: 'cancelled',
        action: 'cancel',
        data: {
          service,
          cancelTime: new Date().toISOString(),
          ui_tool_id,
          eventId,
          workflowName: resolvedWorkflowName,
          sourceWorkflowName,
          generatedWorkflowName,
          agent_message_id: agentMessageId
        }
      };
      if (onResponse) await onResponse(response);
      setApiKey('');
      setError('');
      tlog.event('cancel', 'done', { service, ok: true });
    } catch (cancelError) {
      tlog.error('cancel failed', { service, error: cancelError?.message });
    }
  };

  const toggleVisibility = () => setIsVisible((current) => !current);

  // ---------------------------------------------------------------------------
  // 4. RENDER
  // ---------------------------------------------------------------------------
  return (
    <div className={containerClasses} data-agent-message-id={agentMessageId || undefined}>
      <div className={cardClasses}>
        <div className="flex items-start gap-3">
          <span
            className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-[rgba(255,200,0,0.12)] text-sm font-semibold"
            aria-hidden="true"
          >
            {'🔑'}
          </span>
          <div className="flex-1 space-y-1.5">
            <h2 className={headingClasses}>{payload.label || `Connect ${friendlyServiceName}`}</h2>
            <p className={descriptionClasses}>{description}</p>
          </div>
        </div>

        <form onSubmit={handleSubmit} className={`${spacing.items} pt-1`}>
          <label className={`${typography.label.md} ${colors.text.secondary} block`}>
            API key
          </label>
          <div className="relative mt-2">
            <input
              type={isVisible ? 'text' : 'password'}
              value={apiKey}
              onChange={(event) => {
                setApiKey(event.target.value);
                if (error) setError('');
              }}
              placeholder={placeholder}
              required={requiresKey}
              disabled={isSubmitting}
              className={inputClasses}
            />
            {maskInput && (
              <button
                type="button"
                onClick={toggleVisibility}
                disabled={isSubmitting}
                className="absolute inset-y-0 right-3 flex items-center text-xs font-semibold uppercase tracking-wide text-[rgba(255,255,255,0.65)] hover:text-white transition-colors"
              >
                {isVisible ? 'Hide' : 'Show'}
              </button>
            )}
          </div>
          {error && <p className={`${errorTextClasses} mt-2`}>{error}</p>}

          <div className={buttonGroup}>
            <button
              type="button"
              onClick={handleCancel}
              disabled={isSubmitting}
              className={secondaryButtonClasses}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!apiKey.trim() || isSubmitting}
              className={primaryButtonClasses}
            >
              {isSubmitting ? 'Submitting...' : 'Submit'}
            </button>
          </div>
        </form>

        <div className={assistiveTextClasses}>
          <p>We never display the key after submission.</p>
          <p>Service identifier: <span className={colors.text.primary}>{service}</span></p>
        </div>
      </div>
    </div>

  );
};

AgentAPIKeyInput.displayName = 'AgentAPIKeyInput';
export default AgentAPIKeyInput;
