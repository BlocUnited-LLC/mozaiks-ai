# WORKFLOW CONFIG OPTIMIZATION PLAN

## Current Problems:
1. **workflow_config.py** loads all workflows at startup using WorkflowFileManager
2. **init_registry.py** has its own YAML loading logic for on-demand discovery
3. **orchestration_patterns.py** has duplicate factory creation logic
4. Multiple configuration access patterns across the codebase

## Proposed Solution: Consolidate into Single Configuration Engine

### PHASE 1: Merge init_registry discovery into workflow_config.py
- Move on-demand discovery from init_registry.py into WorkflowConfig class
- Eliminate duplicate YAML loading logic
- Create unified workflow registration system

### PHASE 2: Consolidate factory creation
- Move factory creation logic from init_registry.py into workflow_config.py
- Remove duplicate load_workflow_components() from orchestration_patterns.py
- Single source of truth for agents/context/handoffs factories

### PHASE 3: Unified Configuration API
- Single method: WorkflowConfig.get_workflow_handler(workflow_name)
- Handles: discovery, loading, factory creation, registration
- Replace all current workflow_config.get_config() calls

## Benefits:
- ✅ Eliminate 200+ lines of duplicate code
- ✅ Single configuration loading path
- ✅ Lazy loading instead of startup overhead
- ✅ Simplified architecture

## Files to Modify:
1. workflow_config.py - Add discovery and factory creation
2. init_registry.py - Remove YAML loading, keep only registry functions
3. orchestration_patterns.py - Remove load_workflow_components()
4. agents.py, context_variables.py, handoffs.py - Use unified API

## Estimated Code Reduction: ~300 lines
