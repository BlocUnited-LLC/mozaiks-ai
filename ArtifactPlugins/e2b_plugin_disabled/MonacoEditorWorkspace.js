import React, { useState, useEffect, useRef } from 'react';
import { Editor } from '@monaco-editor/react';

/**
 * MonacoEditorWorkspace - Complete code development environment
 * 
 * This ONE component provides everything needed for code development:
 * - File explorer for managing multiple files
 * - Monaco editor for code editing with syntax highlighting
 * - Live preview via E2B sandbox integration
 * - Terminal output for build logs and errors
 * - Hot reload when files change
 * 
 * This is the simplified, realistic approach used by Bolt.new, Lovable, etc.
 */

const MonacoEditorWorkspace = ({ 
  files = {},
  onFileChange,
  onDeploy,
  sandboxUrl = null,
  isDeploying = false,
  buildLogs = [],
  title = "Code Workspace"
}) => {
  const [activeFile, setActiveFile] = useState('src/App.js');
  const [fileContents, setFileContents] = useState(files);
  const [showTerminal, setShowTerminal] = useState(false);
  const editorRef = useRef(null);

  // Auto-select first file if activeFile doesn't exist
  useEffect(() => {
    const fileList = Object.keys(fileContents);
    if (fileList.length > 0 && !fileContents[activeFile]) {
      setActiveFile(fileList[0]);
    }
  }, [fileContents, activeFile]);

  // Auto-deploy when files change (with debounce)
  useEffect(() => {
    const deployTimer = setTimeout(() => {
      if (Object.keys(fileContents).length > 0) {
        onDeploy?.(fileContents);
      }
    }, 2000); // 2 second debounce

    return () => clearTimeout(deployTimer);
  }, [fileContents, onDeploy]);

  const handleEditorDidMount = (editor, monaco) => {
    editorRef.current = editor;
    
    // Configure Monaco for better development experience
    monaco.languages.typescript.typescriptDefaults.setCompilerOptions({
      jsx: monaco.languages.typescript.JsxEmit.React,
      target: monaco.languages.typescript.ScriptTarget.ES2020,
      allowNonTsExtensions: true,
      moduleResolution: monaco.languages.typescript.ModuleResolutionKind.NodeJs,
    });

    // Add React types for better IntelliSense
    monaco.languages.typescript.typescriptDefaults.addExtraLib(
      'declare module "react";',
      'file:///node_modules/@types/react/index.d.ts'
    );
  };

  const handleCodeChange = (value) => {
    const newFiles = {
      ...fileContents,
      [activeFile]: value
    };
    setFileContents(newFiles);
    onFileChange?.(newFiles);
  };

  const getLanguageFromFile = (filename) => {
    const extension = filename.split('.').pop();
    const languageMap = {
      'js': 'javascript',
      'jsx': 'javascript', 
      'ts': 'typescript',
      'tsx': 'typescript',
      'css': 'css',
      'html': 'html',
      'json': 'json',
      'md': 'markdown',
      'py': 'python'
    };
    return languageMap[extension] || 'plaintext';
  };

  const getFileIcon = (filename) => {
    const extension = filename.split('.').pop();
    const iconMap = {
      'js': '📄',
      'jsx': '⚛️',
      'ts': '📘',
      'tsx': '⚛️',
      'css': '🎨',
      'html': '🌐',
      'json': '📋',
      'md': '📝',
      'py': '🐍'
    };
    return iconMap[extension] || '📄';
  };

  return (
    <div className="h-full flex flex-col bg-gray-900">
      {/* Header */}
      <div className="flex items-center justify-between p-4 bg-gray-800 border-b border-gray-700">
        <div className="flex items-center space-x-3">
          <div className="w-3 h-3 bg-cyan-400 rounded-full animate-pulse"></div>
          <h2 className="text-white font-bold oxanium">{title}</h2>
        </div>
        
        <div className="flex items-center space-x-2">
          <button
            onClick={() => setShowTerminal(!showTerminal)}
            className={`px-3 py-1 rounded text-sm techfont transition-all ${
              showTerminal 
                ? 'bg-cyan-600 text-white' 
                : 'bg-gray-600 text-gray-300 hover:bg-gray-500'
            }`}
          >
            Terminal
          </button>
          
          <div className={`px-3 py-1 rounded text-sm techfont ${
            isDeploying
              ? 'bg-yellow-600 text-white animate-pulse'
              : sandboxUrl
                ? 'bg-green-600 text-white'
                : 'bg-gray-600 text-gray-300'
          }`}>
            {isDeploying ? '🔄 Building...' : sandboxUrl ? '✅ Live' : '⏸️ Stopped'}
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="flex-1 flex">
        {/* File Explorer */}
        <div className="w-64 bg-gray-800 border-r border-gray-700 flex flex-col">
          <div className="p-3 border-b border-gray-700">
            <h3 className="text-sm font-medium text-white oxanium">Files</h3>
          </div>
          
          <div className="flex-1 overflow-y-auto">
            {Object.keys(fileContents).map(filename => (
              <div
                key={filename}
                className={`flex items-center space-x-2 p-2 text-sm cursor-pointer transition-all hover:bg-gray-700 ${
                  activeFile === filename 
                    ? 'bg-cyan-600 text-white' 
                    : 'text-gray-300'
                }`}
                onClick={() => setActiveFile(filename)}
              >
                <span className="text-base">{getFileIcon(filename)}</span>
                <span className="techfont">{filename}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Editor and Preview */}
        <div className="flex-1 flex flex-col">
          {/* Code Editor */}
          <div className={`${showTerminal ? 'h-1/2' : 'h-3/5'} border-b border-gray-700`}>
            <div className="flex items-center justify-between p-2 bg-gray-800 border-b border-gray-700">
              <span className="text-sm text-gray-300 techfont">{activeFile}</span>
              <span className="text-xs text-gray-500 techfont">
                {getLanguageFromFile(activeFile)}
              </span>
            </div>
            
            <Editor
              height="100%"
              language={getLanguageFromFile(activeFile)}
              value={fileContents[activeFile] || ''}
              onChange={handleCodeChange}
              onMount={handleEditorDidMount}
              theme="vs-dark"
              options={{
                minimap: { enabled: true },
                lineNumbers: 'on',
                wordWrap: 'on',
                automaticLayout: true,
                suggestOnTriggerCharacters: true,
                quickSuggestions: true,
                tabSize: 2,
                fontSize: 14,
                fontFamily: 'Fira Code, Monaco, Consolas, monospace',
                scrollBeyondLastLine: false,
                renderWhitespace: 'selection',
                bracketPairColorization: { enabled: true },
              }}
            />
          </div>

          {/* Live Preview */}
          <div className={`${showTerminal ? 'h-1/2' : 'h-2/5'} bg-white`}>
            <div className="p-2 bg-gray-800 border-b border-gray-700 flex items-center justify-between">
              <span className="text-sm text-gray-300 techfont">Live Preview</span>
              {sandboxUrl && (
                <a 
                  href={sandboxUrl} 
                  target="_blank" 
                  rel="noopener noreferrer"
                  className="text-cyan-400 hover:text-cyan-300 text-sm techfont"
                >
                  Open in new tab ↗
                </a>
              )}
            </div>
            
            {sandboxUrl ? (
              <iframe
                src={sandboxUrl}
                className="w-full h-full border-0"
                title="Live Preview"
                sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
              />
            ) : (
              <div className="flex items-center justify-center h-full text-gray-500 bg-gray-100">
                <div className="text-center">
                  <div className="text-4xl mb-2">🚀</div>
                  <p className="techfont">
                    {isDeploying ? 'Deploying your app...' : 'Deploy your app to see the preview'}
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Terminal (Optional) */}
      {showTerminal && (
        <div className="h-48 bg-black border-t border-gray-700">
          <div className="p-2 bg-gray-800 border-b border-gray-700">
            <span className="text-sm text-gray-300 techfont">Terminal Output</span>
          </div>
          
          <div className="h-full p-3 overflow-y-auto font-mono text-sm text-green-400">
            {buildLogs.length > 0 ? (
              buildLogs.map((log, index) => (
                <div key={index} className="mb-1">
                  <span className="text-gray-500">[{log.timestamp}]</span> {log.message}
                </div>
              ))
            ) : (
              <div className="text-gray-500">No output yet...</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default MonacoEditorWorkspace;
