# E2B/Monaco Integration Guide for Natural Language App Development Platform
## Building a Bolt.new/Lovable-style Experience in MozaiksAI

This guide shows how to set up E2B sandboxes with Monaco Editor for a complete natural language app development experience where users can:
1. Chat with AI to describe their app
2. See code generated in real-time in Monaco Editor
3. View live preview of their app running in E2B sandbox
4. Iterate and deploy their app

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      CHAT + CODE INTERFACE                      │
│  ┌─────────────────────┐  ┌─────────────────────────────────┐   │
│  │   Chat Panel        │  │        Artifact Workspace        │   │
│  │                     │  │  ┌─────────────┐ ┌─────────────┐ │   │
│  │ User: "Create a     │  │  │   Monaco    │ │   Live      │ │   │
│  │ React todo app"     │  │  │   Editor    │ │   Preview   │ │   │
│  │                     │  │  │  (Code)     │ │  (E2B App)  │ │   │
│  │ AI: "I'll create... │  │  └─────────────┘ └─────────────┘ │   │
│  │ [code appears] →────┼──┼──→ Auto-sync ←─→ Hot reload    │   │
│  └─────────────────────┘  └─────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                                    │
┌─────────────────────────────────────────────────────────────────┐
│                        E2B SANDBOX LAYER                        │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │   Node.js/React │  │   Python/Flask  │  │   Full Stack    │  │
│  │    Template     │  │    Template     │  │    Template     │  │
│  │                 │  │                 │  │                 │  │
│  │ • Live reload   │  │ • Hot reload    │  │ • Multi-service │  │
│  │ • Package mgmt  │  │ • Pip install   │  │ • Database      │  │
│  │ • Port forward  │  │ • Port forward  │  │ • Port forward  │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Step 1: E2B Account and API Setup

### 1.1 Get E2B Access
```bash
# Sign up at https://e2b.dev
# Get your API key from dashboard
export E2B_API_KEY="your_api_key_here"
```

### 1.2 Install E2B SDK
```bash
# In your project directory
pip install e2b
npm install @e2b/sdk  # For frontend if needed
```

### 1.3 Configure E2B in MozaiksAI
Add to your `core/config.py`:
```python
# E2B Configuration
E2B_API_KEY = os.getenv("E2B_API_KEY")
E2B_TEMPLATES = {
    "react": "e2b-react-template",
    "python": "e2b-python-template", 
    "fullstack": "e2b-fullstack-template"
}
```

## Step 2: Enhanced E2B Plugin Implementation

### 2.1 Update E2B Plugin with Real Implementation
The current E2B plugin (`plugins/e2b_plugin/__init__.py`) needs these enhancements:

```python
# Add to E2BCodeExecutionPlugin class

async def create_sandbox(self, template: str = "react") -> Dict[str, Any]:
    """Create a new E2B sandbox"""
    if not self.api_key:
        return {"error": "E2B API key required"}
    
    try:
        from e2b import Sandbox
        
        sandbox = await Sandbox.create(template=template)
        session_id = f"e2b_{sandbox.id}"
        
        self.sessions[session_id] = {
            "sandbox": sandbox,
            "template": template,
            "created_at": datetime.now(),
            "status": "running"
        }
        
        return {
            "session_id": session_id,
            "sandbox_id": sandbox.id,
            "url": f"https://{sandbox.id}.e2b.dev",
            "template": template,
            "status": "ready"
        }
    except Exception as e:
        logger.error(f"Failed to create E2B sandbox: {e}")
        return {"error": str(e)}

async def write_file(self, session_id: str, file_path: str, content: str) -> Dict[str, Any]:
    """Write file to E2B sandbox"""
    session = self.sessions.get(session_id)
    if not session:
        return {"error": "Session not found"}
    
    try:
        sandbox = session["sandbox"]
        await sandbox.files.write(file_path, content)
        
        return {
            "success": True,
            "file_path": file_path,
            "size": len(content)
        }
    except Exception as e:
        return {"error": str(e)}

async def run_command(self, session_id: str, command: str) -> Dict[str, Any]:
    """Run command in E2B sandbox"""
    session = self.sessions.get(session_id)
    if not session:
        return {"error": "Session not found"}
    
    try:
        sandbox = session["sandbox"]
        result = await sandbox.process.run(command)
        
        return {
            "success": True,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.exit_code
        }
    except Exception as e:
        return {"error": str(e)}
```

### 2.2 Add E2B Service Layer
Create `core/services/e2b_service.py`:

```python
"""
E2B Service - High-level interface for E2B sandbox management
"""
from typing import Dict, Any, Optional
import asyncio
import json
from plugins.e2b_plugin import E2BCodeExecutionPlugin

class E2BService:
    def __init__(self):
        self.plugin = E2BCodeExecutionPlugin()
        self.plugin.initialize({"e2b_api_key": os.getenv("E2B_API_KEY")})
    
    async def create_app_sandbox(self, app_type: str = "react") -> Dict[str, Any]:
        """Create sandbox for app development"""
        return await self.plugin.create_sandbox(template=app_type)
    
    async def deploy_app(self, session_id: str, files: Dict[str, str]) -> Dict[str, Any]:
        """Deploy app files to sandbox"""
        results = []
        
        for file_path, content in files.items():
            result = await self.plugin.write_file(session_id, file_path, content)
            results.append(result)
        
        # Start the development server
        if "package.json" in files:
            # React/Node.js app
            await self.plugin.run_command(session_id, "npm install")
            start_result = await self.plugin.run_command(session_id, "npm start")
        elif "requirements.txt" in files:
            # Python app
            await self.plugin.run_command(session_id, "pip install -r requirements.txt")
            start_result = await self.plugin.run_command(session_id, "python app.py")
        
        return {
            "deployment": results,
            "server": start_result,
            "status": "deployed"
        }
```

## Step 3: Frontend Monaco Editor Integration

### 3.1 Install Monaco Editor
```bash
cd ChatUI
npm install monaco-editor @monaco-editor/react
```

### 3.2 Create Monaco Artifact Component
Create `ChatUI/src/components/MonacoArtifact.js`:

```javascript
import React, { useState, useEffect, useRef } from 'react';
import { Editor } from '@monaco-editor/react';

const MonacoArtifact = ({ artifact, onCodeChange, onDeploy }) => {
  const [activeFile, setActiveFile] = useState('src/App.js');
  const [files, setFiles] = useState(artifact.files || {});
  const [previewUrl, setPreviewUrl] = useState(null);
  const [isDeploying, setIsDeploying] = useState(false);
  
  const editorRef = useRef(null);

  useEffect(() => {
    // Auto-deploy when files change
    if (Object.keys(files).length > 0) {
      const debounceTimer = setTimeout(() => {
        handleDeploy();
      }, 2000); // 2 second debounce
      
      return () => clearTimeout(debounceTimer);
    }
  }, [files]);

  const handleEditorDidMount = (editor, monaco) => {
    editorRef.current = editor;
    
    // Configure Monaco for React/TypeScript
    monaco.languages.typescript.typescriptDefaults.setCompilerOptions({
      jsx: monaco.languages.typescript.JsxEmit.React,
      target: monaco.languages.typescript.ScriptTarget.ES2020,
      allowNonTsExtensions: true,
    });
  };

  const handleCodeChange = (value) => {
    const newFiles = {
      ...files,
      [activeFile]: value
    };
    setFiles(newFiles);
    onCodeChange?.(newFiles);
  };

  const handleDeploy = async () => {
    if (isDeploying) return;
    
    setIsDeploying(true);
    try {
      const result = await onDeploy(files);
      if (result.sandbox_url) {
        setPreviewUrl(result.sandbox_url);
      }
    } catch (error) {
      console.error('Deployment failed:', error);
    } finally {
      setIsDeploying(false);
    }
  };

  return (
    <div className="monaco-artifact h-full flex">
      {/* File Explorer */}
      <div className="w-64 bg-gray-800 border-r border-gray-700">
        <div className="p-3 border-b border-gray-700">
          <h3 className="text-sm font-medium text-white">Files</h3>
        </div>
        <div className="p-2">
          {Object.keys(files).map(filename => (
            <div
              key={filename}
              className={`p-2 text-sm cursor-pointer rounded $\{
                activeFile === filename 
                  ? 'bg-blue-600 text-white' 
                  : 'text-gray-300 hover:bg-gray-700'
              }`}
              onClick={() => setActiveFile(filename)}
            >
              {filename}
            </div>
          ))}
        </div>
      </div>

      {/* Editor Panel */}
      <div className="flex-1 flex flex-col">
        <div className="h-1/2 border-b border-gray-700">
          <div className="flex items-center justify-between p-2 bg-gray-800 border-b border-gray-700">
            <span className="text-sm text-gray-300">{activeFile}</span>
            <button
              onClick={handleDeploy}
              disabled={isDeploying}
              className="px-3 py-1 bg-blue-600 text-white rounded text-sm hover:bg-blue-700 disabled:opacity-50"
            >
              {isDeploying ? 'Deploying...' : 'Deploy'}
            </button>
          </div>
          <Editor
            height="100%"
            language={getLanguageFromFile(activeFile)}
            value={files[activeFile] || ''}
            onChange={handleCodeChange}
            onMount={handleEditorDidMount}
            theme="vs-dark"
            options={{
              minimap: { enabled: false },
              lineNumbers: 'on',
              wordWrap: 'on',
              automaticLayout: true,
              suggestOnTriggerCharacters: true,
              quickSuggestions: true,
            }}
          />
        </div>

        {/* Live Preview */}
        <div className="h-1/2 bg-white">
          <div className="p-2 bg-gray-800 border-b border-gray-700">
            <span className="text-sm text-gray-300">Live Preview</span>
            {previewUrl && (
              <a 
                href={previewUrl} 
                target="_blank" 
                rel="noopener noreferrer"
                className="ml-2 text-blue-400 hover:text-blue-300"
              >
                Open in new tab ↗
              </a>
            )}
          </div>
          {previewUrl ? (
            <iframe
              src={previewUrl}
              className="w-full h-full border-0"
              title="App Preview"
            />
          ) : (
            <div className="flex items-center justify-center h-full text-gray-500">
              Deploy your app to see the preview
            </div>
          )}
        </div>
      </div>
    </div>
  );
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

export default MonacoArtifact;
```

## Step 4: Backend Integration

### 4.1 Update Artifact Router
Modify `core/ui/dynamic_artifacts.py` to handle E2B deployment:

```python
async def deploy_to_e2b(self, artifact_data: Dict[str, Any]) -> Dict[str, Any]:
    """Deploy artifact to E2B sandbox"""
    from core.services.e2b_service import E2BService
    
    e2b_service = E2BService()
    
    # Determine app type from artifact
    app_type = self._detect_app_type(artifact_data)
    
    # Create sandbox
    sandbox_result = await e2b_service.create_app_sandbox(app_type)
    if "error" in sandbox_result:
        return sandbox_result
    
    # Deploy files
    files = artifact_data.get("files", {})
    deploy_result = await e2b_service.deploy_app(
        sandbox_result["session_id"], 
        files
    )
    
    return {
        "sandbox_id": sandbox_result["sandbox_id"],
        "sandbox_url": sandbox_result["url"],
        "deployment": deploy_result,
        "status": "deployed"
    }

def _detect_app_type(self, artifact_data: Dict[str, Any]) -> str:
    """Detect app type from artifact data"""
    files = artifact_data.get("files", {})
    
    if "package.json" in files:
        return "react"
    elif "requirements.txt" in files or any(f.endswith(".py") for f in files):
        return "python"
    else:
        return "react"  # Default
```

### 4.2 Add WebSocket Events for E2B
Update `core/ui/ag_ui_events.py`:

```python
class E2BDeploymentEvent(BaseAGUIEvent):
    """Event for E2B deployment updates"""
    type: Literal[EventType.CUSTOM] = EventType.CUSTOM
    name: Literal["e2b_deployment"] = "e2b_deployment"
    sandbox_id: str
    sandbox_url: str
    status: str
    files: Dict[str, Any]

class E2BPreviewEvent(BaseAGUIEvent):
    """Event for E2B preview updates"""
    type: Literal[EventType.CUSTOM] = EventType.CUSTOM
    name: Literal["e2b_preview"] = "e2b_preview"
    sandbox_id: str
    preview_url: str
    ready: bool
```

## Step 5: Chat Integration for Natural Language Development

### 5.1 Update LLM Service for App Generation
Add to `core/config.py` LLMService:

```python
async def generate_app_code(self, description: str, app_type: str = "react") -> Dict[str, Any]:
    """Generate complete app code from description"""
    
    system_prompt = f"""You are an expert {app_type} developer. Generate a complete, working application based on the user's description.

    Return a JSON object with this structure:
    {{
        "files": {{
            "src/App.js": "// React component code...",
            "src/index.js": "// Entry point...",
            "package.json": "// Package configuration...",
            // ... other files
        }},
        "title": "App Name",
        "description": "Brief description",
        "category": "app"
    }}

    Make sure the app is:
    - Complete and runnable
    - Uses modern best practices
    - Includes all necessary dependencies
    - Has proper error handling
    - Includes basic styling
    """

    user_prompt = f"Create a {app_type} application: {description}"

    response = await self.client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.1
    )

    try:
        return json.loads(response.choices[0].message.content)
    except json.JSONDecodeError:
        # Fallback if LLM doesn't return valid JSON
        return {
            "files": {
                "src/App.js": "// Error generating app code",
            },
            "title": "Generated App",
            "description": description,
            "category": "app"
        }
```

### 5.2 Update GroupChat for App Generation
Modify `core/scalable_groupchat.py`:

```python
async def handle_app_generation_request(self, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
    """Handle request to generate an app"""
    
    # Use LLM to generate app code
    app_data = await self.llm_service.generate_app_code(message)
    
    # Create artifact
    artifact_response = await self.dynamic_artifacts.route_to_artifact(
        app_data, 
        context
    )
    
    # Deploy to E2B if configured
    if os.getenv("E2B_API_KEY"):
        deployment = await self.dynamic_artifacts.deploy_to_e2b(app_data)
        artifact_response["deployment"] = deployment
    
    return artifact_response
```

## Step 6: Full Integration Flow

### 6.1 User Experience Flow
1. **User Input**: "Create a React todo app with local storage"
2. **LLM Analysis**: Determines this needs an artifact workspace
3. **Code Generation**: LLM generates complete React app files
4. **Artifact Creation**: Creates Monaco editor with generated code
5. **E2B Deployment**: Automatically deploys to E2B sandbox
6. **Live Preview**: Shows running app in iframe
7. **Iteration**: User can modify code and see live updates

### 6.2 Test the Complete Flow
Create `test_e2b_integration.py`:

```python
"""Test E2B integration end-to-end"""
import asyncio
from core.services.e2b_service import E2BService

async def test_full_app_creation():
    """Test creating and deploying a React app"""
    
    # Sample React app files
    files = {
        "src/App.js": '''
import React, { useState } from 'react';
import './App.css';

function App() {
  const [count, setCount] = useState(0);

  return (
    <div className="App">
      <header className="App-header">
        <h1>Hello MozaiksAI!</h1>
        <button onClick={() => setCount(count + 1)}>
          Count: {count}
        </button>
      </header>
    </div>
  );
}

export default App;
        ''',
        "src/index.js": '''
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);
        ''',
        "package.json": '''
{
  "name": "MozaiksAI-app",
  "version": "0.1.0",
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-scripts": "5.0.1"
  },
  "scripts": {
    "start": "react-scripts start",
    "build": "react-scripts build"
  }
}
        '''
    }

    e2b_service = E2BService()
    
    print("🚀 Creating E2B sandbox...")
    sandbox = await e2b_service.create_app_sandbox("react")
    print(f"✅ Sandbox created: {sandbox}")
    
    print("📁 Deploying app files...")
    deployment = await e2b_service.deploy_app(sandbox["session_id"], files)
    print(f"✅ App deployed: {deployment}")
    
    print(f"🌐 App URL: {sandbox['url']}")

if __name__ == "__main__":
    asyncio.run(test_full_app_creation())
```

## Step 7: Production Deployment

### 7.1 Environment Configuration
```bash
# .env file
E2B_API_KEY=your_e2b_api_key
OPENAI_API_KEY=your_openai_key
```

### 7.2 Docker Configuration
Update `docker-compose.yml`:

```yaml
version: '3.8'
services:
  MozaiksAI-app:
    environment:
      - E2B_API_KEY=${E2B_API_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    # ... rest of config
```

## Summary

This integration gives you a complete Bolt.new/Lovable-style experience:

1. ✅ **E2B Plugin Fixed**: No more Protocol errors
2. 🚀 **Monaco Editor**: Real-time code editing
3. 🔄 **Live Preview**: Instant app preview in E2B sandbox
4. 🤖 **AI-Powered**: Natural language to working app
5. 📱 **Hot Reload**: Changes appear instantly
6. 🌐 **Full Stack**: Support for React, Python, and more

The system now supports the full natural language app development workflow that makes platforms like Bolt.new and Lovable so powerful for rapid prototyping and development!
