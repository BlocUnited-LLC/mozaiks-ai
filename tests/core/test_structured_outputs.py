"""
Structured outputs tests - Pydantic model generation.
"""

import pytest


class TestStructuredOutputs:
    """Test structured output generation."""

    def test_structured_outputs_import(self):
        """Verify structured outputs module can be imported."""
        from mozaiksai.core.workflow.outputs import structured
        assert structured is not None

    def test_pydantic_model_generator(self):
        """Verify Pydantic model can be generated from schema."""
        from mozaiksai.core.workflow.outputs.structured import create_pydantic_model_from_schema
        
        schema = {
            "name": "TestModel",
            "fields": [
                {"name": "message", "type": "str", "description": "A test message"}
            ]
        }
        
        Model = create_pydantic_model_from_schema(schema)
        assert Model is not None
        assert Model.__name__ == "TestModel"
        
        # Should be able to instantiate
        instance = Model(message="hello")
        assert instance.message == "hello"
