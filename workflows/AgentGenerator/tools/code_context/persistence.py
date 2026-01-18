"""
Code Context Persistence

Stores extracted code context in MongoDB keyed by (app_id, workspace_id, version_hash).
Supports incremental updates and version comparison for diff detection.
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime
import hashlib

logger = logging.getLogger(__name__)


class CodeContextPersistence:
    """
    Manages persistence of extracted code contexts.
    
    Schema:
    {
        "app_id": str,
        "workspace_id": str,  # identifies the project/repo being generated
        "version_hash": str,  # hash of all file hashes (version identifier)
        "indexed_at": datetime,
        "files": {
            "path/to/file.py": {
                "hash": "abc123...",
                "language": "python",
                "imports": [...],
                "symbols": [...],
                ...
            }
        },
        "metadata": {
            "mode": "full|incremental",
            "file_count": int,
            "total_symbols": int
        }
    }
    """
    
    def __init__(self, db_client):
        """
        Args:
            db_client: MongoDB database client
        """
        self.db = db_client
        self.collection = self.db["CodeContext"]
        
        # Create indexes for efficient queries
        self.collection.create_index([("app_id", 1), ("workspace_id", 1), ("version_hash", 1)])
        self.collection.create_index([("app_id", 1), ("workspace_id", 1), ("indexed_at", -1)])
    
    def store_context(
        self,
        app_id: str,
        workspace_id: str,
        extracted_contexts: Dict[str, Dict[str, Any]],
        mode: str = "full"
    ) -> str:
        """
        Store extracted contexts.
        
        Args:
            app_id: Application ID
            workspace_id: Workspace/project identifier
            extracted_contexts: Map of file_path -> extracted context
            mode: "full" or "incremental"
        
        Returns:
            version_hash: Unique identifier for this version
        """
        # Compute version hash from all file hashes
        file_hashes = sorted([ctx["hash"] for ctx in extracted_contexts.values()])
        version_hash = hashlib.sha256("".join(file_hashes).encode()).hexdigest()[:16]
        
        # Calculate metadata
        total_symbols = sum(len(ctx.get("symbols", [])) for ctx in extracted_contexts.values())
        
        document = {
            "app_id": app_id,
            "workspace_id": workspace_id,
            "version_hash": version_hash,
            "indexed_at": datetime.utcnow(),
            "files": extracted_contexts,
            "metadata": {
                "mode": mode,
                "file_count": len(extracted_contexts),
                "total_symbols": total_symbols
            }
        }
        
        # Upsert (replace if same version exists)
        self.collection.replace_one(
            {
                "app_id": app_id,
                "workspace_id": workspace_id,
                "version_hash": version_hash
            },
            document,
            upsert=True
        )
        
        logger.info(
            f"Stored code context: app={app_id}, workspace={workspace_id}, "
            f"version={version_hash}, files={len(extracted_contexts)}"
        )
        
        return version_hash
    
    def get_context(
        self,
        app_id: str,
        workspace_id: str,
        version_hash: Optional[str] = None
    ) -> Optional[Dict[str, Dict[str, Any]]]:
        """
        Retrieve stored contexts.
        
        Args:
            app_id: Application ID
            workspace_id: Workspace identifier
            version_hash: Specific version (if None, returns latest)
        
        Returns:
            Map of file_path -> extracted context, or None if not found
        """
        query = {"app_id": app_id, "workspace_id": workspace_id}
        
        if version_hash:
            query["version_hash"] = version_hash
            document = self.collection.find_one(query)
        else:
            # Get latest version
            document = self.collection.find_one(
                query,
                sort=[("indexed_at", -1)]
            )
        
        if not document:
            return None
        
        return document.get("files", {})
    
    def get_version_hash(
        self,
        app_id: str,
        workspace_id: str
    ) -> Optional[str]:
        """Get the latest version hash for a workspace."""
        document = self.collection.find_one(
            {"app_id": app_id, "workspace_id": workspace_id},
            sort=[("indexed_at", -1)],
            projection={"version_hash": 1}
        )
        return document["version_hash"] if document else None
    
    def compare_versions(
        self,
        app_id: str,
        workspace_id: str,
        old_hash: str,
        new_hash: str
    ) -> Dict[str, Any]:
        """
        Compare two versions and return diff information.
        
        Returns:
        {
            "added_files": [file_paths],
            "removed_files": [file_paths],
            "modified_files": [file_paths],
            "unchanged_files": [file_paths],
            "detailed_changes": {
                "path/to/file.py": {
                    "added_symbols": [...],
                    "removed_symbols": [...],
                    "modified_symbols": [...]
                }
            }
        }
        """
        old_context = self.get_context(app_id, workspace_id, old_hash)
        new_context = self.get_context(app_id, workspace_id, new_hash)
        
        if not old_context or not new_context:
            logger.warning(f"Cannot compare: missing version (old={bool(old_context)}, new={bool(new_context)})")
            return {
                "added_files": list(new_context.keys()) if new_context else [],
                "removed_files": list(old_context.keys()) if old_context else [],
                "modified_files": [],
                "unchanged_files": [],
                "detailed_changes": {}
            }
        
        old_files = set(old_context.keys())
        new_files = set(new_context.keys())
        
        added_files = list(new_files - old_files)
        removed_files = list(old_files - new_files)
        common_files = old_files & new_files
        
        modified_files = []
        unchanged_files = []
        detailed_changes = {}
        
        for file_path in common_files:
            old_file = old_context[file_path]
            new_file = new_context[file_path]
            
            # Compare by hash
            if old_file["hash"] != new_file["hash"]:
                modified_files.append(file_path)
                
                # Detailed symbol-level diff
                old_symbols = {s["name"]: s for s in old_file.get("symbols", [])}
                new_symbols = {s["name"]: s for s in new_file.get("symbols", [])}
                
                detailed_changes[file_path] = {
                    "added_symbols": [s for name, s in new_symbols.items() if name not in old_symbols],
                    "removed_symbols": [s for name, s in old_symbols.items() if name not in new_symbols],
                    "modified_symbols": [
                        s for name, s in new_symbols.items()
                        if name in old_symbols and s != old_symbols[name]
                    ]
                }
            else:
                unchanged_files.append(file_path)
        
        return {
            "added_files": sorted(added_files),
            "removed_files": sorted(removed_files),
            "modified_files": sorted(modified_files),
            "unchanged_files": sorted(unchanged_files),
            "detailed_changes": detailed_changes
        }
    
    def update_incremental(
        self,
        app_id: str,
        workspace_id: str,
        new_or_modified_contexts: Dict[str, Dict[str, Any]],
        deleted_files: Optional[List[str]] = None
    ) -> str:
        """
        Incrementally update stored context.
        
        Fetches latest version, merges changes, and stores as new version.
        
        Args:
            app_id: Application ID
            workspace_id: Workspace identifier
            new_or_modified_contexts: Map of file_path -> extracted context
            deleted_files: List of file paths to remove
        
        Returns:
            new_version_hash: Version hash after update
        """
        # Get latest context
        latest = self.get_context(app_id, workspace_id)
        if latest is None:
            # No existing context, treat as full index
            return self.store_context(app_id, workspace_id, new_or_modified_contexts, mode="full")
        
        # Merge: update existing files, keep unchanged files
        merged = dict(latest)  # Copy existing
        merged.update(new_or_modified_contexts)  # Apply updates
        
        # Remove deleted files
        if deleted_files:
            for file_path in deleted_files:
                merged.pop(file_path, None)
        
        # Store as new version
        return self.store_context(app_id, workspace_id, merged, mode="incremental")
    
    def clear_workspace(
        self,
        app_id: str,
        workspace_id: str
    ) -> int:
        """
        Clear all indexed versions for a workspace.
        
        Returns:
            Number of deleted documents
        """
        result = self.collection.delete_many({
            "app_id": app_id,
            "workspace_id": workspace_id
        })
        logger.info(f"Cleared workspace: app={app_id}, workspace={workspace_id}, deleted={result.deleted_count}")
        return result.deleted_count
    
    def list_versions(
        self,
        app_id: str,
        workspace_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        List recent versions for a workspace.
        
        Returns list of:
        {
            "version_hash": str,
            "indexed_at": datetime,
            "file_count": int,
            "total_symbols": int
        }
        """
        cursor = self.collection.find(
            {"app_id": app_id, "workspace_id": workspace_id},
            projection={"version_hash": 1, "indexed_at": 1, "metadata": 1},
            sort=[("indexed_at", -1)],
            limit=limit
        )
        
        versions = []
        for doc in cursor:
            versions.append({
                "version_hash": doc["version_hash"],
                "indexed_at": doc["indexed_at"],
                "file_count": doc.get("metadata", {}).get("file_count", 0),
                "total_symbols": doc.get("metadata", {}).get("total_symbols", 0)
            })
        
        return versions
