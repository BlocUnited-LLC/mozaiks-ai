"""
E2B Code Execution Plugin
Provides secure code execution capabilities through E2B
"""

from typing import Dict, Any, List
import logging

# Import the core plugin system
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from core.plugin_system import ContentTypePlugin, CapabilityPlugin

logger = logging.getLogger(__name__)


class E2BCodeExecutionPlugin(ContentTypePlugin, CapabilityPlugin):
    """Plugin for E2B-powered code execution environments"""
    
    def __init__(self):
        self.sessions = {}  # session_id -> e2b_session
        self.execution_history = {}  # session_id -> [executions]
    
    @property
    def name(self) -> str:
        return "e2b_code_execution"
    
    @property
    def version(self) -> str:
        return "1.0.0"
    
    @property
    def dependencies(self) -> List[str]:
        return ["e2b", "asyncio"]
    
    def initialize(self, context: Dict[str, Any]) -> None:
        """Initialize E2B client"""
        self.api_key = context.get("e2b_api_key")
        if not self.api_key:
            logger.warning("E2B API key not provided, plugin will work in simulation mode")
        logger.info("E2B Code Execution Plugin initialized")
    
    def cleanup(self) -> None:
        """Cleanup E2B sessions"""
        for session_id, session in self.sessions.items():
            try:
                # session.close()  # E2B session cleanup
                pass
            except Exception as e:
                logger.error(f"Error closing E2B session {session_id}: {e}")
        self.sessions.clear()
    
    # ContentTypePlugin methods
    def get_content_types(self) -> List[str]:
        return ["executable_code", "code_environment"]
    
    def create_content(self, content_type: str, data: Any, **kwargs) -> Any:
        """Create executable code content"""
        if content_type == "executable_code":
            return self._create_executable_code(data, **kwargs)
        elif content_type == "code_environment":
            return self._create_code_environment(data, **kwargs)
        else:
            raise ValueError(f"Unknown content type: {content_type}")
    
    def get_content_capabilities(self, content_type: str) -> List[str]:
        """Return capabilities for content type"""
        if content_type in ["executable_code", "code_environment"]:
            return ["executable", "interactive", "real_time", "collaborative", "persistent"]
        return []
    
    def get_renderer_config(self, content_type: str) -> Dict[str, Any]:
        """Return frontend renderer configuration"""
        if content_type == "executable_code":
            return {
                "component": "E2BCodeRunner",
                "props": {
                    "language": "auto",
                    "theme": "vs-dark",
                    "features": ["run", "debug", "terminal", "files"],
                    "environment": "isolated"
                },
                "assets": {
                    "css": ["e2b-runner.css", "monaco-editor.css"],
                    "js": ["e2b-client.js", "monaco-editor.js"]
                }
            }
        elif content_type == "code_environment":
            return {
                "component": "E2BEnvironment",
                "props": {
                    "features": ["terminal", "filesystem", "packages", "networking"],
                    "preset": "default",
                    "persistent": True
                },
                "assets": {
                    "css": ["e2b-environment.css", "terminal.css"],
                    "js": ["e2b-client.js", "xterm.js"]
                }
            }
        return {}
    
    # CapabilityPlugin methods
    def get_capabilities(self) -> List[str]:
        return ["execute_code", "manage_environment", "file_operations"]
    
    def handle_capability(self, capability: str, content: Any, action: str, **kwargs) -> Any:
        """Handle capability actions"""
        if capability == "execute_code":
            return self._handle_code_execution(content, action, **kwargs)
        elif capability == "manage_environment":
            return self._handle_environment_management(content, action, **kwargs)
        elif capability == "file_operations":
            return self._handle_file_operations(content, action, **kwargs)
        else:
            raise ValueError(f"Unknown capability: {capability}")
    
    def _create_executable_code(self, data: Any, **kwargs) -> Dict[str, Any]:
        """Create executable code content"""
        session_id = data.get("session_id") or f"session_{len(self.sessions)}"
        
        return {
            "type": "executable_code",
            "code": data.get("code", ""),
            "language": data.get("language", "python"),
            "session_id": session_id,
            "environment": data.get("environment", "python3"),
            "packages": data.get("packages", []),
            "metadata": {
                **kwargs,
                "execution_count": 0,
                "last_output": None,
                "status": "ready"
            }
        }
    
    def _create_code_environment(self, data: Any, **kwargs) -> Dict[str, Any]:
        """Create code environment content"""
        session_id = data.get("session_id") or f"env_{len(self.sessions)}"
        
        return {
            "type": "code_environment",
            "name": data.get("name", "default"),
            "session_id": session_id,
            "template": data.get("template", "python3"),
            "packages": data.get("packages", []),
            "files": data.get("files", {}),
            "environment_vars": data.get("environment_vars", {}),
            "metadata": {
                **kwargs,
                "status": "initializing",
                "uptime": 0,
                "last_activity": None
            }
        }
    
    def _handle_code_execution(self, content: Any, action: str, **kwargs) -> Any:
        """Handle code execution actions"""
        if action == "run":
            return self._execute_code(content, **kwargs)
        elif action == "stop":
            return self._stop_execution(content, **kwargs)
        elif action == "restart":
            return self._restart_session(content, **kwargs)
        else:
            raise ValueError(f"Unknown execution action: {action}")
    
    def _handle_environment_management(self, content: Any, action: str, **kwargs) -> Any:
        """Handle environment management actions"""
        if action == "create":
            return self._create_session(content, **kwargs)
        elif action == "destroy":
            return self._destroy_session(content, **kwargs)
        elif action == "install_package":
            return self._install_package(content, **kwargs)
        elif action == "list_packages":
            return self._list_packages(content, **kwargs)
        else:
            raise ValueError(f"Unknown environment action: {action}")
    
    def _handle_file_operations(self, content: Any, action: str, **kwargs) -> Any:
        """Handle file operations"""
        if action == "write":
            return self._write_file(content, **kwargs)
        elif action == "read":
            return self._read_file(content, **kwargs)
        elif action == "delete":
            return self._delete_file(content, **kwargs)
        elif action == "list":
            return self._list_files(content, **kwargs)
        else:
            raise ValueError(f"Unknown file action: {action}")
    
    def _execute_code(self, content: Any, **kwargs) -> Dict[str, Any]:
        """Execute code in E2B environment (simulated for now)"""
        session_id = content.get("session_id")
        code = kwargs.get("code", content.get("code", ""))
        
        logger.info(f"Executing code in session {session_id}")
        
        # Simulate code execution
        # In real implementation, this would use E2B client
        if not self.api_key:
            # Simulation mode
            result = {
                "success": True,
                "output": f"Simulated execution of: {code[:50]}...",
                "error": None,
                "execution_time": 0.1,
                "session_id": session_id
            }
        else:
            # Real E2B execution would go here
            # session = self._get_or_create_session(session_id)
            # result = session.run_code(code)
            result = {"success": False, "error": "E2B integration not implemented yet"}
        
        # Update execution history
        if session_id not in self.execution_history:
            self.execution_history[session_id] = []
        
        self.execution_history[session_id].append({
            "code": code,
            "result": result,
            "timestamp": kwargs.get("timestamp")
        })
        
        return result
    
    def _stop_execution(self, content: Any, **kwargs) -> Dict[str, Any]:
        """Stop code execution"""
        session_id = content.get("session_id")
        logger.info(f"Stopping execution in session {session_id}")
        
        return {"success": True, "message": "Execution stopped"}
    
    def _restart_session(self, content: Any, **kwargs) -> Dict[str, Any]:
        """Restart E2B session"""
        session_id = content.get("session_id")
        logger.info(f"Restarting session {session_id}")
        
        # Clear execution history
        self.execution_history[session_id] = []
        
        return {"success": True, "message": "Session restarted"}
    
    def _create_session(self, content: Any, **kwargs) -> Dict[str, Any]:
        """Create new E2B session"""
        session_id = content.get("session_id")
        template = content.get("template", "python3")
        
        logger.info(f"Creating E2B session {session_id} with template {template}")
        
        # Simulation mode
        self.sessions[session_id] = {
            "id": session_id,
            "template": template,
            "status": "running",
            "created_at": kwargs.get("timestamp")
        }
        
        return {"success": True, "session_id": session_id, "status": "running"}
    
    def _destroy_session(self, content: Any, **kwargs) -> Dict[str, Any]:
        """Destroy E2B session"""
        session_id = content.get("session_id")
        
        if session_id in self.sessions:
            del self.sessions[session_id]
        
        if session_id in self.execution_history:
            del self.execution_history[session_id]
        
        return {"success": True, "message": "Session destroyed"}
    
    def _install_package(self, content: Any, **kwargs) -> Dict[str, Any]:
        """Install package in environment"""
        package = kwargs.get("package")
        session_id = content.get("session_id")
        
        logger.info(f"Installing package {package} in session {session_id}")
        
        return {"success": True, "package": package, "installed": True}
    
    def _list_packages(self, content: Any, **kwargs) -> Dict[str, Any]:
        """List installed packages"""
        return {
            "success": True,
            "packages": ["numpy", "pandas", "matplotlib", "requests"]  # Simulated
        }
    
    def _write_file(self, content: Any, **kwargs) -> Dict[str, Any]:
        """Write file to environment"""
        filename = kwargs.get("filename")
        file_content = kwargs.get("content", "")
        
        return {"success": True, "filename": filename, "size": len(file_content)}
    
    def _read_file(self, content: Any, **kwargs) -> Dict[str, Any]:
        """Read file from environment"""
        filename = kwargs.get("filename")
        
        return {"success": True, "filename": filename, "content": "# File content here"}
    
    def _delete_file(self, content: Any, **kwargs) -> Dict[str, Any]:
        """Delete file from environment"""
        filename = kwargs.get("filename")
        
        return {"success": True, "filename": filename, "deleted": True}
    
    def _list_files(self, content: Any, **kwargs) -> Dict[str, Any]:
        """List files in environment"""
        return {
            "success": True,
            "files": [
                {"name": "main.py", "size": 1024, "modified": "2024-01-01T12:00:00Z"},
                {"name": "data.csv", "size": 2048, "modified": "2024-01-01T12:30:00Z"}
            ]
        }


# Plugin class that will be instantiated
class E2BPlugin(E2BCodeExecutionPlugin):
    pass
