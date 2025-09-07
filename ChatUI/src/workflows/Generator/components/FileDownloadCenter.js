// ==============================================================================
// FILE: ChatUI/src/workflows/generator/components/FileDownloadCenter.js
// DESCRIPTION: Generator workflow component for file downloads with AG2 integration
// ==============================================================================

import React, { useState } from 'react';
import { createToolsLogger } from '../../../core/toolsLogger';

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
  workflowName,
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
  const agentMessageId = payload.agent_message_id;
  const tlog = createToolsLogger({ tool: ui_tool_id || componentId, eventId, workflowName, agentMessageId });
  const [downloadStatus, setDownloadStatus] = useState({});

  const handleDownload = async (fileId, filename) => {
    setDownloadStatus(prev => ({ ...prev, [fileId]: 'downloading' }));
    
    try {
      tlog.event('download', 'start', { fileId, filename });
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
          agent_message_id: agentMessageId,
          fileInfo: config.files.find(f => f.id === fileId) || { name: filename }
        },
        agentContext: { downloaded: true, type: 'single' }
      };

      // Call the response handler from event dispatcher
      if (onResponse) {
        await onResponse(response);
      }
      
      setDownloadStatus(prev => ({ ...prev, [fileId]: 'completed' }));
      
  tlog.event('download', 'done', { fileId, ok: true });
      
    } catch (error) {
  tlog.error('download failed', { fileId, error: error?.message });
      setDownloadStatus(prev => ({ ...prev, [fileId]: 'error' }));
      
      // Enhanced error response with context
      if (onResponse) {
        onResponse({
          status: 'error',
          action: 'download',
          error: error.message,
          data: { fileId, filename, ui_tool_id, eventId, agent_message_id: agentMessageId },
          agentContext: { downloaded: false, type: 'single', error: true }
        });
      }
    }
  };

  const handleDownloadAll = async () => {
    try {
      tlog.event('download_all', 'start', { count: config.files.length });
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
          agent_message_id: agentMessageId,
          totalSize: config.files.reduce((sum, f) => sum + (f.size_bytes || 0), 0)
        },
        agentContext: { downloaded: true, type: 'bulk', complete: true }
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

  tlog.event('download_all', 'done', { count: config.files.length, ok: true });
      
    } catch (error) {
  tlog.error('download_all failed', { count: config.files.length, error: error?.message });
      
      if (onResponse) {
        onResponse({
          status: 'error',
          action: 'download_all',
          error: error.message,
          data: { fileCount: config.files.length, ui_tool_id, eventId, agent_message_id: agentMessageId },
          agentContext: { downloaded: false, type: 'bulk', error: true }
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
        agentContext: { downloaded: false, cancelled: true }
      });
    }
  tlog.event('cancel', 'done');
  };

  return (
  <div className="file-download-center bg-gray-900 border border-cyan-500/30 rounded-lg p-4" data-agent-message-id={agentMessageId || undefined}>
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

// Component metadata for the dynamic UI system (MASTER_UI_TOOL_AGENT_PROMPT requirement)
export default FileDownloadCenter;
