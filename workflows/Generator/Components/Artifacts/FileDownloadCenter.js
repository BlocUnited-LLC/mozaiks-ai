// ==============================================================================
// FILE: workflows/Generator/Components/Artifacts/FileDownloadCenter.js
// DESCRIPTION: Artifact component for file downloads and management
// ==============================================================================

import React, { useState, useEffect } from 'react';

const FileDownloadCenter = ({ 
  files = [], 
  title = "Generated Files",
  onDownload,
  onDownloadAll 
}) => {
  const [downloadStatus, setDownloadStatus] = useState({});

  const handleDownload = async (fileId, filename) => {
    setDownloadStatus(prev => ({ ...prev, [fileId]: 'downloading' }));
    
    try {
      if (onDownload) {
        await onDownload(fileId, filename);
      }
      setDownloadStatus(prev => ({ ...prev, [fileId]: 'completed' }));
    } catch (error) {
      console.error('Download failed:', error);
      setDownloadStatus(prev => ({ ...prev, [fileId]: 'error' }));
    }
  };

  const handleDownloadAll = async () => {
    try {
      if (onDownloadAll) {
        await onDownloadAll();
      }
    } catch (error) {
      console.error('Download all failed:', error);
    }
  };

  return (
    <div className="file-download-center">
      <div className="download-header">
        <h3>{title}</h3>
        {files.length > 1 && (
          <button 
            className="download-all-btn"
            onClick={handleDownloadAll}
          >
            Download All
          </button>
        )}
      </div>
      
      <div className="file-list">
        {files.length === 0 ? (
          <div className="no-files">No files available for download</div>
        ) : (
          files.map((file) => (
            <div key={file.id} className="file-item">
              <div className="file-info">
                <span className="filename">{file.name}</span>
                <span className="file-size">{file.size || 'Unknown size'}</span>
              </div>
              
              <button
                className={`download-btn ${downloadStatus[file.id] || 'ready'}`}
                onClick={() => handleDownload(file.id, file.name)}
                disabled={downloadStatus[file.id] === 'downloading'}
              >
                {downloadStatus[file.id] === 'downloading' && 'Downloading...'}
                {downloadStatus[file.id] === 'completed' && '✓ Downloaded'}
                {downloadStatus[file.id] === 'error' && 'Retry'}
                {!downloadStatus[file.id] && 'Download'}
              </button>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default FileDownloadCenter;
