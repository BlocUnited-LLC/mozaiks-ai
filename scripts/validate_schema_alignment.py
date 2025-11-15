"""
Schema Alignment Validator

Compares agent [OUTPUT FORMAT] sections in agents.json with their registered
structured output schemas in structured_outputs.json to identify mismatches.

Usage:
    python scripts/validate_schema_alignment.py
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional


class SchemaAlignmentValidator:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.agents_path = workspace_root / "workflows" / "Generator" / "agents.json"
        self.schemas_path = workspace_root / "workflows" / "Generator" / "structured_outputs.json"
        
        self.agents_data = None
        self.schemas_data = None
        self.mismatches = []
        
    def load_files(self) -> bool:
        """Load both JSON files."""
        try:
            with open(self.agents_path, 'r', encoding='utf-8') as f:
                self.agents_data = json.load(f)
            with open(self.schemas_path, 'r', encoding='utf-8') as f:
                self.schemas_data = json.load(f)
            return True
        except Exception as e:
            print(f"❌ Error loading files: {e}")
            return False
    
    def extract_output_format_fields(self, output_format_content: str) -> Optional[Dict[str, Any]]:
        """
        Extract field structure from [OUTPUT FORMAT] section.
        Looks for JSON examples in the content.
        """
        # Find JSON block in the output format (between ```json and ```)
        json_match = re.search(r'```json\s*\n(.*?)\n```', output_format_content, re.DOTALL)
        if not json_match:
            return None
        
        json_text = json_match.group(1)
        
        # Try to parse the JSON example
        try:
            # Replace placeholders like <int>, <string>, etc. with actual values
            cleaned = re.sub(r'<[^>]+>', '""', json_text)
            cleaned = re.sub(r'\|\|', '', cleaned)  # Remove || separators
            cleaned = re.sub(r'(true|false)', '"bool"', cleaned)  # Replace booleans
            
            # Parse to get structure
            parsed = json.loads(cleaned)
            return parsed
        except json.JSONDecodeError:
            # If parsing fails, try to extract field names manually
            fields = re.findall(r'"(\w+)":', json_text)
            return {field: "unknown" for field in fields}
    
    def get_schema_fields(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Get field structure from schema definition."""
        if not model_name or model_name == "null":
            return None
        
        models = self.schemas_data.get("structured_outputs", {}).get("models", {})
        model = models.get(model_name)
        
        if not model:
            return None
        
        if model.get("type") != "model":
            return None
        
        return model.get("fields", {})
    
    def compare_structures(self, agent_name: str, output_fields: Dict, schema_fields: Dict) -> List[str]:
        """Compare output format fields with schema fields."""
        issues = []
        
        # Get all top-level keys
        output_keys = set(output_fields.keys())
        schema_keys = set(schema_fields.keys())
        
        # Check for missing fields in output format
        missing_in_output = schema_keys - output_keys
        if missing_in_output:
            issues.append(f"  ⚠️  Fields in schema but NOT in [OUTPUT FORMAT]: {', '.join(missing_in_output)}")
        
        # Check for extra fields in output format
        extra_in_output = output_keys - schema_keys
        if extra_in_output:
            issues.append(f"  ⚠️  Fields in [OUTPUT FORMAT] but NOT in schema: {', '.join(extra_in_output)}")
        
        # Check for nested structure mismatches
        common_keys = output_keys & schema_keys
        for key in common_keys:
            output_val = output_fields[key]
            schema_val = schema_fields[key]
            
            # If both are dicts, check nested structure
            if isinstance(output_val, dict) and isinstance(schema_val, dict):
                if "type" in schema_val:
                    schema_type = schema_val["type"]
                    # Check if it's a nested model reference
                    if schema_type in self.schemas_data.get("structured_outputs", {}).get("models", {}):
                        nested_schema = self.get_schema_fields(schema_type)
                        if nested_schema:
                            nested_issues = self.compare_structures(agent_name, output_val, nested_schema)
                            if nested_issues:
                                issues.append(f"  ⚠️  Nested field '{key}' has mismatches:")
                                issues.extend([f"    {issue}" for issue in nested_issues])
        
        return issues
    
    def validate_agent(self, agent_name: str) -> Tuple[bool, List[str]]:
        """Validate a single agent's schema alignment."""
        issues = []
        
        # Get agent config
        agents = self.agents_data.get("agents", {})
        agent_config = agents.get(agent_name)
        
        if not agent_config:
            return False, [f"Agent '{agent_name}' not found in agents.json"]
        
        # Get registered schema name from structured_outputs.json registry
        registry = self.schemas_data.get("structured_outputs", {}).get("registry", {})
        schema_name = registry.get(agent_name)
        
        if schema_name is None or schema_name == "null":
            # Agent doesn't require structured outputs
            return True, [f"✅ Agent '{agent_name}' has no structured output requirement (registry: null)"]
        
        # Get output format section
        prompt_sections = agent_config.get("prompt_sections", [])
        output_format_section = None
        
        for section in prompt_sections:
            if section.get("id") == "output_format":
                output_format_section = section.get("content", "")
                break
        
        if not output_format_section:
            return False, [f"❌ Agent '{agent_name}' has no [OUTPUT FORMAT] section but schema expects '{schema_name}'"]
        
        # Extract fields from output format
        output_fields = self.extract_output_format_fields(output_format_section)
        
        if not output_fields:
            return False, [f"❌ Could not parse JSON example from [OUTPUT FORMAT] for agent '{agent_name}'"]
        
        # Get schema fields
        schema_fields = self.get_schema_fields(schema_name)
        
        if not schema_fields:
            return False, [f"❌ Schema '{schema_name}' not found in structured_outputs.json"]
        
        # Compare structures
        comparison_issues = self.compare_structures(agent_name, output_fields, schema_fields)
        
        if comparison_issues:
            issues.append(f"❌ MISALIGNMENT for '{agent_name}' (schema: {schema_name}):")
            issues.extend(comparison_issues)
            return False, issues
        else:
            return True, [f"✅ Agent '{agent_name}' is ALIGNED with schema '{schema_name}'"]
    
    def validate_all(self) -> Dict[str, Any]:
        """Validate all agents."""
        if not self.load_files():
            return {"success": False, "error": "Failed to load files"}
        
        registry = self.schemas_data.get("structured_outputs", {}).get("registry", {})
        results = {
            "total": len(registry),
            "aligned": 0,
            "misaligned": 0,
            "details": {}
        }
        
        print("\n" + "="*80)
        print("SCHEMA ALIGNMENT VALIDATION REPORT")
        print("="*80 + "\n")
        
        for agent_name in sorted(registry.keys()):
            is_aligned, messages = self.validate_agent(agent_name)
            
            results["details"][agent_name] = {
                "aligned": is_aligned,
                "messages": messages
            }
            
            if is_aligned:
                results["aligned"] += 1
            else:
                results["misaligned"] += 1
            
            # Print results
            for msg in messages:
                print(msg)
            print()
        
        # Summary
        print("="*80)
        print("SUMMARY")
        print("="*80)
        print(f"Total Agents: {results['total']}")
        print(f"✅ Aligned: {results['aligned']}")
        print(f"❌ Misaligned: {results['misaligned']}")
        print()
        
        if results["misaligned"] > 0:
            print("⚠️  MISALIGNMENTS FOUND - Review required before making changes")
            print("\nMisaligned Agents:")
            for agent_name, details in results["details"].items():
                if not details["aligned"]:
                    print(f"  - {agent_name}")
        else:
            print("✅ ALL AGENTS ARE ALIGNED!")
        
        print("="*80 + "\n")
        
        return results


def main():
    """Main entry point."""
    # Get workspace root (3 levels up from scripts/)
    script_dir = Path(__file__).parent
    workspace_root = script_dir.parent
    
    validator = SchemaAlignmentValidator(workspace_root)
    results = validator.validate_all()
    
    # Exit with error code if misalignments found
    if results.get("misaligned", 0) > 0:
        exit(1)
    else:
        exit(0)


if __name__ == "__main__":
    main()
