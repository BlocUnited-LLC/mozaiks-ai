"""
Neutral Code Extractor

Language-aware AST extraction using TreeSitter.
Outputs a canonical schema (symbols, imports, exports, routes, components) 
independent of agent roles or specific tech stacks.
"""

import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Try to import tree_sitter; gracefully degrade if not available
try:
    from tree_sitter import Language, Parser
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    logger.warning("tree_sitter not available; using fallback extraction")


class CodeExtractor:
    """
    Extracts structured code context from files using language-specific parsers.
    Outputs a neutral canonical schema regardless of requesting agent or workflow.
    """
    
    SUPPORTED_LANGUAGES = {
        '.py': 'python',
        '.js': 'javascript',
        '.jsx': 'javascript',
        '.ts': 'typescript',
        '.tsx': 'typescript',
        '.css': 'css',
        '.json': 'json',
        '.yaml': 'yaml',
        '.yml': 'yaml'
    }
    
    def __init__(self):
        self.parsers = {}
        if TREE_SITTER_AVAILABLE:
            self._init_parsers()
    
    def _init_parsers(self):
        """Initialize tree-sitter parsers for supported languages."""
        # NOTE: In production, you'd build and load .so/.dll language files
        # For now, we'll use a fallback regex-based approach
        pass
    
    def extract_file(
        self,
        file_path: str,
        content: str,
        language: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extract structured context from a single file.
        
        Returns a canonical schema:
        {
            "path": str,
            "language": str,
            "hash": str,  # content hash for versioning
            "imports": [{"module": str, "items": [str], "alias": Optional[str]}],
            "exports": [{"name": str, "type": str, "signature": Optional[str]}],
            "symbols": [{"name": str, "type": str, "line": int, "docstring": str}],
            "framework_hints": {"type": str, "patterns": [str]},
            "excerpt_ranges": [(start_line, end_line, label)]  # for token-efficient retrieval
        }
        """
        ext = Path(file_path).suffix.lower()
        detected_language = language or self.SUPPORTED_LANGUAGES.get(ext, 'text')
        
        # Compute content hash for versioning
        import hashlib
        content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]
        
        base_context = {
            "path": file_path,
            "language": detected_language,
            "hash": content_hash,
            "imports": [],
            "exports": [],
            "symbols": [],
            "framework_hints": {},
            "excerpt_ranges": []
        }
        
        # Route to language-specific extractor
        if detected_language == 'python':
            return self._extract_python(content, base_context)
        elif detected_language in ('javascript', 'typescript'):
            return self._extract_javascript(content, base_context)
        elif detected_language == 'json':
            return self._extract_json(content, base_context)
        else:
            return self._extract_fallback(content, base_context)
    
    def _extract_python(self, content: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Extract Python imports, classes, functions using regex patterns."""
        import re
        
        lines = content.split('\n')
        
        # Extract imports
        for i, line in enumerate(lines):
            # from X import Y
            match = re.match(r'^\s*from\s+([\w\.]+)\s+import\s+(.+)', line)
            if match:
                module = match.group(1)
                items = [item.strip().split(' as ')[0] for item in match.group(2).split(',')]
                context["imports"].append({
                    "module": module,
                    "items": items,
                    "line": i + 1
                })
            # import X
            match = re.match(r'^\s*import\s+([\w\.]+)(?:\s+as\s+(\w+))?', line)
            if match:
                context["imports"].append({
                    "module": match.group(1),
                    "items": [],
                    "alias": match.group(2),
                    "line": i + 1
                })
        
        # Extract classes
        for i, line in enumerate(lines):
            match = re.match(r'^class\s+(\w+)(?:\(([^)]*)\))?:', line)
            if match:
                class_name = match.group(1)
                bases = match.group(2) or ""
                # Find docstring
                docstring = ""
                if i + 1 < len(lines):
                    doc_match = re.match(r'^\s*"""(.+)"""', lines[i + 1])
                    if doc_match:
                        docstring = doc_match.group(1).strip()
                
                context["symbols"].append({
                    "name": class_name,
                    "type": "class",
                    "line": i + 1,
                    "bases": [b.strip() for b in bases.split(',') if b.strip()],
                    "docstring": docstring
                })
                context["exports"].append({
                    "name": class_name,
                    "type": "class",
                    "line": i + 1
                })
        
        # Extract functions (top-level and methods)
        for i, line in enumerate(lines):
            match = re.match(r'^(\s*)def\s+(\w+)\s*\(([^)]*)\)', line)
            if match:
                indent = match.group(1)
                func_name = match.group(2)
                params = match.group(3)
                is_method = len(indent) > 0
                
                # Find docstring
                docstring = ""
                if i + 1 < len(lines):
                    doc_match = re.match(r'^\s*"""(.+)"""', lines[i + 1])
                    if doc_match:
                        docstring = doc_match.group(1).strip()
                
                context["symbols"].append({
                    "name": func_name,
                    "type": "method" if is_method else "function",
                    "line": i + 1,
                    "params": [p.strip().split(':')[0].strip() for p in params.split(',') if p.strip()],
                    "docstring": docstring
                })
                
                if not is_method:
                    context["exports"].append({
                        "name": func_name,
                        "type": "function",
                        "line": i + 1
                    })
        
        # Detect framework hints
        import_modules = [imp["module"] for imp in context["imports"]]
        if any('fastapi' in m for m in import_modules):
            context["framework_hints"]["backend"] = "fastapi"
        if any('flask' in m for m in import_modules):
            context["framework_hints"]["backend"] = "flask"
        if any('sqlalchemy' in m for m in import_modules):
            context["framework_hints"]["orm"] = "sqlalchemy"
        
        return context
    
    def _extract_javascript(self, content: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Extract JavaScript/TypeScript imports, exports, components using regex."""
        import re
        
        lines = content.split('\n')
        
        # Extract imports
        for i, line in enumerate(lines):
            # import X from 'Y'
            match = re.match(r'^\s*import\s+(.+?)\s+from\s+[\'"](.+?)[\'"]', line)
            if match:
                items_str = match.group(1).strip()
                module = match.group(2)
                
                # Parse items (handle default, named, namespace imports)
                items = []
                if items_str.startswith('{'):
                    # Named imports
                    items = [item.strip().split(' as ')[0] for item in items_str.strip('{}').split(',')]
                else:
                    # Default import
                    items = [items_str.split(' as ')[0]]
                
                context["imports"].append({
                    "module": module,
                    "items": items,
                    "line": i + 1
                })
        
        # Extract exports
        for i, line in enumerate(lines):
            # export function X
            match = re.match(r'^\s*export\s+(?:default\s+)?(?:function|const|class)\s+(\w+)', line)
            if match:
                context["exports"].append({
                    "name": match.group(1),
                    "type": "export",
                    "line": i + 1
                })
        
        # Extract React components (function components)
        for i, line in enumerate(lines):
            match = re.match(r'^\s*(?:export\s+)?(?:default\s+)?function\s+(\w+)\s*\(([^)]*)\)', line)
            if match:
                comp_name = match.group(1)
                props = match.group(2)
                context["symbols"].append({
                    "name": comp_name,
                    "type": "component",
                    "line": i + 1,
                    "props": props.strip()
                })
        
        # Detect framework hints
        import_modules = [imp["module"] for imp in context["imports"]]
        if any('react' in m.lower() for m in import_modules):
            context["framework_hints"]["frontend"] = "react"
        if any('vue' in m.lower() for m in import_modules):
            context["framework_hints"]["frontend"] = "vue"
        
        return context
    
    def _extract_json(self, content: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Extract schema from JSON config files."""
        import json
        try:
            data = json.loads(content)
            context["symbols"].append({
                "name": "config",
                "type": "json",
                "keys": list(data.keys()) if isinstance(data, dict) else []
            })
        except json.JSONDecodeError:
            pass
        return context
    
    def _extract_fallback(self, content: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback extractor for unsupported file types."""
        lines = content.split('\n')
        context["excerpt_ranges"] = [(1, min(50, len(lines)), "preview")]
        return context


def extract_codebase(
    file_paths: List[str],
    content_map: Dict[str, str],
    ignore_patterns: Optional[List[str]] = None
) -> Dict[str, Dict[str, Any]]:
    """
    Extract structured context from multiple files.
    
    Args:
        file_paths: List of file paths to index
        content_map: Map of file_path -> content
        ignore_patterns: Glob patterns to exclude
    
    Returns:
        Map of file_path -> extracted context
    """
    extractor = CodeExtractor()
    results = {}
    
    ignore_patterns = ignore_patterns or []
    
    for file_path in file_paths:
        # Check ignore patterns
        from fnmatch import fnmatch
        if any(fnmatch(file_path, pattern) for pattern in ignore_patterns):
            continue
        
        content = content_map.get(file_path, "")
        if not content:
            continue
        
        try:
            context = extractor.extract_file(file_path, content)
            results[file_path] = context
        except Exception as e:
            logger.error(f"Failed to extract {file_path}: {e}")
            continue
    
    return results
