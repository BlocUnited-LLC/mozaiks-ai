// AgentFileUpload - File upload component that agents can inject into chat

import React, { useState, useRef } from 'react';

const AgentFileUpload = ({ 
  agentId, 
  onAction,
  accept = "*/*",
  multiple = false,
  maxSize = 5 * 1024 * 1024, // 5MB default
  title = "Upload Files"
}) => {
  const [files, setFiles] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef(null);

  const handleFileSelect = (selectedFiles) => {
    const fileArray = Array.from(selectedFiles);
    const validFiles = fileArray.filter(file => {
      if (file.size > maxSize) {
        console.warn(`File ${file.name} is too large (${file.size} bytes)`);
        return false;
      }
      return true;
    });
    
    setFiles(multiple ? [...files, ...validFiles] : validFiles);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    handleFileSelect(e.dataTransfer.files);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setDragOver(true);
  };

  const handleDragLeave = () => {
    setDragOver(false);
  };

  const removeFile = (index) => {
    setFiles(files.filter((_, i) => i !== index));
  };

  const handleUpload = async () => {
    if (files.length === 0) return;
    
    setUploading(true);
    try {
      // Convert files to base64 for demo purposes
      const fileData = await Promise.all(
        files.map(async (file) => ({
          name: file.name,
          size: file.size,
          type: file.type,
          data: await fileToBase64(file)
        }))
      );

      await onAction({
        agentId,
        type: 'file_upload',
        data: { files: fileData },
        timestamp: Date.now()
      });
      
      setFiles([]);
    } catch (error) {
      console.error('Error uploading files:', error);
    } finally {
      setUploading(false);
    }
  };

  const fileToBase64 = (file) => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.readAsDataURL(file);
      reader.onload = () => resolve(reader.result);
      reader.onerror = error => reject(error);
    });
  };

  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  return (
    <div className="bg-black/40 backdrop-blur-lg border border-cyan-500/20 rounded-xl p-4 my-3 max-w-lg">
      <div className="flex items-center mb-4">
        <span className="text-cyan-400 text-xl mr-2">📁</span>
        <h4 className="text-cyan-300 font-semibold techfont">{title}</h4>
      </div>
      
      {/* Drop Zone */}
      <div
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => fileInputRef.current?.click()}
        className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-all ${
          dragOver 
            ? 'border-cyan-400 bg-cyan-400/10' 
            : 'border-cyan-500/30 hover:border-cyan-400/50 bg-black/20'
        }`}
      >
        <div className="text-center">
          <div className="text-4xl mb-4 text-cyan-400">📄</div>
          <div className="text-white font-semibold mb-2 techfont">
            Drop files here or click to browse
          </div>
          <div className="text-gray-400 text-sm techfont">
            Max size: {formatFileSize(maxSize)}
          </div>
        </div>
      </div>

      <input
        ref={fileInputRef}
        type="file"
        accept={accept}
        multiple={multiple}
        onChange={(e) => handleFileSelect(e.target.files)}
        className="hidden"
      />

      {/* File List */}
      {files.length > 0 && (
        <div className="mt-4 space-y-2">
          <h5 className="text-white font-semibold text-sm techfont mb-3">Selected Files:</h5>
          {files.map((file, index) => (
            <div key={index} className="flex items-center justify-between p-3 bg-black/40 rounded-lg border border-cyan-500/20">
              <div className="flex items-center space-x-3">
                <span className="text-2xl">📄</span>
                <div>
                  <div className="text-white font-medium techfont">{file.name}</div>
                  <div className="text-gray-400 text-sm techfont">{formatFileSize(file.size)}</div>
                </div>
              </div>
              <button
                onClick={() => removeFile(index)}
                className="text-red-400 hover:text-red-300 p-1 rounded hover:bg-red-400/10 transition-colors techfont font-bold"
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Upload Button */}
      {files.length > 0 && (
        <button
          onClick={handleUpload}
          disabled={uploading}
          className={`w-full mt-4 py-3 rounded-lg techfont font-bold transition-all ${
            uploading 
              ? 'bg-gray-600/80 text-gray-400 cursor-not-allowed' 
              : 'bg-gradient-to-r from-cyan-500/90 to-blue-500/90 text-white hover:from-cyan-400/90 hover:to-blue-400/90 hover:shadow-[0_0_20px_rgba(0,209,255,0.4)]'
          }`}
        >
          {uploading ? '⏳ UPLOADING...' : `🚀 UPLOAD ${files.length} FILE${files.length !== 1 ? 'S' : ''}`}
        </button>
      )}
    </div>
  );
};

export default AgentFileUpload;
