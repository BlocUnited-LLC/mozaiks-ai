"""
Workflow Dependency Manager

Manages application-level workflow dependency graphs and validates prerequisites
before workflow execution. Stores dependency relationships in WorkflowDependencies
collection and validates against ChatSessions runtime state.

Architecture:
- WorkflowDependencies collection: Application-level graph (one doc per enterprise)
- ChatSessions collection: Runtime workflow state (multiple docs per workflow)
- Validation: Query graph for prerequisites, check ChatSessions for completion status

Usage:
    from core.workflow.dependencies import dependency_manager
    
    # Validate before starting workflow
    is_valid, error = await dependency_manager.validate_workflow_dependencies(
        workflow_name="Build",
        enterprise_id="ent_123",
        user_id="user_456"
    )
    
    # Update graph when workflow generated
    await dependency_manager.update_workflow_graph(
        enterprise_id="ent_123",
        workflow_name="Build",
        dependencies={...},
        provides={...}
    )
"""

from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from core.data.models import WorkflowStatus
from core.data.persistence.persistence_manager import AG2PersistenceManager, PersistenceManager
import logging

logger = logging.getLogger(__name__)


class WorkflowDependencyManager:
    """Manages application-level workflow dependency graph and validation."""
    
    def __init__(self):
        """Initialize with PersistenceManager for MongoDB access."""
        self.pm = PersistenceManager()
        self.ag2_pm = AG2PersistenceManager()
        self._client: Optional[AsyncIOMotorClient] = None
        self._db = None
    
    async def _ensure_client(self):
        """Ensure MongoDB client is initialized."""
        if self._client is not None and self._db is not None:
            return

        await self.pm._ensure_client()
        if self.pm.client is None:
            raise RuntimeError("PersistenceManager failed to initialize Mongo client")

        # Reuse the existing PersistenceManager client/db to avoid parallel connections.
        self._client = self.pm.client
        if getattr(self.pm, "db2", None) is not None:
            self._db = self.pm.db2
        else:
            self._db = self._client["MozaiksAI"]
    
    async def _get_dependencies_collection(self):
        """Get WorkflowDependencies collection."""
        await self._ensure_client()
        return self._db["WorkflowDependencies"]
    
    async def get_workflow_graph(self, enterprise_id: str) -> Optional[Dict[str, Any]]:
        """
        Get complete workflow dependency graph for enterprise.
        
        Args:
            enterprise_id: Enterprise identifier
            
        Returns:
            Workflow graph document or None if not found
            
        Example:
            {
                "_id": ObjectId(...),
                "enterprise_id": "ent_123",
                "application_name": "Marketing Platform",
                "workflows": {
                    "Generator": {
                        "workflow_name": "Generator",
                        "created_at": "2025-11-09T...",
                        "status": "active",
                        "dependencies": {},
                        "provides": {
                            "context_vars": ["action_plan_approval"],
                            "artifacts": ["ActionPlan"]
                        }
                    }
                }
            }
        """
        coll = await self._get_dependencies_collection()
        doc = await coll.find_one({"enterprise_id": enterprise_id})
        return doc
    
    async def update_workflow_graph(
        self, 
        enterprise_id: str, 
        workflow_name: str,
        dependencies: Dict[str, Any]
    ):
        """
        Add or update workflow in dependency graph.
        
        Args:
            enterprise_id: Enterprise identifier
            workflow_name: Workflow name (e.g., "Generator", "Build")
            dependencies: Workflow prerequisites
                {
                    "required_workflows": [
                        {"workflow": "Generator", "status": "completed", "reason": "..."}
                    ],
                    "required_context_vars": [
                        {"variable": "action_plan_approval", "source_workflow": "Generator", "reason": "..."}
                    ],
                    "required_artifacts": [
                        {"artifact_type": "ActionPlan", "workflow": "Generator", "reason": "..."}
                    ]
                }
        """
        coll = await self._get_dependencies_collection()
        
        logger.info(f"Updating workflow graph: {workflow_name} in enterprise {enterprise_id}")
        
        # Upsert workflow entry
        await coll.update_one(
            {"enterprise_id": enterprise_id},
            {
                "$set": {
                    f"workflows.{workflow_name}": {
                        "workflow_name": workflow_name,
                        "created_at": datetime.utcnow().isoformat(),
                        "status": "active",
                        "dependencies": dependencies or {}
                    }
                }
            },
            upsert=True
        )
        
        logger.info(f"Workflow graph updated successfully for {workflow_name}")
    
    async def validate_workflow_dependencies(
        self,
        workflow_name: str,
        enterprise_id: str,
        user_id: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if workflow dependencies are satisfied.
        
        Validates workflow prerequisites by:
        1. Loading workflow graph from WorkflowDependencies collection
        2. Checking required_workflows completion status in ChatSessions
        3. Checking required_context_vars existence in ChatSessions context
        4. Checking required_artifacts persistence in ChatSessions last_artifact
        
        Args:
            workflow_name: Workflow to validate (e.g., "Build")
            enterprise_id: Enterprise identifier
            user_id: User identifier
            
        Returns:
            Tuple of (is_valid, error_message)
            - (True, None) if all dependencies met
            - (False, "error message") if dependencies not met
            
        Example:
            is_valid, error = await validate_workflow_dependencies(
                workflow_name="Build",
                enterprise_id="ent_123",
                user_id="user_456"
            )
            if not is_valid:
                return error_event(error)
        """
        logger.info(f"Validating dependencies for {workflow_name} (enterprise={enterprise_id}, user={user_id})")
        
        # Get workflow graph
        graph = await self.get_workflow_graph(enterprise_id)
        if not graph or "workflows" not in graph:
            logger.info(f"No workflow graph found for enterprise {enterprise_id} - allowing as first workflow")
            return True, None  # No graph = first workflow, allow
        
        # Get workflow entry
        workflow_entry = graph["workflows"].get(workflow_name)
        if not workflow_entry:
            logger.info(f"Workflow {workflow_name} not in graph - allowing (will be added on generation)")
            return True, None  # Workflow not in graph = allow (will be added)
        
        dependencies = workflow_entry.get("dependencies", {})
        if not dependencies or not any(dependencies.values()):
            logger.info(f"Workflow {workflow_name} has no dependencies - allowing")
            return True, None  # No dependencies = allow
        
        # Get ChatSessions collection for validation
        coll = await self.ag2_pm._coll()
        
        # Check required_workflows
        for req_wf in dependencies.get("required_workflows", []):
            wf_name = req_wf["workflow"]
            required_status = req_wf.get("status", "completed")
            reason = req_wf.get("reason", "")
            
            logger.debug(f"Checking required workflow: {wf_name} (status={required_status})")
            
            # Find most recent chat for that workflow
            doc = await coll.find_one(
                {
                    "enterprise_id": enterprise_id,
                    "user_id": user_id,
                    "workflow_name": wf_name
                },
                sort=[("created_at", -1)]
            )
            
            if not doc:
                error_msg = f"Please complete the {wf_name} workflow first. {reason}"
                logger.warning(f"Dependency not met: {error_msg}")
                return False, error_msg
            
            if required_status == "completed":
                if doc.get("status") != WorkflowStatus.COMPLETED:
                    error_msg = f"The {wf_name} workflow must be completed before starting {workflow_name}. {reason}"
                    logger.warning(f"Dependency not met: {error_msg}")
                    return False, error_msg
        
        # Check required_context_vars
        for req_var in dependencies.get("required_context_vars", []):
            var_name = req_var["variable"]
            source_wf = req_var.get("source_workflow")
            reason = req_var.get("reason", "")
            
            logger.debug(f"Checking required context variable: {var_name} from {source_wf}")
            
            if source_wf:
                doc = await coll.find_one(
                    {
                        "enterprise_id": enterprise_id,
                        "user_id": user_id,
                        "workflow_name": source_wf
                    },
                    sort=[("created_at", -1)]
                )
                
                if not doc or var_name not in doc.get("context", {}):
                    error_msg = f"Missing required context from {source_wf}: {var_name}. {reason}"
                    logger.warning(f"Dependency not met: {error_msg}")
                    return False, error_msg
        
        # Check required_artifacts
        for req_artifact in dependencies.get("required_artifacts", []):
            artifact_type = req_artifact["artifact_type"]
            source_wf = req_artifact.get("workflow")
            reason = req_artifact.get("reason", "")
            
            logger.debug(f"Checking required artifact: {artifact_type} from {source_wf}")
            
            doc = await coll.find_one(
                {
                    "enterprise_id": enterprise_id,
                    "user_id": user_id,
                    "workflow_name": source_wf
                },
                sort=[("created_at", -1)]
            )
            
            if not doc or "last_artifact" not in doc:
                error_msg = f"No {artifact_type} found from {source_wf}. {reason}"
                logger.warning(f"Dependency not met: {error_msg}")
                return False, error_msg
            
            artifact = doc.get("last_artifact", {})
            if artifact.get("type") != artifact_type:
                error_msg = f"Expected {artifact_type} artifact from {source_wf}. {reason}"
                logger.warning(f"Dependency not met: {error_msg}")
                return False, error_msg
        
        logger.info(f"All dependencies met for {workflow_name}")
        return True, None
    
    async def list_available_workflows(
        self, 
        enterprise_id: str, 
        user_id: str
    ) -> List[Dict[str, Any]]:
        """
        List all workflows and their availability status for a user.
        
        Args:
            enterprise_id: Enterprise identifier
            user_id: User identifier
            
        Returns:
            List of workflow availability objects:
            [
                {
                    "workflow_name": "Build",
                    "available": True,
                    "reason": "All dependencies met",
                    "dependencies": {...}
                }
            ]
        """
        logger.info(f"Listing available workflows for enterprise {enterprise_id}, user {user_id}")
        
        graph = await self.get_workflow_graph(enterprise_id)
        if not graph or "workflows" not in graph:
            logger.info("No workflow graph found - returning empty list")
            return []
        
        workflows = []
        for wf_name, wf_entry in graph["workflows"].items():
            is_available, reason = await self.validate_workflow_dependencies(
                workflow_name=wf_name,
                enterprise_id=enterprise_id,
                user_id=user_id
            )
            
            workflows.append({
                "workflow_name": wf_name,
                "available": is_available,
                "reason": reason or "All dependencies met",
                "dependencies": wf_entry.get("dependencies", {})
            })
        
        logger.info(f"Found {len(workflows)} workflows in graph")
        return workflows


# Global singleton instance
dependency_manager = WorkflowDependencyManager()
