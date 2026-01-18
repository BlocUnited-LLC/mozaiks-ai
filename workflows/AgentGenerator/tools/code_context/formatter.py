"""
Intent-Based Formatter

Transforms neutral extracted context into role/intent-specific formatted output.
Intent definitions are loaded from workflow config (declarative, not hard-coded).
"""

import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class ContextFormatter:
    """
    Formats extracted code context based on intent definitions.
    
    An intent defines:
    - which fields to include (imports, symbols, exports, etc.)
    - scope rules (all files, changed files, specific paths)
    - token budget and truncation strategy
    """
    
    def __init__(self, intent_config: Dict[str, Any]):
        """
        Args:
            intent_config: Map of intent_name -> intent definition
                Example:
                {
                    "backend_service_generation": {
                        "includes": ["imports", "symbols", "framework_hints"],
                        "symbol_types": ["class", "function"],
                        "max_tokens": 8000,
                        "format": "structured"
                    }
                }
        """
        self.intent_config = intent_config or {}
    
    def format(
        self,
        intent: str,
        contexts: Dict[str, Dict[str, Any]],
        scope: Optional[List[str]] = None,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Format extracted contexts for a specific intent.
        
        Args:
            intent: Intent name (e.g., "backend_service_generation")
            contexts: Map of file_path -> extracted context
            scope: Optional file path filter
            max_tokens: Optional token limit override
        
        Returns:
            Formatted context string ready for agent consumption
        """
        if intent not in self.intent_config:
            logger.warning(f"Unknown intent: {intent}, using default formatting")
            return self._format_default(contexts, scope, max_tokens)
        
        intent_def = self.intent_config[intent]
        
        # Apply scope filter
        if scope:
            contexts = {k: v for k, v in contexts.items() if k in scope}
        
        # Route to format style
        format_style = intent_def.get("format", "structured")
        if format_style == "structured":
            return self._format_structured(contexts, intent_def, max_tokens)
        elif format_style == "imports_only":
            return self._format_imports_only(contexts, intent_def, max_tokens)
        elif format_style == "symbols_only":
            return self._format_symbols_only(contexts, intent_def, max_tokens)
        else:
            return self._format_default(contexts, scope, max_tokens)
    
    def _format_structured(
        self,
        contexts: Dict[str, Dict[str, Any]],
        intent_def: Dict[str, Any],
        max_tokens: Optional[int]
    ) -> str:
        """Full structured format with sections."""
        includes = intent_def.get("includes", ["imports", "symbols", "exports"])
        symbol_types = intent_def.get("symbol_types", None)  # None = all types
        
        sections = []
        
        # Group by module/file
        sections.append("### Code Context ###\n")
        sections.append("The following modules and symbols are available in the codebase:\n\n")
        
        for file_path, context in sorted(contexts.items()):
            sections.append(f"**{file_path}** ({context['language']})\n")
            
            # Imports section
            if "imports" in includes and context.get("imports"):
                sections.append("  Imports:\n")
                for imp in context["imports"][:20]:  # Limit per file
                    module = imp["module"]
                    items = imp.get("items", [])
                    if items:
                        sections.append(f"    - from {module} import {', '.join(items)}\n")
                    else:
                        alias = imp.get("alias", "")
                        sections.append(f"    - import {module}{' as ' + alias if alias else ''}\n")
            
            # Symbols section
            if "symbols" in includes and context.get("symbols"):
                filtered_symbols = context["symbols"]
                if symbol_types:
                    filtered_symbols = [s for s in filtered_symbols if s.get("type") in symbol_types]
                
                if filtered_symbols:
                    sections.append("  Symbols:\n")
                    for symbol in filtered_symbols[:30]:  # Limit per file
                        name = symbol["name"]
                        sym_type = symbol["type"]
                        line = symbol.get("line", "?")
                        docstring = symbol.get("docstring", "")
                        
                        sections.append(f"    - {sym_type} `{name}` (line {line})")
                        if docstring:
                            sections.append(f": {docstring[:100]}")
                        sections.append("\n")
            
            # Exports section
            if "exports" in includes and context.get("exports"):
                sections.append("  Exports:\n")
                for exp in context["exports"][:20]:
                    sections.append(f"    - {exp['name']} ({exp['type']})\n")
            
            # Framework hints
            if "framework_hints" in includes and context.get("framework_hints"):
                hints = context["framework_hints"]
                if hints:
                    sections.append(f"  Framework: {', '.join(f'{k}={v}' for k, v in hints.items())}\n")
            
            sections.append("\n")
        
        result = "".join(sections)
        
        # Apply token limit if specified
        if max_tokens:
            result = self._truncate_to_tokens(result, max_tokens)
        
        return result
    
    def _format_imports_only(
        self,
        contexts: Dict[str, Dict[str, Any]],
        intent_def: Dict[str, Any],
        max_tokens: Optional[int]
    ) -> str:
        """Format showing only imports (useful for dependency analysis)."""
        sections = ["### Import Statements ###\n"]
        sections.append("Use the following imports exactly as shown:\n\n")
        
        for file_path, context in sorted(contexts.items()):
            if not context.get("imports"):
                continue
            
            sections.append(f"From {file_path}:\n")
            for imp in context["imports"]:
                module = imp["module"]
                items = imp.get("items", [])
                if items:
                    sections.append(f"  from {module} import {', '.join(items)}\n")
                else:
                    alias = imp.get("alias", "")
                    sections.append(f"  import {module}{' as ' + alias if alias else ''}\n")
            sections.append("\n")
        
        result = "".join(sections)
        if max_tokens:
            result = self._truncate_to_tokens(result, max_tokens)
        return result
    
    def _format_symbols_only(
        self,
        contexts: Dict[str, Dict[str, Any]],
        intent_def: Dict[str, Any],
        max_tokens: Optional[int]
    ) -> str:
        """Format showing only symbol definitions (classes, functions)."""
        symbol_types = intent_def.get("symbol_types", None)
        
        sections = ["### Available Symbols ###\n"]
        
        for file_path, context in sorted(contexts.items()):
            symbols = context.get("symbols", [])
            if symbol_types:
                symbols = [s for s in symbols if s.get("type") in symbol_types]
            
            if not symbols:
                continue
            
            sections.append(f"**{file_path}**:\n")
            for symbol in symbols:
                name = symbol["name"]
                sym_type = symbol["type"]
                params = symbol.get("params", [])
                docstring = symbol.get("docstring", "")
                
                if params:
                    sections.append(f"  - {sym_type} `{name}({', '.join(params)})`")
                else:
                    sections.append(f"  - {sym_type} `{name}`")
                
                if docstring:
                    sections.append(f": {docstring[:80]}")
                sections.append("\n")
            sections.append("\n")
        
        result = "".join(sections)
        if max_tokens:
            result = self._truncate_to_tokens(result, max_tokens)
        return result
    
    def _format_default(
        self,
        contexts: Dict[str, Dict[str, Any]],
        scope: Optional[List[str]],
        max_tokens: Optional[int]
    ) -> str:
        """Default formatting when intent is unknown."""
        sections = ["### Code Context (Default View) ###\n\n"]
        
        for file_path, context in sorted(contexts.items()):
            sections.append(f"**{file_path}**\n")
            sections.append(f"  Language: {context['language']}\n")
            sections.append(f"  Imports: {len(context.get('imports', []))}\n")
            sections.append(f"  Symbols: {len(context.get('symbols', []))}\n")
            sections.append(f"  Exports: {len(context.get('exports', []))}\n\n")
        
        result = "".join(sections)
        if max_tokens:
            result = self._truncate_to_tokens(result, max_tokens)
        return result
    
    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """
        Truncate text to approximately max_tokens.
        Uses rough heuristic: 1 token ≈ 4 characters.
        """
        max_chars = max_tokens * 4
        if len(text) <= max_chars:
            return text
        
        truncated = text[:max_chars]
        # Try to cut at a newline
        last_newline = truncated.rfind('\n')
        if last_newline > max_chars * 0.8:
            truncated = truncated[:last_newline]
        
        return truncated + "\n\n... (truncated to fit token budget)"


# Default intent definitions (can be overridden by workflow config)
DEFAULT_INTENTS = {
    "backend_service_generation": {
        "includes": ["imports", "symbols", "framework_hints"],
        "symbol_types": ["class", "function"],
        "max_tokens": 8000,
        "format": "structured"
    },
    "api_routes_generation": {
        "includes": ["imports", "symbols", "exports"],
        "symbol_types": ["function", "class"],
        "max_tokens": 6000,
        "format": "structured"
    },
    "frontend_components_generation": {
        "includes": ["imports", "symbols", "exports"],
        "symbol_types": ["component", "function"],
        "max_tokens": 6000,
        "format": "structured"
    },
    "imports_check": {
        "includes": ["imports"],
        "max_tokens": 2000,
        "format": "imports_only"
    },
    "symbols_overview": {
        "includes": ["symbols"],
        "max_tokens": 4000,
        "format": "symbols_only"
    }
}
