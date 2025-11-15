"""
Validate pattern-specific structured output examples in update_agent_state_pattern.py

This script verifies that:
1. All 9 patterns have examples for WorkflowArchitectAgent, ProjectOverviewAgent, and WorkflowImplementationAgent
2. All examples are valid JSON
3. Examples match their respective schema structures (TechnicalBlueprintCall, MermaidSequenceDiagramCall, PhaseAgentsCall)
"""
import json
import re
from pathlib import Path


def extract_examples_from_file(file_path: Path, pattern_name: str, dict_name: str):
    """Extract example dictionary from Python file."""
    content = file_path.read_text(encoding='utf-8')
    
    # Find the dictionary assignment (e.g., architect_examples = { ... })
    pattern = rf'{dict_name}\s*=\s*{{'
    match = re.search(pattern, content)
    if not match:
        return None, f"Could not find {dict_name} dictionary"
    
    # Find matching closing brace
    start = match.end() - 1  # Start at opening brace
    brace_count = 0
    in_string = False
    escape_next = False
    i = start
    
    while i < len(content):
        char = content[i]
        
        if escape_next:
            escape_next = False
            i += 1
            continue
            
        if char == '\\':
            escape_next = True
            i += 1
            continue
            
        if char == '"':
            in_string = not in_string
        elif not in_string:
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    # Found the closing brace
                    dict_str = content[start:i+1]
                    return dict_str, None
        i += 1
    
    return None, f"Could not find closing brace for {dict_name}"


def validate_json_examples(dict_str: str, dict_name: str):
    """Validate that all examples in the dictionary are valid JSON."""
    results = {
        'total': 0,
        'valid': 0,
        'invalid': [],
        'missing': []
    }
    
    # Extract pattern IDs 1-9
    for pattern_id in range(1, 10):
        results['total'] += 1
        
        # Find the pattern entry (e.g., 1: """{ ... }""")
        pattern_match = re.search(rf'{pattern_id}:\s*"""(.*?)"""', dict_str, re.DOTALL)
        if not pattern_match:
            results['missing'].append(pattern_id)
            continue
            
        json_str = pattern_match.group(1).strip()
        
        # Try to parse JSON
        try:
            parsed = json.loads(json_str)
            results['valid'] += 1
        except json.JSONDecodeError as e:
            results['invalid'].append({
                'pattern_id': pattern_id,
                'error': str(e),
                'preview': json_str[:200]
            })
    
    return results


def validate_schema_structure(dict_str: str, dict_name: str, expected_structure: dict):
    """Validate that examples match expected schema structure."""
    results = {
        'total': 0,
        'valid': 0,
        'invalid': []
    }
    
    for pattern_id in range(1, 10):
        results['total'] += 1
        
        pattern_match = re.search(rf'{pattern_id}:\s*"""(.*?)"""', dict_str, re.DOTALL)
        if not pattern_match:
            continue
            
        json_str = pattern_match.group(1).strip()
        
        try:
            parsed = json.loads(json_str)
            
            # Check top-level keys
            missing_keys = []
            extra_keys = []
            
            for key in expected_structure['required_keys']:
                if key not in parsed:
                    missing_keys.append(key)
            
            for key in parsed.keys():
                if key not in expected_structure['allowed_keys']:
                    extra_keys.append(key)
            
            if missing_keys or extra_keys:
                results['invalid'].append({
                    'pattern_id': pattern_id,
                    'missing_keys': missing_keys,
                    'extra_keys': extra_keys
                })
            else:
                results['valid'] += 1
                
        except json.JSONDecodeError:
            # Already caught in JSON validation
            pass
    
    return results


def main():
    script_dir = Path(__file__).parent
    workspace_root = script_dir.parent
    pattern_file = workspace_root / 'workflows' / 'Generator' / 'tools' / 'update_agent_state_pattern.py'
    
    if not pattern_file.exists():
        print(f"❌ File not found: {pattern_file}")
        return
    
    print("=" * 80)
    print("PATTERN INJECTION EXAMPLES VALIDATION")
    print("=" * 80)
    print()
    
    # Define expected schema structures
    schemas = {
        'architect_examples': {
            'agent': 'WorkflowArchitectAgent',
            'schema': 'TechnicalBlueprintCall',
            'expected_structure': {
                'required_keys': ['phase_technical_requirements', 'shared_requirements', 'agent_message'],
                'allowed_keys': ['phase_technical_requirements', 'shared_requirements', 'agent_message']
            }
        },
        'mermaid_examples': {
            'agent': 'ProjectOverviewAgent',
            'schema': 'MermaidSequenceDiagramCall',
            'expected_structure': {
                'required_keys': ['MermaidSequenceDiagram', 'agent_message'],
                'allowed_keys': ['MermaidSequenceDiagram', 'agent_message']
            }
        },
        'implementation_examples': {
            'agent': 'WorkflowImplementationAgent',
            'schema': 'PhaseAgentsCall',
            'expected_structure': {
                'required_keys': ['PhaseAgents'],
                'allowed_keys': ['PhaseAgents']
            }
        }
    }
    
    all_valid = True
    
    for dict_name, config in schemas.items():
        print(f"\n{'=' * 80}")
        print(f"{config['agent']} ({dict_name})")
        print(f"Expected Schema: {config['schema']}")
        print(f"{'=' * 80}\n")
        
        # Extract dictionary
        dict_str, error = extract_examples_from_file(pattern_file, config['agent'], dict_name)
        if error:
            print(f"❌ {error}")
            all_valid = False
            continue
        
        # Validate JSON
        json_results = validate_json_examples(dict_str, dict_name)
        print(f"JSON Validation:")
        print(f"  Total patterns: {json_results['total']}")
        print(f"  ✅ Valid JSON: {json_results['valid']}")
        
        if json_results['missing']:
            print(f"  ⚠️  Missing patterns: {json_results['missing']}")
            all_valid = False
        
        if json_results['invalid']:
            print(f"  ❌ Invalid JSON: {len(json_results['invalid'])}")
            for item in json_results['invalid']:
                print(f"     Pattern {item['pattern_id']}: {item['error']}")
            all_valid = False
        
        # Validate structure
        structure_results = validate_schema_structure(dict_str, dict_name, config['expected_structure'])
        print(f"\nSchema Structure Validation:")
        print(f"  ✅ Valid structure: {structure_results['valid']}/{structure_results['total']}")
        
        if structure_results['invalid']:
            print(f"  ❌ Invalid structure: {len(structure_results['invalid'])}")
            for item in structure_results['invalid']:
                print(f"     Pattern {item['pattern_id']}:")
                if item['missing_keys']:
                    print(f"       Missing keys: {item['missing_keys']}")
                if item['extra_keys']:
                    print(f"       Extra keys: {item['extra_keys']}")
            all_valid = False
    
    print(f"\n{'=' * 80}")
    if all_valid:
        print("✅ ALL VALIDATIONS PASSED")
    else:
        print("❌ SOME VALIDATIONS FAILED")
    print(f"{'=' * 80}\n")
    
    return 0 if all_valid else 1


if __name__ == '__main__':
    exit(main())
