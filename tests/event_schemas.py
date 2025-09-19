from __future__ import annotations

"""JSON Schemas for WebSocket event envelopes used by ChatUI.

These are intentionally minimal and forward-compatible: we only pin
fields the frontend relies on so backend additions don't break tests.
"""

CHAT_TEXT_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["type", "data"],
    "properties": {
        "type": {"const": "chat.text"},
        "data": {
            "type": "object",
            "required": ["content"],
            "properties": {
                "content": {"type": "string"},
                "agent": {"type": ["string", "null"]},
                "sequence": {"type": ["integer", "null"]},
                "is_visual": {"type": ["boolean", "null"]},
                "is_structured_capable": {"type": ["boolean", "null"]},
                "is_tool_agent": {"type": ["boolean", "null"]},
            },
            "additionalProperties": True,
        },
        "timestamp": {"type": ["string", "null"]},
    },
    "additionalProperties": True,
}

CHAT_TOOL_CALL_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "required": ["type", "data"],
    "properties": {
        "type": {"const": "chat.tool_call"},
        "data": {
            "type": "object",
            "required": ["tool_name", "component_type", "payload"],
            "properties": {
                "tool_name": {"type": "string"},
                "component_type": {"type": "string"},
                "awaiting_response": {"type": ["boolean", "null"]},
                "payload": {
                    "type": "object",
                    "required": ["workflow_name"],
                    "properties": {
                        "workflow_name": {"type": "string"},
                        "display": {"type": ["string", "null"], "enum": ["inline", "artifact", None]},
                        "component_type": {"type": ["string", "null"]},
                        "content": {"type": ["string", "object", "null"]},
                    },
                    "additionalProperties": True,
                },
                "corr": {"type": ["string", "null"]},
            },
            "additionalProperties": True,
        },
        "timestamp": {"type": ["string", "null"]},
    },
    "additionalProperties": True,
}

SCHEMAS = {
    "chat.text": CHAT_TEXT_SCHEMA,
    "chat.tool_call": CHAT_TOOL_CALL_SCHEMA,
}

def get_schema(event_type: str):
    return SCHEMAS.get(event_type)
