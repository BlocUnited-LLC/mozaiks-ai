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
  files = [], 
  title = "Generated Files",
  toolId,
  eventId,
  workflowType,
  onResponse,
  componentId = "FileDownloadCenter"
}) => {
  const [downloadStatus, setDownloadStatus] = useState({});

  const handleDownload = async (fileId, filename) => {
    setDownloadStatus(prev => ({ ...prev, [fileId]: 'downloading' }));
    
    try {
      // Send response back to backend via event dispatcher
      const response = {
        status: 'success',
        action: 'download',
        data: {
          fileId: fileId,
          filename: filename,
          downloadTime: new Date().toISOString(),
          toolId,
          eventId,
          workflowType
        }
      };

      // Call the response handler from event dispatcher
      if (onResponse) {
        await onResponse(response);
      }
      
      setDownloadStatus(prev => ({ ...prev, [fileId]: 'completed' }));
      
      console.log(`✅ FileDownloadCenter: Downloaded ${filename}`);
      
    } catch (error) {
      console.error('❌ FileDownloadCenter: Download failed:', error);
      setDownloadStatus(prev => ({ ...prev, [fileId]: 'error' }));
      
      // Send error response
      if (onResponse) {
        onResponse({
          status: 'error',
          action: 'download',
          error: error.message,
          data: { fileId, filename, toolId, eventId }
        });
      }
    }
  };

  const handleDownloadAll = async () => {
    try {
      // Send bulk download response to backend
      const response = {
        status: 'success',
        action: 'download_all',
        data: {
          fileCount: files.length,
          files: files.map(f => ({ id: f.id, name: f.name, size: f.size })),
          downloadTime: new Date().toISOString(),
          toolId,
          eventId,
          workflowType
        }
      };

      if (onResponse) {
        await onResponse(response);
      }
      
      // Mark all files as downloaded
      const allDownloaded = {};
      files.forEach(file => {
        allDownloaded[file.id] = 'completed';
      });
      setDownloadStatus(allDownloaded);

      console.log(`✅ FileDownloadCenter: Downloaded all ${files.length} files`);
      
    } catch (error) {
      console.error('❌ FileDownloadCenter: Download all failed:', error);
      
      if (onResponse) {
        onResponse({
          status: 'error',
          action: 'download_all',
          error: error.message,
          data: { fileCount: files.length, toolId, eventId }
        });
      }
    }
  };

  const handleCancel = () => {
    if (onResponse) {
      onResponse({
        status: 'cancelled',
        action: 'cancel',
        data: { toolId, eventId, workflowType }
      });
    }
  };

  return (
    <div className="file-download-center bg-gray-900 border border-cyan-500/30 rounded-lg p-4">
      <div className="download-header flex justify-between items-center mb-4">
        <h3 className="text-cyan-400 text-lg font-semibold">{title}</h3>
        <div className="flex gap-2">
          {files.length > 1 && (
            <button 
              className="px-4 py-2 bg-cyan-600 hover:bg-cyan-700 text-white rounded transition-colors"
              onClick={handleDownloadAll}
            >
              Download All ({files.length})
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
      
      <div className="file-list space-y-2">
        {files.length === 0 ? (
          <div className="no-files text-gray-400 text-center py-8">
            No files available for download
          </div>
        ) : (
          files.map((file) => (
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
          <div>Tool: {toolId} | Event: {eventId} | Workflow: {workflowType}</div>
          <div>Files: {files.length} | Component: {componentId}</div>
        </div>
      )}
    </div>
  );
};

// Add display name for better debugging
FileDownloadCenter.displayName = 'FileDownloadCenter';

export default FileDownloadCenter;
