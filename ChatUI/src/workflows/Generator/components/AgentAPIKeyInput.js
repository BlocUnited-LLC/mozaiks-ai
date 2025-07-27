// ==============================================================================
// FILE: ChatUI/src/workflows/generator/components/AgentAPIKeyInput.js
// DESCRIPTION: Generator workflow component for secure API key collection with AG2 integration
// ==============================================================================

import React, { useState } from 'react';

/**
 * AgentAPIKeyInput - Workflow-agnostic API key input component
 * 
 * This component handles secure API key collection for ANY service and communicates 
 * with the backend via the event dispatcher response system. The service type is 
 * dynamically determined by the AG2 agent's request.
 */
const AgentAPIKeyInput = ({ 
  toolId,
  eventId,
  workflowType,
  onResponse,
  // Dynamic props from agent event payload
  payload = {},
  // Fallback defaults
  placeholder,
  label,
  description,
  required = true,
  maskInput = true,
  service = "openai",
  componentId = "AgentAPIKeyInput"
}) => {
  // Extract dynamic configuration from agent payload
  const config = {
    service: payload.service || service,
    label: payload.label || label || `${(payload.service || service).toUpperCase()} API Key`,
    description: payload.description || description || `Enter your ${payload.service || service} API key to continue`,
    placeholder: payload.placeholder || placeholder || `Enter your ${(payload.service || service).toUpperCase()} API key...`,
    required: payload.required !== undefined ? payload.required : required,
    maskInput: payload.maskInput !== undefined ? payload.maskInput : maskInput
  };
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
      // Prepare response for backend (don't send actual key in logs)
      const response = {
        status: 'success',
        action: 'submit',
        data: {
          service: config.service,
          apiKey: apiKey.trim(), // This will be securely handled by backend
          hasApiKey: true,
          keyLength: apiKey.length,
          submissionTime: new Date().toISOString(),
          toolId,
          eventId,
          workflowType
        }
      };

      // Send response back to backend via event dispatcher
      if (onResponse) {
        await onResponse(response);
      }
      
      setApiKey(''); // Clear input after successful submission
      
      console.log(`✅ AgentAPIKeyInput: API key submitted for service: ${config.service}`);
      
    } catch (error) {
      console.error('❌ AgentAPIKeyInput: Submission failed:', error);
      setError('Failed to submit API key. Please try again.');
      
      // Send error response
      if (onResponse) {
        onResponse({
          status: 'error',
          action: 'submit',
          error: error.message,
          data: { service: config.service, toolId, eventId }
        });
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = async () => {
    try {
      // Send cancel response to backend
      const response = {
        status: 'cancelled',
        action: 'cancel',
        data: {
          service: config.service,
          cancelTime: new Date().toISOString(),
          toolId,
          eventId,
          workflowType
        }
      };

      if (onResponse) {
        await onResponse(response);
      }
      
      setApiKey('');
      setError('');
      
      console.log(`🚫 AgentAPIKeyInput: Cancelled for service: ${config.service}`);
      
    } catch (error) {
      console.error('❌ AgentAPIKeyInput: Cancel failed:', error);
    }
  };

  const toggleVisibility = () => {
    setIsVisible(!isVisible);
  };

  return (
    <div className="agent-api-key-input rounded-lg p-6 max-w-md mx-auto border-cyan-500/30 bg-gray-900">
      <div className="header mb-4">
        <h3 className="text-cyan-400 text-lg font-semibold mb-2 flex items-center gap-2">
          <span>🔑</span>
          {config.label}
          {config.required && <span className="text-red-400 ml-1">*</span>}
        </h3>
        {config.description && (
          <p className="text-gray-400 text-sm">{config.description}</p>
        )}
        <div className="flex justify-between items-center mt-2">
          <p className="text-gray-400 text-xs">Service: {config.service}</p>
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
              className={`w-full px-4 py-3 bg-gray-800 border rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 transition-colors ${
                error 
                  ? 'border-red-500 focus:ring-red-500' 
                  : 'border-gray-600 focus:border-cyan-500 focus:ring-cyan-500'
              } ${isSubmitting ? 'opacity-50 cursor-not-allowed' : ''}`}
            />
            
            {config.maskInput && (
              <button
                type="button"
                onClick={toggleVisibility}
                className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-white transition-colors"
                disabled={isSubmitting}
              >
                {isVisible ? '🙈' : '👁️'}
              </button>
            )}
          </div>

          {error && (
            <p className="text-red-400 text-sm mt-2">⚠️ {error}</p>
          )}
        </div>
        
        <div className="button-group flex gap-3">
          <button
            type="button"
            onClick={handleCancel}
            disabled={isSubmitting}
            className="flex-1 px-4 py-3 bg-gray-600 hover:bg-gray-700 disabled:bg-gray-700 disabled:opacity-50 text-white rounded-lg transition-colors font-medium"
          >
            Cancel
          </button>
          
          <button
            type="submit"
            disabled={!apiKey.trim() || isSubmitting}
            className="flex-1 px-4 py-3 bg-cyan-600 hover:bg-cyan-700 disabled:bg-gray-700 disabled:opacity-50 text-white rounded-lg transition-colors font-medium"
          >
            {isSubmitting ? '⏳ Submitting...' : '🔑 Submit'}
          </button>
        </div>
      </form>

      {/* Debug info (only in development) */}
      {process.env.NODE_ENV === 'development' && (
        <div className="debug-info mt-4 p-2 bg-gray-800 rounded text-xs text-gray-400">
          <div>Tool: {toolId} | Event: {eventId} | Workflow: {workflowType}</div>
          <div>Service: {config.service} | Required: {config.required.toString()} | Component: {componentId}</div>
        </div>
      )}
    </div>
  );
};

// Add display name for better debugging
AgentAPIKeyInput.displayName = 'AgentAPIKeyInput';

export default AgentAPIKeyInput;
