"""
Simplified Artifact System - No plugins, direct content management
"""

from typing import Dict, Any, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid
import logging

from ..events.simple_events import SimpleEvent, SimpleEventType

logger = logging.getLogger(__name__)


@dataclass
class SimpleArtifactMetadata:
    """Simplified artifact metadata"""
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    created_by_agent: str
    category: str = "general"
    version: int = 1
    tags: List[str] = field(default_factory=list)
    public: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "created_by_agent": self.created_by_agent,
            "version": self.version,
            "tags": self.tags,
            "public": self.public
        }


class SimpleArtifact:
    """Simplified artifact with direct content management"""
    
    def __init__(self, metadata: SimpleArtifactMetadata, content: str = ""):
        self.metadata = metadata
        self.content = content
        self._event_handlers: List[Callable] = []
    
    def update_content(self, content: str, agent_id: str) -> None:
        """Update artifact content"""
        self.content = content
        self.metadata.updated_at = datetime.now(timezone.utc)
        self.metadata.version += 1
        
        # Emit update event
        self._emit_update_event("content_updated", {
            "updated_by": agent_id,
            "content_length": len(content)
        })
    
    def update_metadata(self, **kwargs) -> None:
        """Update artifact metadata"""
        for key, value in kwargs.items():
            if hasattr(self.metadata, key):
                setattr(self.metadata, key, value)
        
        self.metadata.updated_at = datetime.now(timezone.utc)
        self._emit_update_event("metadata_updated", kwargs)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert artifact to dictionary for serialization"""
        return {
            "metadata": self.metadata.to_dict(),
            "content": self.content
        }
    
    def add_event_handler(self, handler: Callable) -> None:
        """Add event handler for artifact updates"""
        self._event_handlers.append(handler)
    
    def _emit_update_event(self, action: str, details: Dict[str, Any]) -> None:
        """Emit artifact update event using simple events"""
        event_data = {
            "artifact_id": self.metadata.id,
            "action": action,
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Create simple event
        event = SimpleEvent(
            type=SimpleEventType.ROUTE_TO_ARTIFACT,
            data=event_data,
            agent_name="artifact_system"
        )
        
        # Notify handlers
        for handler in self._event_handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Error in event handler: {e}")


class SimpleArtifactManager:
    """Simplified artifact manager without plugin system"""
    
    def __init__(self):
        self.artifacts: Dict[str, SimpleArtifact] = {}
        self._event_handlers: List[Callable] = []
        logger.info("Simple Artifact Manager initialized (no plugins needed)")
    
    def create_artifact(self, title: str, content: str = "", category: str = "general", agent_id: str = "unknown", **kwargs) -> SimpleArtifact:
        """Create a new simplified artifact"""
        artifact_id = str(uuid.uuid4())
        
        metadata = SimpleArtifactMetadata(
            id=artifact_id,
            title=title,
            category=category,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            created_by_agent=agent_id,
            **kwargs
        )
        
        artifact = SimpleArtifact(metadata, content)
        artifact.add_event_handler(self._handle_artifact_event)
        
        self.artifacts[artifact_id] = artifact
        
        # Emit creation event
        self._emit_manager_event("artifact_created", {
            "artifact_id": artifact_id,
            "title": title,
            "category": category,
            "created_by": agent_id
        })
        
        return artifact
    
    def get_artifact(self, artifact_id: str) -> Optional[SimpleArtifact]:
        """Get artifact by ID"""
        return self.artifacts.get(artifact_id)
    
    def update_artifact(self, artifact_id: str, content: Optional[str] = None, agent_id: str = "unknown", **metadata_updates) -> SimpleArtifact:
        """Update an existing artifact"""
        artifact = self.get_artifact(artifact_id)
        if not artifact:
            raise ValueError(f"Artifact not found: {artifact_id}")
        
        if content is not None:
            artifact.update_content(content, agent_id)
        
        if metadata_updates:
            artifact.update_metadata(**metadata_updates)
        
        return artifact
    
    def delete_artifact(self, artifact_id: str, agent_id: str = "unknown") -> None:
        """Delete an artifact"""
        if artifact_id not in self.artifacts:
            raise ValueError(f"Artifact not found: {artifact_id}")
        
        artifact = self.artifacts[artifact_id]
        del self.artifacts[artifact_id]
        
        # Emit deletion event
        self._emit_manager_event("artifact_deleted", {
            "artifact_id": artifact_id,
            "title": artifact.metadata.title,
            "deleted_by": agent_id
        })
    
    def list_artifacts(self, agent_id: Optional[str] = None, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """List artifacts with optional filtering"""
        artifacts = []
        
        for artifact in self.artifacts.values():
            # Filter by agent if specified
            if agent_id and artifact.metadata.created_by_agent != agent_id:
                continue
            
            # Filter by category if specified
            if category and artifact.metadata.category != category:
                continue
            
            artifacts.append(artifact.metadata.to_dict())
        
        return artifacts
    
    def add_event_handler(self, handler: Callable) -> None:
        """Add event handler for manager events"""
        self._event_handlers.append(handler)
    
    def _handle_artifact_event(self, event: SimpleEvent) -> None:
        """Handle events from artifacts"""
        for handler in self._event_handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Error in manager event handler: {e}")
    
    def _emit_manager_event(self, action: str, details: Dict[str, Any]) -> None:
        """Emit manager-level event using simple events"""
        event_data = {
            "action": action,
            "details": details,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        event = SimpleEvent(
            type=SimpleEventType.STATUS,
            data=event_data,
            agent_name="artifact_manager"
        )
        
        for handler in self._event_handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Error in manager event handler: {e}")


# Global simple artifact manager instance
simple_artifact_manager = SimpleArtifactManager()
