// ==============================================================================
// FILE: workflows/Generator/Components/Inline/AgentAPIKeyInput.js
// DESCRIPTION: Inline component for secure API key collection
// ==============================================================================

import React, { useState } from 'react';

const AgentAPIKeyInput = ({ 
  onSubmit,
  onCancel,
  placeholder = "Enter your API key...",
  label = "API Key",
  required = true,
  maskInput = true
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

  const handleCancel = () => {
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
