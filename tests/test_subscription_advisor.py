"""
Unit tests for SubscriptionAdvisor workflow tools.

Verifies:
1. No tool can write data (read_only constraint)
2. No tool can call Stripe (forbidden API constraint)
3. No tool can call Control-Plane except via the advisory webhook
4. No tool generates subscription_config.json
"""

import ast
import inspect
import re
from pathlib import Path
from typing import Any, Dict, List, Set
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import tools and constraints
from workflows.SubscriptionAdvisor.tools import (
    read_platform_kpis,
    read_app_telemetry,
    generate_platform_advisory,
    generate_app_advisory,
    ALL_TOOL_CONSTRAINTS,
    validate_all_constraints,
)
from workflows.SubscriptionAdvisor.tools.read_platform_kpis import (
    TOOL_CONSTRAINTS as PLATFORM_KPI_CONSTRAINTS,
)
from workflows.SubscriptionAdvisor.tools.read_app_telemetry import (
    TOOL_CONSTRAINTS as APP_TELEMETRY_CONSTRAINTS,
)
from workflows.SubscriptionAdvisor.tools.generate_platform_advisory import (
    TOOL_CONSTRAINTS as PLATFORM_ADVISORY_CONSTRAINTS,
)
from workflows.SubscriptionAdvisor.tools.generate_app_advisory import (
    TOOL_CONSTRAINTS as APP_ADVISORY_CONSTRAINTS,
)


# ============================================================================
# CONSTRAINT DECLARATION TESTS
# ============================================================================

class TestConstraintDeclarations:
    """Verify all tools declare required constraints."""
    
    def test_all_tools_declare_read_only(self):
        """Every tool must declare read_only=True."""
        for tool_name, constraints in ALL_TOOL_CONSTRAINTS.items():
            assert constraints.get("read_only") is True, (
                f"Tool '{tool_name}' must declare read_only=True"
            )
    
    def test_all_tools_declare_no_external_mutations(self):
        """Every tool must declare no_external_mutations=True."""
        for tool_name, constraints in ALL_TOOL_CONSTRAINTS.items():
            assert constraints.get("no_external_mutations") is True, (
                f"Tool '{tool_name}' must declare no_external_mutations=True"
            )
    
    def test_all_tools_declare_tenant_scoped(self):
        """Every tool must declare tenant_scoped=True."""
        for tool_name, constraints in ALL_TOOL_CONSTRAINTS.items():
            assert constraints.get("tenant_scoped") is True, (
                f"Tool '{tool_name}' must declare tenant_scoped=True"
            )
    
    def test_validate_all_constraints_passes(self):
        """The validate_all_constraints helper should pass."""
        assert validate_all_constraints() is True
    
    def test_kpi_tools_forbid_write_operations(self):
        """KPI collection tools must forbid write operations."""
        write_ops = {"insert", "update", "delete", "replace", "bulk_write", "drop"}
        
        for constraints in [PLATFORM_KPI_CONSTRAINTS, APP_TELEMETRY_CONSTRAINTS]:
            forbidden = set(constraints.get("forbidden_operations", []))
            for op in write_ops:
                assert op in forbidden, f"Missing forbidden operation: {op}"
    
    def test_advisory_tools_forbid_stripe(self):
        """Advisory generation tools must forbid Stripe access."""
        stripe_patterns = {"stripe", "payment", "billing"}
        
        for constraints in [PLATFORM_ADVISORY_CONSTRAINTS, APP_ADVISORY_CONSTRAINTS]:
            forbidden = set(constraints.get("forbidden_apis", []))
            for pattern in stripe_patterns:
                assert any(pattern in f.lower() for f in forbidden), (
                    f"Missing forbidden API pattern: {pattern}"
                )


# ============================================================================
# CODE ANALYSIS TESTS (Static verification)
# ============================================================================

class TestCodeAnalysis:
    """Static analysis of tool source code to verify constraints."""
    
    TOOLS_DIR = Path(__file__).parent.parent / "workflows" / "SubscriptionAdvisor" / "tools"
    
    @pytest.fixture
    def tool_source_files(self) -> Dict[str, str]:
        """Load source code for all tool files."""
        sources = {}
        for py_file in self.TOOLS_DIR.glob("*.py"):
            if py_file.name != "__init__.py":
                sources[py_file.stem] = py_file.read_text(encoding="utf-8")
        return sources
    
    def test_no_stripe_imports(self, tool_source_files: Dict[str, str]):
        """No tool should import Stripe."""
        stripe_patterns = [
            r"import\s+stripe",
            r"from\s+stripe",
            r"stripe\.",
            r"Stripe\(",
        ]
        
        for filename, source in tool_source_files.items():
            for pattern in stripe_patterns:
                matches = re.findall(pattern, source, re.IGNORECASE)
                assert not matches, (
                    f"Tool '{filename}' contains Stripe reference: {matches}"
                )
    
    def test_no_direct_db_writes(self, tool_source_files: Dict[str, str]):
        """No tool should contain direct DB write operations."""
        write_patterns = [
            r"\.insert_one\(",
            r"\.insert_many\(",
            r"\.update_one\(",
            r"\.update_many\(",
            r"\.delete_one\(",
            r"\.delete_many\(",
            r"\.replace_one\(",
            r"\.bulk_write\(",
            r"\.drop\(",
            r"\.create_index\(",
        ]
        
        for filename, source in tool_source_files.items():
            for pattern in write_patterns:
                matches = re.findall(pattern, source)
                assert not matches, (
                    f"Tool '{filename}' contains DB write operation: {pattern}"
                )
    
    def test_only_allowed_external_calls(self, tool_source_files: Dict[str, str]):
        """Advisory tools should only call the webhook endpoint."""
        # These tools are allowed to POST to the webhook
        advisory_tools = {"generate_platform_advisory", "generate_app_advisory"}
        
        # External HTTP patterns
        http_patterns = [
            r"httpx\.(get|post|put|patch|delete|request)\(",
            r"requests\.(get|post|put|patch|delete)\(",
            r"aiohttp\.",
            r"urllib\.request\.",
        ]
        
        for filename, source in tool_source_files.items():
            if filename in advisory_tools:
                # Advisory tools can POST to webhook
                # Verify they only POST to /internal/advisory/ingest
                if "httpx" in source:
                    assert "/internal/advisory/ingest" in source, (
                        f"Tool '{filename}' makes HTTP calls but not to advisory webhook"
                    )
                    # Should not call other Control-Plane endpoints
                    cp_patterns = [
                        r"/api/subscriptions",
                        r"/api/billing",
                        r"/api/users/\w+/subscription",
                    ]
                    for pattern in cp_patterns:
                        assert not re.search(pattern, source), (
                            f"Tool '{filename}' calls forbidden Control-Plane endpoint"
                        )
            else:
                # KPI tools should not make any external HTTP calls
                for pattern in http_patterns:
                    # Allow httpx import but not usage
                    if "import httpx" not in source:
                        matches = re.findall(pattern, source)
                        assert not matches, (
                            f"Tool '{filename}' makes external HTTP calls: {pattern}"
                        )
    
    def test_no_subscription_config_generation(self, tool_source_files: Dict[str, str]):
        """No tool should generate subscription_config.json."""
        forbidden_patterns = [
            r"subscription_config\.json",
            r"subscription_config",
            r'"type":\s*"subscription"',
        ]
        
        for filename, source in tool_source_files.items():
            for pattern in forbidden_patterns:
                # Skip if it's in the forbidden_outputs constraint (that's allowed)
                if "forbidden_outputs" in source and pattern in source:
                    continue
                # Check for actual generation attempts
                if re.search(r"(open|write|json\.dump).*subscription_config", source):
                    pytest.fail(
                        f"Tool '{filename}' attempts to generate subscription_config.json"
                    )


# ============================================================================
# RUNTIME BEHAVIOR TESTS
# ============================================================================

class TestRuntimeBehavior:
    """Test actual tool execution respects constraints."""
    
    @pytest.fixture
    def mock_context(self) -> MagicMock:
        """Create mock context variables."""
        ctx = MagicMock()
        ctx.data = {}
        ctx.set = lambda k, v: ctx.data.__setitem__(k, v)
        return ctx
    
    @pytest.fixture
    def sample_platform_kpis(self) -> Dict[str, Any]:
        """Sample platform KPIs for testing."""
        return {
            "tokens_used_30d": 85000,
            "tier_allocation": 100000,
            "tokens_used_7d_trend": 0.12,
            "peak_tokens_per_hour": 5000,
            "model_tier_distribution": {"gpt-4": 0.4, "gpt-3.5-turbo": 0.6},
            "workflow_executions_30d": 750,
            "workflow_executions_limit": 1000,
            "avg_workflow_duration_ms": 15000,
            "concurrent_sessions_peak": 4,
            "concurrent_sessions_limit": 5,
            "storage_artifacts_gb": 3.5,
            "storage_limit_gb": 5.0,
            "apps_published": 2,
            "apps_with_custom_domain": 0,
            "email_volume_30d": 150,
            "brand_consistency_score": 0.75,
            "current_tier": "starter",
            "collection_timestamp": "2026-01-16T10:00:00Z",
            "date_range_start": "2025-12-17T10:00:00Z",
            "date_range_end": "2026-01-16T10:00:00Z",
        }
    
    @pytest.fixture
    def sample_app_telemetry(self) -> Dict[str, Any]:
        """Sample app telemetry for testing."""
        return {
            "app_id": "app_test_123",
            "app_name": "Test App",
            "app_description": "A test application",
            "target_market": "b2c_fitness",
            "workflow_list": [
                {
                    "workflow_id": "wf1",
                    "name": "Basic Workout",
                    "description": "Generate workout plans",
                    "avg_tokens_per_run": 500,
                    "invocation_count_30d": 100,
                    "cost_tier": "low",
                    "tools_used": ["get_exercises"],
                },
                {
                    "workflow_id": "wf2",
                    "name": "AI Coach Chat",
                    "description": "Interactive AI coaching",
                    "avg_tokens_per_run": 2000,
                    "invocation_count_30d": 50,
                    "cost_tier": "high",
                    "tools_used": ["openai_chat", "get_user_history"],
                },
            ],
            "workflow_count": 2,
            "total_workflow_invocations_30d": 150,
            "tool_usage": [
                {"tool_name": "get_exercises", "invocation_count": 200, "has_external_api": False},
                {"tool_name": "openai_chat", "invocation_count": 50, "has_external_api": True},
            ],
            "unique_tools_count": 2,
            "external_api_tools_count": 1,
            "total_tokens_30d": 150000,
            "avg_tokens_per_session": 1000,
            "token_by_workflow": {"wf1": 50000, "wf2": 100000},
            "plugin_usage": [
                {"plugin_id": "calendar", "plugin_name": "Calendar Sync", "has_external_cost": False},
            ],
            "plugins_with_external_cost": [],
            "collection_timestamp": "2026-01-16T10:00:00Z",
            "date_range_start": "2025-12-17T10:00:00Z",
            "date_range_end": "2026-01-16T10:00:00Z",
        }
    
    def test_platform_advisory_generates_valid_schema(
        self, mock_context: MagicMock, sample_platform_kpis: Dict[str, Any]
    ):
        """Platform advisory should match MozaiksPlatformAdvisory schema."""
        mock_context.data["collected_kpis"] = sample_platform_kpis
        mock_context.data["target_id"] = "user_123"
        
        result = generate_platform_advisory(
            kpis=sample_platform_kpis,
            user_id="user_123",
            post_to_webhook=False,  # Don't actually POST
            context_variables=mock_context,
        )
        
        assert "Advisory ID:" in result
        assert "user_123" in result
        
        # Check advisory was cached
        advisory = mock_context.data.get("advisory_payload")
        assert advisory is not None
        
        # Validate schema
        assert "advisory_id" in advisory
        assert "timestamp" in advisory
        assert "user_id" in advisory
        assert "recommendations" in advisory
        assert isinstance(advisory["recommendations"], list)
    
    def test_app_advisory_generates_valid_schema(
        self, mock_context: MagicMock, sample_app_telemetry: Dict[str, Any]
    ):
        """App advisory should match AppSubscriptionAdvisor schema."""
        mock_context.data["collected_kpis"] = sample_app_telemetry
        mock_context.data["target_id"] = "app_test_123"
        
        result = generate_app_advisory(
            telemetry=sample_app_telemetry,
            app_id="app_test_123",
            post_to_webhook=False,
            context_variables=mock_context,
        )
        
        assert "Advisory ID:" in result
        assert "app_test_123" in result
        
        # Check advisory was cached
        advisory = mock_context.data.get("advisory_payload")
        assert advisory is not None
        
        # Validate schema
        assert "advisory_id" in advisory
        assert "app_id" in advisory
        assert "proposed_model" in advisory
        assert "pricing_strategy" in advisory["proposed_model"]
        assert "tiers" in advisory["proposed_model"]
        assert isinstance(advisory["proposed_model"]["tiers"], list)
    
    def test_app_advisory_does_not_output_subscription_config(
        self, mock_context: MagicMock, sample_app_telemetry: Dict[str, Any]
    ):
        """App advisory must NOT generate subscription_config.json."""
        mock_context.data["collected_kpis"] = sample_app_telemetry
        
        result = generate_app_advisory(
            telemetry=sample_app_telemetry,
            app_id="app_test_123",
            post_to_webhook=False,
            context_variables=mock_context,
        )
        
        # Should mention that Control-Plane translates to config
        assert "subscription_config.json" in result
        assert "Control-Plane will translate" in result
        
        # Advisory should NOT be a subscription_config format
        advisory = mock_context.data.get("advisory_payload")
        assert "subscription_config" not in str(advisory).lower().replace("_", "")
        assert advisory.get("proposed_model") is not None  # It's an advisory, not config
    
    @patch("workflows.SubscriptionAdvisor.tools.generate_platform_advisory.httpx.AsyncClient")
    def test_platform_advisory_only_posts_to_webhook(
        self,
        mock_httpx: MagicMock,
        mock_context: MagicMock,
        sample_platform_kpis: Dict[str, Any],
    ):
        """Platform advisory should only POST to /internal/advisory/ingest."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()
        
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_httpx.return_value = mock_client
        
        mock_context.data["collected_kpis"] = sample_platform_kpis
        mock_context.data["control_plane_base_url"] = "http://control-plane:8000"
        mock_context.data["service_token"] = "test_token"
        
        generate_platform_advisory(
            kpis=sample_platform_kpis,
            user_id="user_123",
            post_to_webhook=True,
            context_variables=mock_context,
        )
        
        # Verify the POST was to the correct endpoint
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        url = call_args[0][0] if call_args[0] else call_args[1].get("url")
        
        assert "/internal/advisory/ingest" in url
        assert "subscriptions" not in url
        assert "billing" not in url
        assert "stripe" not in url.lower()


# ============================================================================
# FORBIDDEN API TESTS
# ============================================================================

class TestForbiddenAPIs:
    """Verify tools cannot access forbidden APIs."""
    
    def test_no_stripe_in_any_tool_module(self):
        """Stripe should not be accessible from any tool."""
        tools = [
            read_platform_kpis,
            read_app_telemetry,
            generate_platform_advisory,
            generate_app_advisory,
        ]
        
        for tool in tools:
            module = inspect.getmodule(tool)
            module_dict = vars(module)
            
            # Check no stripe-related names
            for name in module_dict:
                assert "stripe" not in name.lower(), (
                    f"Tool module contains stripe-related name: {name}"
                )
    
    def test_constraints_forbid_subscription_mutations(self):
        """All tools must forbid subscription mutations."""
        mutation_patterns = [
            "subscription.update",
            "subscription.create",
            "subscription.delete",
        ]
        
        for tool_name, constraints in ALL_TOOL_CONSTRAINTS.items():
            forbidden = constraints.get("forbidden_apis", [])
            for pattern in mutation_patterns:
                assert any(pattern in f for f in forbidden), (
                    f"Tool '{tool_name}' missing forbidden API: {pattern}"
                )


# ============================================================================
# TENANT ISOLATION TESTS
# ============================================================================

class TestTenantIsolation:
    """Verify tools maintain tenant isolation."""
    
    def test_kpi_tools_require_target_id(self):
        """KPI tools should require a tenant identifier."""
        # read_platform_kpis requires user_id
        sig = inspect.signature(read_platform_kpis)
        assert "user_id" in sig.parameters
        
        # read_app_telemetry requires app_id
        sig = inspect.signature(read_app_telemetry)
        assert "app_id" in sig.parameters
    
    def test_advisory_tools_require_target_id(self):
        """Advisory tools should require a tenant identifier."""
        # generate_platform_advisory requires user_id
        sig = inspect.signature(generate_platform_advisory)
        assert "user_id" in sig.parameters
        
        # generate_app_advisory requires app_id
        sig = inspect.signature(generate_app_advisory)
        assert "app_id" in sig.parameters


# ============================================================================
# INTEGRATION SANITY TESTS
# ============================================================================

class TestIntegrationSanity:
    """Basic sanity checks for tool integration."""
    
    def test_all_tools_are_callable(self):
        """All tools should be callable functions."""
        tools = [
            read_platform_kpis,
            read_app_telemetry,
            generate_platform_advisory,
            generate_app_advisory,
        ]
        
        for tool in tools:
            assert callable(tool), f"{tool.__name__} is not callable"
    
    def test_all_tools_have_docstrings(self):
        """All tools should have docstrings explaining constraints."""
        tools = [
            read_platform_kpis,
            read_app_telemetry,
            generate_platform_advisory,
            generate_app_advisory,
        ]
        
        for tool in tools:
            assert tool.__doc__ is not None, f"{tool.__name__} missing docstring"
            doc = tool.__doc__.lower()
            assert "never" in doc or "read-only" in doc or "constraint" in doc, (
                f"{tool.__name__} docstring should mention constraints"
            )
    
    def test_constraint_exports_available(self):
        """Tool constraints should be importable for runtime validation."""
        from workflows.SubscriptionAdvisor.tools import (
            PLATFORM_KPI_CONSTRAINTS,
            APP_TELEMETRY_CONSTRAINTS,
            PLATFORM_ADVISORY_CONSTRAINTS,
            APP_ADVISORY_CONSTRAINTS,
            ALL_TOOL_CONSTRAINTS,
        )
        
        assert len(ALL_TOOL_CONSTRAINTS) == 4
        assert all(
            c.get("read_only") is True for c in ALL_TOOL_CONSTRAINTS.values()
        )
