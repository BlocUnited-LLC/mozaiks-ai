// ==============================================================================
// FILE: workflows/Generator/Components/Inline/AgentAPIKeyInput.js
// DESCRIPTION: Inline component for secure API key collection with AG2 context integration
// ==============================================================================

import React, { useState } from 'react';
import { simpleTransport } from '../../../../ChatUI/src/core/simpleTransport';

const AgentAPIKeyInput = ({ 
  onSubmit,
  onCancel,
  placeholder = "Enter your API key...",
  label = "API Key",
  required = true,
  maskInput = true,
  service = "openai", // Which service this API key is for
  componentId = "AgentAPIKeyInput" // Unique identifier for this component instance
}) => {
  const [apiKey, setApiKey] = useState('');
  const [isVisible, setIsVisible] = useState(!maskInput);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    if (!apiKey.trim()) {
      return;
    }

    setIsSubmitting(true);
    
    try {
      // Send component action to AG2 ContextVariables
      await simpleTransport.sendComponentAction(
        componentId,
        'submit',
        {
          service: service,
          hasApiKey: true, // Don't send actual key for security
          submissionTime: new Date().toISOString()
        }
      );
      
      // Call the original onSubmit if provided
      if (onSubmit) {
        await onSubmit(apiKey.trim());
      }
      
      setApiKey(''); // Clear input after successful submission
    } catch (error) {
      console.error('API key submission failed:', error);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = async () => {
    // Send cancel action to context
    await simpleTransport.sendComponentAction(
      componentId,
      'cancel',
      {
        service: service,
        cancelTime: new Date().toISOString()
      }
    );
    
    setApiKey('');
    if (onCancel) {
      onCancel();
    }
  };

  const toggleVisibility = () => {
    setIsVisible(!isVisible);
  };

  return (
    <div className="agent-api-key-input">
      <form onSubmit={handleSubmit} className="api-key-form">
        <div className="input-group">
          <label htmlFor="api-key-input" className="input-label">
            {label}
            {required && <span className="required">*</span>}
          </label>
          
          <div className="input-wrapper">
            <input
              id="api-key-input"
              type={isVisible ? "text" : "password"}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder={placeholder}
              required={required}
              disabled={isSubmitting}
              className="api-key-input"
            />
            
            {maskInput && (
              <button
                type="button"
                onClick={toggleVisibility}
                className="visibility-toggle"
                disabled={isSubmitting}
              >
                {isVisible ? '👁️' : '👁️‍🗨️'}
              </button>
            )}
          </div>
        </div>
        
        <div className="button-group">
          <button
            type="button"
            onClick={handleCancel}
            disabled={isSubmitting}
            className="cancel-btn"
          >
            Cancel
          </button>
          
          <button
            type="submit"
            disabled={!apiKey.trim() || isSubmitting}
            className="submit-btn"
          >
            {isSubmitting ? 'Submitting...' : 'Submit'}
          </button>
        </div>
      </form>
    </div>
  );
};

export default AgentAPIKeyInput;
