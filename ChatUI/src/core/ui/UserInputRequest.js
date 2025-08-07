// ==============================================================================
// FILE: ChatUI/src/core/ui/UserInputRequest.js
// DESCRIPTION: Generic user input component for AG2 agent requests
// PURPOSE: Reusable user input component for any workflow
// ==============================================================================

import React, { useState, useCallback } from 'react';
import { FiMessageCircle, FiSend, FiX } from 'react-icons/fi';

/**
 * 🎯 GENERIC USER INPUT REQUEST COMPONENT
 * 
 * Handles any user input requests from AG2 agents during workflow execution.
 * This is triggered when agents use input() or need user feedback.
 * 
 * USAGE:
 * - Any workflow can use this for generic user input
 * - Works with any AG2 agent that sends input requests
 * - Workflow-agnostic and reusable
 */
const UserInputRequest = ({ payload, onResponse, onCancel }) => {
  const [userInput, setUserInput] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const {
    input_request_id,
    prompt = "Input required:",
    password = false,
    chat_id,
    enterprise_id,
    timestamp
  } = payload || {};

  const handleSubmit = useCallback(async (e) => {
    e?.preventDefault();
    
    if (isSubmitting) return;
    
    setIsSubmitting(true);
    
    try {
      // Send response to backend via API endpoint
      const response = await fetch('/api/user-input/submit', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          input_request_id,
          user_input: userInput || "" // Empty string for enter/skip
        })
      });
      
      if (response.ok) {
        const result = await response.json();
        console.log(`✅ UserInputRequest: Sent response for ${input_request_id}:`, result);
        
        // Call onResponse if provided for cleanup/notification
        if (onResponse) {
          await onResponse({
            input_request_id,
            user_response: userInput || "",
            status: 'submitted'
          });
        }
      } else {
        const error = await response.text();
        console.error(`❌ UserInputRequest: Failed to send response:`, error);
        throw new Error(`HTTP ${response.status}: ${error}`);
      }
      
    } catch (error) {
      console.error(`❌ UserInputRequest: Failed to send response:`, error);
    } finally {
      setIsSubmitting(false);
    }
  }, [userInput, input_request_id, onResponse, isSubmitting]);

  const handleSkip = useCallback(async () => {
    // Send empty response (equivalent to pressing enter)
    setUserInput('');
    await handleSubmit();
  }, [handleSubmit]);

  const handleCancel = useCallback(() => {
    if (onCancel) {
      onCancel({
        input_request_id,
        reason: 'user_cancelled'
      });
    }
  }, [input_request_id, onCancel]);

  const handleKeyPress = useCallback((e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  }, [handleSubmit]);

  return (
    <div className="user-input-request-container bg-blue-50 border-l-4 border-blue-400 p-4 mb-4 rounded-r-lg">
      <div className="flex items-start space-x-3">
        <div className="flex-shrink-0">
          <FiMessageCircle className="h-5 w-5 text-blue-400 mt-0.5" />
        </div>
        
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-blue-800 mb-2">
            Agent Input Request
          </div>
          
          <div className="text-sm text-blue-700 mb-3">
            {prompt}
          </div>
          
          <form onSubmit={handleSubmit} className="space-y-3">
            <div className="flex items-center space-x-2">
              <input
                type={password ? "password" : "text"}
                value={userInput}
                onChange={(e) => setUserInput(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="Type your response or press Enter to skip..."
                className="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                disabled={isSubmitting}
                autoFocus
              />
              
              <button
                type="submit"
                disabled={isSubmitting}
                className="inline-flex items-center px-3 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <FiSend className="h-4 w-4" />
              </button>
              
              <button
                type="button"
                onClick={handleSkip}
                disabled={isSubmitting}
                className="inline-flex items-center px-3 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Skip
              </button>
              
              {onCancel && (
                <button
                  type="button"
                  onClick={handleCancel}
                  disabled={isSubmitting}
                  className="inline-flex items-center px-2 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <FiX className="h-4 w-4" />
                </button>
              )}
            </div>
            
            <div className="text-xs text-gray-500">
              Press Enter to submit, or click Skip to continue without input
            </div>
          </form>
        </div>
      </div>
      
      {isSubmitting && (
        <div className="mt-2 text-xs text-blue-600">
          Sending response...
        </div>
      )}
    </div>
  );
};

export default UserInputRequest;