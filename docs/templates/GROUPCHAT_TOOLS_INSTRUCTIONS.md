# GroupchatTools Development Instructions

## Purpose
Create Python modules that handle backend responses from UI components and provide AG2 agents with tools for data persistence, file operations, and workflow-specific business logic.

## Template Structure

```python
"""
{TOOL_NAME} for {WORKFLOW_NAME} workflow
Handles {TOOL_PURPOSE} and component responses
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path

# Import workflow-specific context
from ..context_variables import {WORKFLOW_NAME}Context
from logs.logging_config import get_business_logger, log_business_event

logger = logging.getLogger(__name__)
business_logger = get_business_logger("{TOOL_NAME}")

class {TOOL_CLASS_NAME}:
    """
    {TOOL_DESCRIPTION}
    
    Responsibilities:
    - {RESPONSIBILITY_1}
    - {RESPONSIBILITY_2}
    - {RESPONSIBILITY_3}
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._initialize_connections()
    
    def _initialize_connections(self):
        """Initialize database connections, file paths, etc."""
        {INITIALIZATION_LOGIC}
    
    # Component response handlers
    {COMPONENT_HANDLERS}
    
    # AG2 tool functions  
    {AG2_TOOLS}
    
    # Helper methods
    {HELPER_METHODS}

# Tool registration for AG2
def get_tools() -> List[callable]:
    """Return list of tools for AG2 agent registration"""
    tool_instance = {TOOL_CLASS_NAME}()
    
    return [
        {TOOL_FUNCTION_LIST}
    ]
```

## Configuration Fields

### TOOL_NAME
- **Format**: snake_case (e.g., "api_manager", "file_handler", "data_processor")
- **Purpose**: Identifies the tool module
- **Example**: "api_manager" for handling API credential operations

### TOOL_CLASS_NAME
- **Format**: PascalCase (e.g., "APIManager", "FileHandler", "DataProcessor")  
- **Purpose**: Main class name for the tool
- **Convention**: Always end with descriptive noun

### TOOL_PURPOSE
- **Format**: Clear description of what the tool handles
- **Examples**: 
  - "API credential storage and validation"
  - "file generation and download management"
  - "user preference collection and persistence"

### COMPONENT_HANDLERS
Functions that process responses from UI components:

```python
async def handle_api_key_submission(
    self, 
    enterprise_id: str, 
    service: str, 
    api_key: str,
    context: {WORKFLOW_NAME}Context
) -> Dict[str, Any]:
    """
    Handle API key submission from APIKeyInput component
    
    Args:
        enterprise_id: User's enterprise ID
        service: API service name (e.g., "openai", "anthropic")
        api_key: The submitted API key
        context: Current workflow context
        
    Returns:
        Result dictionary with status and message
    """
    try:
        log_business_event(
            event_type="API_KEY_SUBMISSION",
            description=f"API key submitted for {service}",
            context={"enterprise_id": enterprise_id, "service": service}
        )
        
        # Validate API key format
        if not self._validate_api_key(service, api_key):
            return {
                "status": "error",
                "message": f"Invalid API key format for {service}"
            }
        
        # Store securely
        success = await self._store_api_key(enterprise_id, service, api_key)
        
        if success:
            # Update context
            context.api_credentials[service] = api_key
            context.workflow_stage = "api_configured"
            
            return {
                "status": "success", 
                "message": f"{service} API key stored successfully"
            }
        else:
            return {
                "status": "error",
                "message": "Failed to store API key"
            }
            
    except Exception as e:
        logger.error(f"Error handling API key submission: {e}")
        return {
            "status": "error",
            "message": f"Internal error: {str(e)}"
        }

async def handle_file_download_request(
    self,
    file_data: Dict[str, Any],
    context: {WORKFLOW_NAME}Context
) -> Dict[str, Any]:
    """
    Handle file download request from FileDownloadCenter component
    
    Args:
        file_data: File information and content
        context: Current workflow context
        
    Returns:
        Download URL and metadata
    """
    try:
        file_name = file_data.get("name")
        file_content = file_data.get("content")
        
        if not file_name or not file_content:
            return {
                "status": "error",
                "message": "Invalid file data"
            }
        
        # Generate download URL
        download_url = await self._create_download_url(file_name, file_content)
        
        # Log business event
        log_business_event(
            event_type="FILE_DOWNLOAD_REQUESTED",
            description=f"Download requested for {file_name}",
            context={"file_name": file_name, "file_size": len(file_content)}
        )
        
        # Update context
        context.download_urls[file_name] = download_url
        
        return {
            "status": "success",
            "download_url": download_url,
            "expires_at": (datetime.now() + timedelta(hours=24)).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error handling file download: {e}")
        return {
            "status": "error",
            "message": f"Download failed: {str(e)}"
        }
```

### AG2_TOOLS
Functions that AG2 agents can call directly:

```python
async def store_user_preferences(
    self,
    user_id: str,
    preferences: Dict[str, Any],
    context: {WORKFLOW_NAME}Context
) -> str:
    """
    AG2 tool: Store user preferences
    
    Args:
        user_id: User identifier
        preferences: User preference dictionary
        context: Workflow context
        
    Returns:
        Status message for agent
    """
    try:
        # Validate preferences
        validation_errors = self._validate_preferences(preferences)
        if validation_errors:
            return f"Invalid preferences: {', '.join(validation_errors)}"
        
        # Store in database
        success = await self._save_preferences(user_id, preferences)
        
        if success:
            # Update context
            context.user_preferences.update(preferences)
            return "User preferences saved successfully"
        else:
            return "Failed to save user preferences"
            
    except Exception as e:
        logger.error(f"Error storing preferences: {e}")
        return f"Error saving preferences: {str(e)}"

async def generate_content_files(
    self,
    content_specs: List[Dict[str, Any]],
    context: {WORKFLOW_NAME}Context
) -> str:
    """
    AG2 tool: Generate downloadable files from content specifications
    
    Args:
        content_specs: List of content specifications
        context: Workflow context
        
    Returns:
        Status message with file count
    """
    try:
        generated_files = []
        
        for spec in content_specs:
            file_data = await self._generate_file(spec)
            if file_data:
                generated_files.append(file_data)
        
        if generated_files:
            # Update context with generated files
            context.generated_files.extend(generated_files)
            
            # Log business event
            log_business_event(
                event_type="FILES_GENERATED",
                description=f"Generated {len(generated_files)} files",
                context={"file_count": len(generated_files)}
            )
            
            return f"Successfully generated {len(generated_files)} files"
        else:
            return "No files were generated"
            
    except Exception as e:
        logger.error(f"Error generating files: {e}")
        return f"File generation failed: {str(e)}"
```

## Tool Categories

### 1. Data Management Tools
Handle database operations and data persistence:

```python
class DataManager:
    """Handles database operations for workflow data"""
    
    async def store_entity(self, entity_type: str, data: Dict[str, Any]) -> str:
        """Store entity in database"""
        pass
    
    async def retrieve_entity(self, entity_type: str, entity_id: str) -> Dict[str, Any]:
        """Retrieve entity from database"""
        pass
    
    async def update_entity(self, entity_type: str, entity_id: str, updates: Dict[str, Any]) -> bool:
        """Update existing entity"""
        pass
    
    async def delete_entity(self, entity_type: str, entity_id: str) -> bool:
        """Delete entity from database"""
        pass
```

### 2. File Operations Tools
Handle file creation, storage, and download management:

```python
class FileManager:
    """Handles file operations and download management"""
    
    async def create_file(self, filename: str, content: str, format: str = "text") -> Dict[str, Any]:
        """Create file with specified content"""
        pass
    
    async def create_zip_archive(self, files: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Create ZIP archive from multiple files"""
        pass
    
    async def generate_download_url(self, file_path: str, expires_hours: int = 24) -> str:
        """Generate temporary download URL"""
        pass
    
    async def cleanup_expired_files(self) -> int:
        """Clean up expired temporary files"""
        pass
```

### 3. API Integration Tools
Handle external API calls and credential management:

```python
class APIManager:
    """Handles API credentials and external service integration"""
    
    async def validate_api_key(self, service: str, api_key: str) -> bool:
        """Validate API key with service"""
        pass
    
    async def make_api_call(self, service: str, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Make authenticated API call"""
        pass
    
    async def get_service_status(self, service: str) -> Dict[str, Any]:
        """Check service availability and rate limits"""
        pass
    
    async def rotate_api_key(self, service: str, old_key: str, new_key: str) -> bool:
        """Rotate API key"""
        pass
```

### 4. Processing Tools
Handle business logic and data transformation:

```python
class ContentProcessor:
    """Handles content generation and processing"""
    
    async def generate_content(self, prompt: str, style: str, length: int) -> str:
        """Generate content using specified parameters"""
        pass
    
    async def validate_content(self, content: str, requirements: List[str]) -> Dict[str, Any]:
        """Validate generated content against requirements"""
        pass
    
    async def format_content(self, content: str, output_format: str) -> str:
        """Format content for specific output type"""
        pass
    
    async def optimize_content(self, content: str, optimization_type: str) -> str:
        """Optimize content for SEO, readability, etc."""
        pass
```

## Error Handling Patterns

### Graceful Degradation
```python
async def robust_operation(self, data: Dict[str, Any]) -> Dict[str, Any]:
    """Operation with multiple fallback strategies"""
    
    # Primary strategy
    try:
        result = await self._primary_method(data)
        return {"status": "success", "result": result, "method": "primary"}
    except PrimaryMethodError as e:
        logger.warning(f"Primary method failed: {e}, trying fallback")
    
    # Fallback strategy
    try:
        result = await self._fallback_method(data)
        return {"status": "success", "result": result, "method": "fallback"}
    except FallbackMethodError as e:
        logger.warning(f"Fallback method failed: {e}, using basic method")
    
    # Basic strategy
    try:
        result = await self._basic_method(data)
        return {"status": "partial", "result": result, "method": "basic"}
    except Exception as e:
        logger.error(f"All methods failed: {e}")
        return {"status": "error", "message": str(e)}
```

### Validation and Sanitization
```python
def _validate_input(self, data: Dict[str, Any], schema: Dict[str, Any]) -> List[str]:
    """Validate input data against schema"""
    errors = []
    
    # Check required fields
    required_fields = schema.get("required", [])
    for field in required_fields:
        if field not in data or data[field] is None:
            errors.append(f"Required field '{field}' is missing")
    
    # Check field types and constraints
    for field, constraints in schema.get("fields", {}).items():
        if field in data:
            value = data[field]
            
            # Type validation
            expected_type = constraints.get("type")
            if expected_type and not isinstance(value, expected_type):
                errors.append(f"Field '{field}' must be of type {expected_type.__name__}")
            
            # Length validation
            if isinstance(value, str):
                min_length = constraints.get("min_length")
                max_length = constraints.get("max_length")
                
                if min_length and len(value) < min_length:
                    errors.append(f"Field '{field}' must be at least {min_length} characters")
                
                if max_length and len(value) > max_length:
                    errors.append(f"Field '{field}' must be at most {max_length} characters")
            
            # Pattern validation
            pattern = constraints.get("pattern")
            if pattern and isinstance(value, str):
                import re
                if not re.match(pattern, value):
                    errors.append(f"Field '{field}' format is invalid")
    
    return errors

def _sanitize_input(self, data: Dict[str, Any]) -> Dict[str, Any]:
    """Sanitize input data"""
    sanitized = {}
    
    for key, value in data.items():
        if isinstance(value, str):
            # Remove potentially dangerous characters
            sanitized[key] = value.strip()
            # Additional sanitization based on field type
            if key.endswith("_email"):
                sanitized[key] = value.lower()
            elif key.endswith("_phone"):
                sanitized[key] = re.sub(r'[^\d+\-\(\)\s]', '', value)
        else:
            sanitized[key] = value
    
    return sanitized
```

## Security Considerations

### API Key Handling
```python
import hashlib
from cryptography.fernet import Fernet

class SecureKeyManager:
    """Secure API key storage and retrieval"""
    
    def __init__(self, encryption_key: bytes):
        self.cipher = Fernet(encryption_key)
    
    def encrypt_api_key(self, api_key: str) -> str:
        """Encrypt API key for storage"""
        return self.cipher.encrypt(api_key.encode()).decode()
    
    def decrypt_api_key(self, encrypted_key: str) -> str:
        """Decrypt API key for use"""
        return self.cipher.decrypt(encrypted_key.encode()).decode()
    
    def hash_key_for_lookup(self, api_key: str) -> str:
        """Create hash for key lookup without storing plaintext"""
        return hashlib.sha256(api_key.encode()).hexdigest()[:16]
```

### Input Validation
```python
def validate_file_upload(self, file_data: Dict[str, Any]) -> List[str]:
    """Validate file upload for security"""
    errors = []
    
    # Check file size
    max_size = 10 * 1024 * 1024  # 10MB
    if len(file_data.get("content", "")) > max_size:
        errors.append("File size exceeds maximum limit")
    
    # Check file type
    allowed_extensions = {".txt", ".json", ".csv", ".md", ".py", ".js"}
    filename = file_data.get("name", "")
    file_ext = Path(filename).suffix.lower()
    
    if file_ext not in allowed_extensions:
        errors.append(f"File type '{file_ext}' not allowed")
    
    # Check filename for path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        errors.append("Invalid filename")
    
    return errors
```

## Performance Optimization

### Caching Strategies
```python
from functools import lru_cache
import asyncio

class CachedTool:
    """Tool with caching for expensive operations"""
    
    def __init__(self):
        self._cache = {}
        self._cache_ttl = 300  # 5 minutes
    
    async def expensive_operation(self, key: str) -> Any:
        """Cached expensive operation"""
        
        # Check cache
        if key in self._cache:
            cached_data, timestamp = self._cache[key]
            if time.time() - timestamp < self._cache_ttl:
                return cached_data
        
        # Perform operation
        result = await self._perform_expensive_operation(key)
        
        # Cache result
        self._cache[key] = (result, time.time())
        
        return result
    
    @lru_cache(maxsize=100)
    def sync_expensive_operation(self, key: str) -> Any:
        """LRU cached synchronous operation"""
        return self._perform_sync_operation(key)
```

### Batch Operations
```python
async def batch_process_items(self, items: List[Dict[str, Any]], batch_size: int = 10) -> List[Dict[str, Any]]:
    """Process items in batches for better performance"""
    results = []
    
    for i in range(0, len(items), batch_size):
        batch = items[i:i + batch_size]
        
        # Process batch concurrently
        batch_tasks = [self._process_single_item(item) for item in batch]
        batch_results = await asyncio.gather(*batch_tasks, return_exceptions=True)
        
        # Handle results and exceptions
        for result in batch_results:
            if isinstance(result, Exception):
                logger.error(f"Batch processing error: {result}")
                results.append({"status": "error", "error": str(result)})
            else:
                results.append(result)
    
    return results
```

## Testing Patterns

### Unit Testing
```python
import pytest
from unittest.mock import AsyncMock, patch

class TestMyTool:
    """Test cases for MyTool"""
    
    @pytest.fixture
    def tool_instance(self):
        """Create tool instance for testing"""
        return MyTool(config={"test_mode": True})
    
    @pytest.mark.asyncio
    async def test_handle_api_key_submission_success(self, tool_instance):
        """Test successful API key submission"""
        
        # Mock dependencies
        with patch.object(tool_instance, '_validate_api_key', return_value=True), \
             patch.object(tool_instance, '_store_api_key', return_value=True):
            
            # Create test context
            context = WorkflowContext()
            
            # Call method
            result = await tool_instance.handle_api_key_submission(
                enterprise_id="test_123",
                service="openai",
                api_key="sk-test123",
                context=context
            )
            
            # Verify result
            assert result["status"] == "success"
            assert "openai" in context.api_credentials
    
    @pytest.mark.asyncio
    async def test_handle_api_key_submission_invalid_key(self, tool_instance):
        """Test API key submission with invalid key"""
        
        # Mock validation to return False
        with patch.object(tool_instance, '_validate_api_key', return_value=False):
            
            context = WorkflowContext()
            
            result = await tool_instance.handle_api_key_submission(
                enterprise_id="test_123",
                service="openai", 
                api_key="invalid_key",
                context=context
            )
            
            assert result["status"] == "error"
            assert "Invalid API key format" in result["message"]
```

## Best Practices

1. **Single Responsibility**: Each tool should handle one specific domain
2. **Error Handling**: Always provide meaningful error messages
3. **Logging**: Log business events and errors for debugging
4. **Validation**: Validate all inputs before processing
5. **Security**: Encrypt sensitive data and validate file uploads
6. **Performance**: Use caching and batch operations for efficiency
7. **Testing**: Write comprehensive unit tests for all methods
8. **Documentation**: Include detailed docstrings and type hints
9. **Context Updates**: Always update workflow context appropriately
10. **Graceful Degradation**: Provide fallback strategies for failures

## LLM Generation Prompt

```
Create a GroupchatTool for a {WORKFLOW_TYPE} workflow.

Tool Purpose: {TOOL_DESCRIPTION}
Component Handlers: {COMPONENT_RESPONSE_TYPES}
AG2 Tools: {AGENT_TOOL_REQUIREMENTS}
Data Storage: {DATA_PERSISTENCE_NEEDS}
External APIs: {API_INTEGRATION_REQUIREMENTS}

Generate complete tool class with error handling, validation, and testing patterns.
```
