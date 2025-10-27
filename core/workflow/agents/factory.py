# ==============================================================================
# FILE: core/workflow/agents/factory.py
# DESCRIPTION: ConversableAgent factory aligned with agent-centric context plan
# ==============================================================================
from __future__ import annotations

import logging
import string
from collections import defaultdict
from typing import Any, Dict, List, Optional, Callable

from autogen import ConversableAgent, UpdateSystemMessage

from ..outputs import get_structured_outputs_for_workflow

from ..workflow_manager import workflow_manager

logger = logging.getLogger(__name__)


# ==============================================================================
# IMAGE GENERATION UTILITIES
# ==============================================================================

def extract_images_from_conversation(sender: ConversableAgent, recipient: ConversableAgent):
    """Extract PIL images from agent conversation history (for image generation capabilities).
    
    Parses GPT-4V format messages where content is an array with image_url entries.
    
    Args:
        sender: Agent that sent messages (image generator)
        recipient: Agent that received messages
        
    Returns:
        List of PIL Image objects found in conversation
        
    Raises:
        ValueError: If no images found in message history
    """
    try:
        from autogen.agentchat.contrib import img_utils
    except ImportError:
        logger.error("[IMAGE_EXTRACT] Failed to import img_utils from autogen.agentchat.contrib")
        raise ImportError("autogen.agentchat.contrib.img_utils not available - install ag2[lmm]")
    
    images = []
    all_messages = sender.chat_messages.get(recipient, [])
    
    logger.debug(f"[IMAGE_EXTRACT] Scanning {len(all_messages)} messages from {sender.name} to {recipient.name}")
    
    for idx, message in enumerate(reversed(all_messages)):
        contents = message.get("content", [])
        
        # Handle both string and array content formats
        if isinstance(contents, str):
            continue
            
        if not isinstance(contents, list):
            logger.warning(f"[IMAGE_EXTRACT] Message {idx} has unexpected content type: {type(contents)}")
            continue
        
        for content_idx, content in enumerate(contents):
            if isinstance(content, str):
                continue
                
            if not isinstance(content, dict):
                continue
                
            if content.get("type") == "image_url":
                img_data = content.get("image_url", {}).get("url")
                if img_data:
                    try:
                        img = img_utils.get_pil_image(img_data)
                        images.append(img)
                        logger.info(f"[IMAGE_EXTRACT] Found image in message {idx}, content {content_idx}")
                    except Exception as img_err:
                        logger.warning(f"[IMAGE_EXTRACT] Failed to load image from message {idx}: {img_err}")
    
    if not images:
        logger.error(f"[IMAGE_EXTRACT] No images found in {len(all_messages)} messages")
        raise ValueError("No image data found in conversation history")
    
    logger.info(f"[IMAGE_EXTRACT] Successfully extracted {len(images)} images")
    return images


# ==============================================================================
# CONTEXT UTILITIES
# ==============================================================================

def _context_to_dict(container: Any) -> Dict[str, Any]:
    try:
        if hasattr(container, "to_dict"):
            return dict(container.to_dict())  # type: ignore[arg-type]
    except Exception:  # pragma: no cover
        pass
    data = getattr(container, "data", None)
    if isinstance(data, dict):
        return dict(data)
    if isinstance(container, dict):
        return dict(container)
    return {}


def _stringify_context_value(value: Any, null_label: Optional[str]) -> str:
    if value is None:
        return null_label if null_label is not None else "None"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _format_template(template: str, mapping: Dict[str, Any]) -> str:
    formatter = string.Formatter()
    try:
        return formatter.vformat(template, (), mapping)
    except Exception:  # pragma: no cover
        return template


def _render_exposure_fragment(
    exposure: Dict[str, Any],
    context_dict: Dict[str, Any],
    fallback_variables: List[str],
) -> str:
    if not isinstance(exposure, dict):
        return ""

    raw_variables = exposure.get("variables") or fallback_variables or []
    variables = [str(var).strip() for var in raw_variables if isinstance(var, str) and str(var).strip()]
    if not variables:
        return ""

    null_label = exposure.get("null_label")
    mapping = defaultdict(lambda: _stringify_context_value(None, null_label))

    for key, value in context_dict.items():
        mapping[key] = _stringify_context_value(value, null_label if key in variables else None)

    for var in variables:
        if var not in mapping:
            mapping[var] = _stringify_context_value(context_dict.get(var), null_label)

    template = exposure.get("template")
    if template:
        rendered_body = _format_template(str(template), mapping)
    else:
        rendered_body = "\n".join(f"{var.upper()}: {mapping[var]}" for var in variables)

    if not isinstance(rendered_body, str) or not rendered_body.strip():
        return ""

    header = exposure.get("header")
    if isinstance(header, str) and header.strip():
        return f"{header.strip()}\n{rendered_body.strip()}"

    return rendered_body.strip()


def _merge_message_parts(existing: str, fragment: str, placement: str) -> str:
    placement_mode = (placement or "append").lower() if isinstance(placement, str) else "append"
    fragment = fragment.strip() if isinstance(fragment, str) else ""
    existing = existing.strip() if isinstance(existing, str) else ""
    if not fragment:
        return existing
    if placement_mode == "replace":
        return fragment
    if placement_mode == "prepend":
        parts = [fragment, existing]
    else:
        parts = [existing, fragment]
    joined = "\n\n".join(part for part in parts if part)
    return joined


def _apply_context_exposures(
    base_message: str,
    exposures: List[Dict[str, Any]],
    context_dict: Dict[str, Any],
    fallback_variables: List[str],
) -> str:
    effective_exposures: List[Dict[str, Any]] = [
        exposure for exposure in exposures if isinstance(exposure, dict)
    ]
    if not effective_exposures and fallback_variables:
        effective_exposures = [{"variables": list(fallback_variables)}]

    message = base_message or ""
    for exposure in effective_exposures:
        fragment = _render_exposure_fragment(exposure, context_dict, fallback_variables)
        placement = exposure.get("placement", "append") if isinstance(exposure, dict) else "append"
        message = _merge_message_parts(message, fragment, placement)
    return message or base_message or ""


def _render_default_context_fragment(variables: List[str], context_dict: Dict[str, Any]) -> str:
    cleaned = [var.strip() for var in variables if isinstance(var, str) and var.strip()]
    if not cleaned:
        return ""
    lines = ["Context Variables"]
    for var in cleaned:
        value = _stringify_context_value(context_dict.get(var), "null")
        lines.append(f"{var.upper()}: {value}")
    return "\n".join(lines)


def _build_exposure_update_hook(
    agent_name: str,
    base_message: str,
    exposures: List[Dict[str, Any]],
    fallback_variables: List[str],
):
    valid_exposures = [exp for exp in exposures if isinstance(exp, dict)]
    if not valid_exposures:
        return None

    def _update(agent: ConversableAgent, messages: List[Dict[str, Any]]) -> str:
        container = getattr(agent, "context_variables", None)
        context_dict = _context_to_dict(container) if container is not None else {}
        logger.debug(f"[UpdateSystemMessage][{agent_name}] context snapshot: {context_dict}")
        updated = _apply_context_exposures(base_message, valid_exposures, context_dict, fallback_variables)
        if hasattr(agent, "update_system_message") and callable(agent.update_system_message):
            agent.update_system_message(updated or base_message or "")
        return updated or base_message or ""

    _update.__annotations__ = {
        "agent": ConversableAgent,
        "messages": List[Dict[str, Any]],
        "return": str,
    }
    _update.__name__ = f"{agent_name.lower()}_context_update"
    return UpdateSystemMessage(_update)


def _build_interview_message_hook(
    exposures: List[Dict[str, Any]],
    fallback_variables: List[str],
) -> Callable[..., Any]:
    exposures_copy = [exp.copy() for exp in exposures if isinstance(exp, dict)] or []

    def _hook(sender=None, message=None, recipient=None, silent=False):
        try:
            raw_message = message.get("content") if isinstance(message, dict) else message
            if not isinstance(raw_message, str):
                return message
            trimmed = raw_message.strip()
            if trimmed.upper().startswith("NEXT"):
                final = "NEXT"
            else:
                container = getattr(sender, "context_variables", None)
                context_dict = _context_to_dict(container) if container is not None else {}

                if fallback_variables:
                    visible_snapshot: Dict[str, str] = {}
                    for var in fallback_variables:
                        if not isinstance(var, str) or not var.strip():
                            continue
                        value = _stringify_context_value(context_dict.get(var), "null")
                        if len(value) > 500:
                            value = f"{value[:497]}..."
                        visible_snapshot[var] = value
                    if visible_snapshot:
                        logger.info(
                            "[InterviewAgent] Context variables snapshot",
                            extra={"variables": visible_snapshot},
                        )

                if exposures_copy:
                    fragment = _apply_context_exposures("", exposures_copy, context_dict, fallback_variables).strip()
                else:
                    fragment = _render_default_context_fragment(fallback_variables, context_dict).strip()
                if fragment:
                    header, _, body = fragment.partition("\n")
                    header = header.strip() or "Context Variables"
                    body = body.strip()
                    if not body:
                        body = "null"
                    context_block = f"{header}:\n{body}"
                else:
                    context_block = "Context Variables:\nnull"
                question_line = "What would you like to automate?"
                final = f"{question_line}\n\n{context_block}".strip()
            logger.debug(f"[InterviewAgent] normalized outgoing message: {final!r}")
            if isinstance(message, dict):
                updated = dict(message)
                updated["content"] = final
                return updated
            return final
        except Exception as hook_err:  # pragma: no cover
            logger.debug(f"[InterviewAgent] message normalization skipped: {hook_err}")
            return message

    return _hook


async def create_agents(
    workflow_name: str,
    context_variables=None,
    cache_seed: Optional[int] = None,
) -> Dict[str, ConversableAgent]:
    """Create ConversableAgent instances for a workflow."""

    logger.info(f"[AGENTS] Creating agents for workflow: {workflow_name}")
    from time import perf_counter

    start_time = perf_counter()
    workflow_config = workflow_manager.get_config(workflow_name) or {}
    agent_configs = workflow_config.get("agents", {})
    if "agents" in agent_configs:
        agent_configs = agent_configs["agents"]

    try:
        from ..validation.llm_config import get_llm_config as _get_base_llm_config

        extra = {"cache_seed": cache_seed} if cache_seed is not None else None
        _, base_llm_config = await _get_base_llm_config(stream=True, extra_config=extra)
    except Exception as err:
        logger.error(f"[AGENTS] Failed to load base LLM config: {err}")
        return {}

    try:
        from .tools import load_agent_tool_functions

        agent_tool_functions = load_agent_tool_functions(workflow_name)
    except Exception as tool_err:
        logger.warning(f"[AGENTS] Failed loading agent tool functions: {tool_err}")
        agent_tool_functions = {}

    try:
        structured_registry = get_structured_outputs_for_workflow(workflow_name)
    except Exception as so_err:
        structured_registry = {}
        logger.debug(f"[AGENTS] Structured outputs unavailable for '{workflow_name}': {so_err}")

    if context_variables is not None:
        try:
            context_dict: Dict[str, Any] = _context_to_dict(context_variables)
            logger.debug(f"[AGENTS] context_variables snapshot: {context_dict}")
        except Exception as ctx_err:
            logger.debug(f"[AGENTS] context_variables snapshot unavailable: {ctx_err}")
            context_dict = {}
    else:
        context_dict = {}
    exposures_map = (
        getattr(context_variables, "_mozaiks_context_exposures", {}) if context_variables is not None else {}
    )
    agent_plan_map = (
        getattr(context_variables, "_mozaiks_context_agents", {}) if context_variables is not None else {}
    )

    agents: Dict[str, ConversableAgent] = {}

    for agent_name, agent_config in agent_configs.items():
        try:
            from ..outputs.structured import get_llm_for_workflow as _get_structured_llm

            extra = {"cache_seed": cache_seed} if cache_seed is not None else None
            _, llm_config = await _get_structured_llm(
                workflow_name,
                "base",
                agent_name=agent_name,
                extra_config=extra,
            )
        except Exception:
            llm_config = base_llm_config

        auto_tool_mode = bool(agent_config.get("auto_tool_mode"))
        structured_model_cls = structured_registry.get(agent_name) if structured_registry else None
        if auto_tool_mode and structured_model_cls is None:
            raise ValueError(
                f"[AGENTS] auto_tool_mode enabled for '{agent_name}' but no structured output model is registered"
            )

        agent_functions = [] if auto_tool_mode else agent_tool_functions.get(agent_name, [])
        for idx, fn in enumerate(agent_functions):
            if not callable(fn):
                logger.error(
                    f"[AGENTS] Tool function at index {idx} for agent '{agent_name}' is not callable: {fn}"
                )

        if isinstance(llm_config, dict):
            if "tools" not in llm_config:
                llm_config["tools"] = []
            elif auto_tool_mode:
                llm_config["tools"] = []

        system_message = agent_config.get("system_message", "You are a helpful AI assistant.")
        agent_exposures = []
        if isinstance(exposures_map, dict):
            agent_exposures = exposures_map.get(agent_name, []) or []

        agent_plan = None
        if isinstance(agent_plan_map, dict):
            agent_plan = agent_plan_map.get(agent_name)
        agent_variables = list(getattr(agent_plan, "variables", []) or [])

        base_system_message = system_message
        update_hooks: List[Callable[..., Any] | UpdateSystemMessage] = []
        if agent_exposures:
            system_message = _apply_context_exposures(
                base_system_message,
                agent_exposures,
                context_dict,
                agent_variables,
            )
            exposure_hook = _build_exposure_update_hook(
                agent_name,
                base_system_message,
                agent_exposures,
                agent_variables,
            )
            if exposure_hook:
                update_hooks.append(exposure_hook)
        else:
            system_message = base_system_message

##################################################################################################
        interview_message_hook = None
        if agent_name == "InterviewAgent":
            interview_message_hook = _build_interview_message_hook(agent_exposures, agent_variables)
##################################################################################################
        try:
            raw_human_mode = agent_config.get("human_input_mode")
            if raw_human_mode and str(raw_human_mode).upper() not in ("", "NEVER", "NONE"):
                logger.debug(
                    f"[AGENTS] Ignoring configured human_input_mode {raw_human_mode} for {agent_name}; enforcing NEVER"
                )
            human_input_mode = "NEVER"

            agent = ConversableAgent(
                name=agent_name,
                system_message=system_message,
                llm_config=llm_config,
                human_input_mode=human_input_mode,
                max_consecutive_auto_reply=agent_config.get("max_consecutive_auto_reply", 2),
                functions=agent_functions,
                context_variables=context_variables,
                update_agent_state_before_reply=update_hooks or None,
            )
###################################################################################################
            if agent_name == "InterviewAgent" and interview_message_hook:
                agent.register_hook("process_message_before_send", interview_message_hook)
###################################################################################################
        except Exception as err:
            logger.error(f"[AGENTS] CRITICAL ERROR creating ConversableAgent {agent_name}: {err}")
            raise

        # ==============================================================================
        # IMAGE GENERATION CAPABILITY (AG2 addon)
        # ==============================================================================
        if agent_config.get("image_generation_enabled", False):
            logger.info(f"[AGENTS][CAPABILITY] Image generation enabled for {agent_name} - attaching AG2 capability")
            
            try:
                # Import AG2 image generation components
                from autogen.agentchat.contrib.capabilities import generate_images
                
                logger.debug(f"[AGENTS][CAPABILITY] Imported AG2 generate_images module for {agent_name}")
                
                # Load DALL-E specific config
                from ..validation.llm_config import get_dalle_llm_config
                dalle_config = await get_dalle_llm_config(cache_seed=cache_seed)
                
                logger.info(
                    f"[AGENTS][CAPABILITY] Built DALL-E config for {agent_name}: "
                    f"model={dalle_config['config_list'][0].get('model')}"
                )
                
                # Create DALL-E image generator
                dalle_gen = generate_images.DalleImageGenerator(
                    llm_config=dalle_config,
                    resolution="1024x1024",  # Default, can be made configurable
                    quality="standard",       # Default, can be made configurable
                    num_images=1
                )
                
                logger.debug(f"[AGENTS][CAPABILITY] Created DalleImageGenerator for {agent_name}")
                
                # Create image generation capability
                image_capability = generate_images.ImageGeneration(
                    image_generator=dalle_gen,
                    text_analyzer_llm_config=llm_config,  # Use main config for text analysis
                    verbosity=1  # Set to 2 for full debug logs
                )
                
                logger.debug(f"[AGENTS][CAPABILITY] Created ImageGeneration capability for {agent_name}")
                
                # Attach capability to agent
                image_capability.add_to_agent(agent)
                
                logger.info(
                    f"[AGENTS][CAPABILITY] ✓ Successfully attached image generation capability to {agent_name} "
                    f"(DALL-E model={dalle_config['config_list'][0].get('model')}, resolution=1024x1024)"
                )
                
                # Mark agent with capability flag for runtime introspection
                setattr(agent, "_mozaiks_has_image_generation", True)
                
            except ImportError as imp_err:
                logger.error(
                    f"[AGENTS][CAPABILITY] Failed to import AG2 image generation for {agent_name}: {imp_err}. "
                    f"Install with: pip install ag2[lmm,openai]"
                )
                raise
            except Exception as cap_err:
                logger.error(
                    f"[AGENTS][CAPABILITY] Failed to attach image generation capability to {agent_name}: {cap_err}",
                    exc_info=True
                )
                raise

        setattr(agent, "_mozaiks_auto_tool_mode", auto_tool_mode)
        if structured_model_cls is not None:
            try:
                model_name = getattr(structured_model_cls, "__name__", None)
            except Exception:
                model_name = None
            if model_name:
                setattr(agent, "_mozaiks_structured_model_name", model_name)
            setattr(agent, "_mozaiks_structured_model_cls", structured_model_cls)
        setattr(agent, "_mozaiks_base_system_message", base_system_message)
        agents[agent_name] = agent

    duration = perf_counter() - start_time
    logger.info(f"[AGENTS] Created {len(agents)} agents for '{workflow_name}' in {duration:.2f}s")

    try:
        from logs.logging_config import get_workflow_session_logger

        workflow_logger = get_workflow_session_logger(workflow_name)
        total_tools = sum(len(tools) for tools in agent_tool_functions.values())
        workflow_logger.log_tool_binding_summary("ALL_AGENTS", total_tools, list(agent_tool_functions.keys()))
    except Exception:
        logger.debug("[AGENTS] Tool binding summary skipped")

    try:
        from ..workflow_manager import get_workflow_manager

        wm = get_workflow_manager()
        already_loaded = workflow_name in getattr(wm, "_hooks_loaded_workflows", set())
        registered = wm.register_hooks(workflow_name, agents, force=False)
        if registered:
            logger.info(
                f"[HOOKS] Registered {len(registered)} hooks for '{workflow_name}' (already_loaded={already_loaded})"
            )
    except Exception as hook_err:  # pragma: no cover
        logger.warning(f"[HOOKS] Failed to register hooks for '{workflow_name}': {hook_err}")

    return agents


# ------------------------------------------------------------------
# RUNTIME INSPECTION UTILITIES
# ------------------------------------------------------------------

def list_agent_hooks(agent: Any) -> Dict[str, List[str]]:
    """Return a mapping of hook_type -> list of function names for a given agent."""

    out: Dict[str, List[str]] = {}
    try:
        for attr in ("_hooks", "hooks"):
            if hasattr(agent, attr):
                raw = getattr(agent, attr)
                if isinstance(raw, dict):
                    for htype, fns in raw.items():
                        names: List[str] = []
                        try:
                            for fn in fns or []:  # type: ignore
                                names.append(getattr(fn, "__name__", repr(fn)))
                        except Exception:
                            names.append("<error>")
                        out[htype] = names
                break
    except Exception:
        pass
    return out


def list_hooks_for_workflow(agents: Dict[str, Any]) -> Dict[str, Dict[str, List[str]]]:
    """Return hooks per agent for an agents dict."""

    return {name: list_agent_hooks(agent) for name, agent in agents.items()}


__all__ = [
    "create_agents",
    "extract_images_from_conversation",
    "list_agent_hooks",
    "list_hooks_for_workflow",
]



