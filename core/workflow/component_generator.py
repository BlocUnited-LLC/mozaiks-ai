"""
Component manifest generator for workflow initialization
This is part of the core workflow initialization system.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

from logs.logging_config import get_component_logger, get_workflow_logger, log_operation

logger = logging.getLogger(__name__)
component_logger = get_component_logger("manifest_generator")
workflow_logger = get_workflow_logger("component_generation")

class ComponentManifestGenerator:
    """
    Generates component manifests during workflow initialization.
    Used by the init system to create component registries for new workflows.
    """
    
    def __init__(self, base_dir: Path):
        self.base_dir = Path(base_dir)
    
    def generate_component_manifest(self, workflow_name: str, components: List[Dict]) -> Dict:
        """Generate components.json manifest for a workflow"""
        
        with log_operation(workflow_logger, "component_manifest_generation", 
                         workflow_name=workflow_name, component_count=len(components)):
            
            component_logger.info("Starting component manifest generation", extra={
                "workflow_name": workflow_name,
                "component_count": len(components),
                "base_dir": str(self.base_dir)
            })
            
            artifacts = []
            inline = []
            tool_mappings = {}
        
        for component in components:
            if component["type"] == "artifact":
                artifacts.append(component["name"])
            elif component["type"] == "inline":
                inline.append(component["name"])
                
            # Map tool types to components
            if "toolType" in component:
                tool_mappings[component["toolType"]] = {
                    "componentType": component["type"],
                    "componentName": component["name"]
                }
        
        return {
            "version": "1.0.0",
            "lastUpdated": datetime.now().isoformat(),
            "workflow": workflow_name,
            "description": f"Component registry for {workflow_name} workflow",
            "artifacts": {
                "manifestPath": "./Artifacts/components.json",
                "components": artifacts
            },
            "inline": {
                "manifestPath": "./Inline/components.json", 
                "components": inline
            },
            "toolMappings": tool_mappings,
            "requiredBackendTools": [comp.get("requiredTool") for comp in components if comp.get("requiredTool")]
        }
    
    def create_workflow_manifest_files(self, workflow_name: str, components: List[Dict]) -> List[str]:
        """
        Create all manifest files for a workflow during initialization.
        Returns list of created file paths.
        """
        workflow_path = self.base_dir / "workflows" / workflow_name / "Components"
        workflow_path.mkdir(parents=True, exist_ok=True)
        
        # Create component directories
        artifacts_path = workflow_path / "Artifacts"
        inline_path = workflow_path / "Inline"
        artifacts_path.mkdir(exist_ok=True)
        inline_path.mkdir(exist_ok=True)
        
        created_files = []
        
        # 1. Main components.json
        main_manifest = self.generate_component_manifest(workflow_name, components)
        main_file = workflow_path / "components.json"
        self._write_json(main_file, main_manifest)
        created_files.append(str(main_file))
        
        # 2. Artifacts manifest
        artifact_components = {comp["name"]: self._component_to_manifest_entry(comp) 
                             for comp in components if comp["type"] == "artifact"}
        
        if artifact_components:
            artifacts_manifest = {
                "version": "1.0.0",
                "lastUpdated": datetime.now().isoformat(),
                "workflow": workflow_name,
                "components": artifact_components
            }
            artifacts_file = artifacts_path / "components.json"
            self._write_json(artifacts_file, artifacts_manifest)
            created_files.append(str(artifacts_file))
        
        # 3. Inline manifest
        inline_components = {comp["name"]: self._component_to_manifest_entry(comp) 
                           for comp in components if comp["type"] == "inline"}
        
        if inline_components:
            inline_manifest = {
                "version": "1.0.0",
                "lastUpdated": datetime.now().isoformat(),
                "workflow": workflow_name,
                "components": inline_components
            }
            inline_file = inline_path / "components.json"
            self._write_json(inline_file, inline_manifest)
            created_files.append(str(inline_file))
        
        return created_files
    
    def _component_to_manifest_entry(self, component: Dict) -> Dict:
        """Convert component definition to manifest entry"""
        return {
            "file": f"{component['name']}.js",
            "category": component.get("category", "workflow_specific"),
            "toolType": component.get("toolType"),
            "description": component.get("description", f"Component for {component['name']}"),
            "requiredTool": component.get("requiredTool"),
            "props": component.get("defaultProps", {})
        }
    
    def _write_json(self, file_path: Path, data: Dict) -> None:
        """Write JSON data to file"""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def discover_existing_components(self, workflow_type: str) -> List[Dict]:
        """
        Dynamically discover existing components in a workflow folder.
        This scans for actual .js files and generates component definitions.
        """
        workflow_path = self.base_dir / "workflows" / workflow_type / "Components"
        
        if not workflow_path.exists():
            logger.debug(f"No existing components found for workflow: {workflow_type}")
            return []
        
        components = []
        
        # Scan Artifacts folder
        artifacts_path = workflow_path / "Artifacts"
        if artifacts_path.exists():
            for js_file in artifacts_path.glob("*.js"):
                component_name = js_file.stem
                components.append({
                    "name": component_name,
                    "type": "artifact",
                    "category": "discovered",
                    "description": f"Auto-discovered artifact component: {component_name}",
                    "file_path": str(js_file.relative_to(workflow_path))
                })
        
        # Scan Inline folder
        inline_path = workflow_path / "Inline"
        if inline_path.exists():
            for js_file in inline_path.glob("*.js"):
                component_name = js_file.stem
                components.append({
                    "name": component_name,
                    "type": "inline",
                    "category": "discovered",
                    "description": f"Auto-discovered inline component: {component_name}",
                    "file_path": str(js_file.relative_to(workflow_path))
                })
        
        logger.info(f"Discovered {len(components)} existing components for {workflow_type}")
        return components
    
    def load_workflow_component_config(self, workflow_type: str) -> List[Dict]:
        """
        Load component configuration from workflow's own config file.
        This allows each workflow to define its own components.
        """
        config_path = self.base_dir / "workflows" / workflow_type / "component_config.json"
        
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    components = config.get("components", [])
                    logger.info(f"Loaded {len(components)} components from {workflow_type} config")
                    return components
            except Exception as e:
                logger.warning(f"Failed to load component config for {workflow_type}: {e}")
        
        return []

    def get_components_for_workflow(self, workflow_type: str) -> List[Dict]:
        """
        Get components for a workflow using multiple discovery methods.
        Priority: 1) Existing config file 2) Auto-discovery 3) Empty list
        """
        # Try to load from workflow's own component config
        components = self.load_workflow_component_config(workflow_type)
        
        if components:
            logger.info(f"Using configured components for {workflow_type}")
            return components
        
        # Fallback to auto-discovery of existing components
        discovered = self.discover_existing_components(workflow_type)
        
        if discovered:
            logger.info(f"Using auto-discovered components for {workflow_type}")
            return discovered
        
        # If nothing found, return empty list (workflow will have no components initially)
        logger.info(f"No components found for {workflow_type} - will create empty manifest")
        return []

# Function for easy integration with init system
def initialize_workflow_components(workflow_name: str, workflow_type: str, base_dir: Path) -> List[str]:
    """
    Initialize component manifests for a new workflow.
    Called by the workflow initialization system.
    """
    generator = ComponentManifestGenerator(base_dir)
    
    # Use dynamic component discovery instead of hardcoded templates
    components = generator.get_components_for_workflow(workflow_type)
    
    if components:
        return generator.create_workflow_manifest_files(workflow_name, components)
    else:
        # Create minimal manifest structure for new workflows
        logger.info(f"Creating minimal component structure for new workflow: {workflow_name}")
        workflow_path = base_dir / "workflows" / workflow_name / "Components"
        workflow_path.mkdir(parents=True, exist_ok=True)
        (workflow_path / "Artifacts").mkdir(exist_ok=True)
        (workflow_path / "Inline").mkdir(exist_ok=True)
        
        # Create minimal main manifest
        minimal_manifest = {
            "version": "1.0.0",
            "lastUpdated": datetime.now().isoformat(),
            "workflow": workflow_name,
            "description": f"Component registry for {workflow_name} workflow",
            "artifacts": {"components": []},
            "inline": {"components": []},
            "toolMappings": {}
        }
        
        manifest_file = workflow_path / "components.json"
        with open(manifest_file, 'w', encoding='utf-8') as f:
            json.dump(minimal_manifest, f, indent=2, ensure_ascii=False)
        
        return [str(manifest_file)]
