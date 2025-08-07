// ==============================================================================
// FILE: ChatUI/src/workflows/generator/components/FileDownloadCenter.js
// DESCRIPTION: Generator workflow component for file downloads with AG2 integration
// ==============================================================================

import React, { useState } from 'react';

/**
 * FileDownloadCenter - Workflow-agnostic file download component
 * 
 * This component handles file downloads and communicates with the backend
 * via the event dispatcher response system.
 */
const FileDownloadCenter = ({ 
  payload = {},
  ui_tool_id,
  eventId,
  workflowName,
  onResponse,
  componentId = "FileDownloadCenter"
}) => {
  // DEV NOTE: This component receives the agent's contextual message via the
  // `payload.description` prop. This is the standardized convention for all
  // dynamic UI components in this application.
  const config = {
    files: payload.files || [],
    title: payload.title || "Generated Files",
    description: payload.description || null
  };
  const [downloadStatus, setDownloadStatus] = useState({});

  const handleDownload = async (fileId, filename) => {
    setDownloadStatus(prev => ({ ...prev, [fileId]: 'downloading' }));
    
    try {
      // Enhanced response with rich agent feedback information
      const response = {
        status: 'success',
        action: 'download',
        data: {
          fileId: fileId,
          filename: filename,
          downloadTime: new Date().toISOString(),
          ui_tool_id,
          eventId,
          workflowName,
          // Additional context for agent decision making
          userAction: 'download_initiated',
          downloadMethod: 'single_file',
          fileInfo: config.files.find(f => f.id === fileId) || { name: filename }
        },
        // Agent context - helps agents understand what happened
        agentContext: {
          nextAction: 'continue_workflow',  // Suggest what agent should do next
          userEngagement: 'positive',       // User is engaging with the content
          workflowStage: 'file_delivery',   // What stage of workflow this represents
          shouldContinue: true              // Whether workflow should continue
        }
      };

      // Call the response handler from event dispatcher
      if (onResponse) {
        await onResponse(response);
      }
      
      setDownloadStatus(prev => ({ ...prev, [fileId]: 'completed' }));
      
      console.log(`✅ FileDownloadCenter: Downloaded ${filename} with agent context`);
      
    } catch (error) {
      console.error('❌ FileDownloadCenter: Download failed:', error);
      setDownloadStatus(prev => ({ ...prev, [fileId]: 'error' }));
      
      // Enhanced error response with context
      if (onResponse) {
        onResponse({
          status: 'error',
          action: 'download',
          error: error.message,
          data: { fileId, filename, ui_tool_id, eventId },
          agentContext: {
            nextAction: 'retry_or_skip',
            userEngagement: 'neutral',
            workflowStage: 'file_delivery_failed',
            shouldContinue: true,
            errorRecovery: 'offer_alternative'
          }
        });
      }
    }
  };

  const handleDownloadAll = async () => {
    try {
      // Enhanced bulk download response with rich agent context
      const response = {
        status: 'success',
        action: 'download_all',
        data: {
          fileCount: config.files.length,
          files: config.files.map(f => ({ id: f.id, name: f.name, size: f.size })),
          downloadTime: new Date().toISOString(),
          ui_tool_id,
          eventId,
          workflowName,
          // Additional context for agents
          userAction: 'bulk_download_initiated',
          downloadMethod: 'bulk_operation',
          totalSize: config.files.reduce((sum, f) => sum + (f.size || 0), 0)
        },
        // Rich agent context for decision making
        agentContext: {
          nextAction: 'workflow_complete',    // User got all files - workflow likely complete
          userEngagement: 'very_positive',    // User wants everything - high engagement
          workflowStage: 'successful_completion',
          shouldContinue: false,              // Workflow can end successfully
          satisfactionLevel: 'high',          // User satisfaction indicator
          completionSignal: true              // Signal that user's needs are met
        }
      };

      if (onResponse) {
        await onResponse(response);
      }
      
      // Mark all files as downloaded
      const allDownloaded = {};
      config.files.forEach(file => {
        allDownloaded[file.id] = 'completed';
      });
      setDownloadStatus(allDownloaded);

      console.log(`✅ FileDownloadCenter: Downloaded all ${config.files.length} files with completion signal`);
      
    } catch (error) {
      console.error('❌ FileDownloadCenter: Download all failed:', error);
      
      if (onResponse) {
        onResponse({
          status: 'error',
          action: 'download_all',
          error: error.message,
          data: { fileCount: config.files.length, ui_tool_id, eventId },
          agentContext: {
            nextAction: 'troubleshoot_bulk_download',
            userEngagement: 'frustrated',
            workflowStage: 'bulk_download_failed',
            shouldContinue: true,
            errorRecovery: 'offer_individual_downloads'
          }
        });
      }
    }
  };

  const handleCancel = () => {
    if (onResponse) {
      onResponse({
        status: 'cancelled',
        action: 'cancel',
        data: { ui_tool_id, eventId, workflowName },
        // Rich cancellation context for agents
        agentContext: {
          nextAction: 'ask_about_alternatives',  // Agent should ask what user wants instead
          userEngagement: 'disengaged',          // User doesn't want the files
          workflowStage: 'file_delivery_rejected',
          shouldContinue: true,                  // Continue workflow but adapt approach
          rejectionReason: 'user_cancelled',     // Why the interaction failed
          suggestedRecovery: 'offer_different_format_or_content'
        }
      });
    }
  };

  return (
    <div className="file-download-center bg-gray-900 border border-cyan-500/30 rounded-lg p-4">
      <div className="download-header flex justify-between items-center mb-4">
        <h3 className="text-cyan-400 text-lg font-semibold">{config.title}</h3>
        <div className="flex gap-2">
          {config.files.length > 1 && (
            <button 
              className="px-4 py-2 bg-cyan-600 hover:bg-cyan-700 text-white rounded transition-colors"
              onClick={handleDownloadAll}
            >
              Download All ({config.files.length})
            </button>
          )}
          <button 
            className="px-3 py-2 bg-gray-600 hover:bg-gray-700 text-white rounded transition-colors text-sm"
            onClick={handleCancel}
          >
            Cancel
          </button>
        </div>
      </div>
      
      {config.description && (
        <p className="text-gray-400 text-sm mb-4">{config.description}</p>
      )}

      <div className="file-list space-y-2">
        {config.files.length === 0 ? (
          <div className="no-files text-gray-400 text-center py-8">
            No files available for download
          </div>
        ) : (
          config.files.map((file) => (
            <div key={file.id} className="file-item flex items-center justify-between p-3 bg-gray-800 rounded border border-gray-700">
              <div className="file-info flex-1">
                <div className="filename text-white font-medium">{file.name}</div>
                <div className="file-size text-gray-400 text-sm">
                  {file.size || 'Unknown size'}
                  {file.type && ` • ${file.type}`}
                </div>
              </div>
              
              <button
                className={`download-btn px-4 py-2 rounded transition-colors font-medium ${
                  downloadStatus[file.id] === 'downloading' 
                    ? 'bg-yellow-600 text-white cursor-not-allowed' 
                    : downloadStatus[file.id] === 'completed'
                    ? 'bg-green-600 text-white'
                    : downloadStatus[file.id] === 'error'
                    ? 'bg-red-600 hover:bg-red-700 text-white'
                    : 'bg-blue-600 hover:bg-blue-700 text-white'
                }`}
                onClick={() => handleDownload(file.id, file.name)}
                disabled={downloadStatus[file.id] === 'downloading'}
              >
                {downloadStatus[file.id] === 'downloading' && '⏳ Downloading...'}
                {downloadStatus[file.id] === 'completed' && '✓ Downloaded'}
                {downloadStatus[file.id] === 'error' && '🔄 Retry'}
                {!downloadStatus[file.id] && '📥 Download'}
              </button>
            </div>
          ))
        )}
      </div>

      {/* Debug info (only in development) */}
      {process.env.NODE_ENV === 'development' && (
        <div className="debug-info mt-4 p-2 bg-gray-800 rounded text-xs text-gray-400">
          <div>Tool: {ui_tool_id} | Event: {eventId} | Workflow: {workflowName}</div>
          <div>Files: {config.files.length} | Component: {componentId}</div>
        </div>
      )}
    </div>
  );
};

// Add display name for better debugging
FileDownloadCenter.displayName = 'FileDownloadCenter';

export default FileDownloadCenter;
