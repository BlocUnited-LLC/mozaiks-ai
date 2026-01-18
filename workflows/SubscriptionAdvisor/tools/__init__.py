"""
SubscriptionAdvisor Tools

Advisory-only tools for subscription recommendations.
All tools enforce: read_only=true, no_external_mutations=true, tenant_scoped=true
"""

from .read_platform_kpis import read_platform_kpis, TOOL_CONSTRAINTS as PLATFORM_KPI_CONSTRAINTS
from .read_app_telemetry import read_app_telemetry, TOOL_CONSTRAINTS as APP_TELEMETRY_CONSTRAINTS
from .generate_platform_advisory import generate_platform_advisory, TOOL_CONSTRAINTS as PLATFORM_ADVISORY_CONSTRAINTS
from .generate_app_advisory import generate_app_advisory, TOOL_CONSTRAINTS as APP_ADVISORY_CONSTRAINTS

__all__ = [
    "read_platform_kpis",
    "read_app_telemetry",
    "generate_platform_advisory",
    "generate_app_advisory",
    # Constraint exports for testing
    "PLATFORM_KPI_CONSTRAINTS",
    "APP_TELEMETRY_CONSTRAINTS",
    "PLATFORM_ADVISORY_CONSTRAINTS",
    "APP_ADVISORY_CONSTRAINTS",
]

# Aggregate constraints for validation
ALL_TOOL_CONSTRAINTS = {
    "read_platform_kpis": PLATFORM_KPI_CONSTRAINTS,
    "read_app_telemetry": APP_TELEMETRY_CONSTRAINTS,
    "generate_platform_advisory": PLATFORM_ADVISORY_CONSTRAINTS,
    "generate_app_advisory": APP_ADVISORY_CONSTRAINTS,
}


def validate_all_constraints() -> bool:
    """
    Validate that all tools declare required constraints.
    Used by runtime and tests to ensure advisory-only behavior.
    """
    required = {"read_only", "no_external_mutations", "tenant_scoped"}
    
    for tool_name, constraints in ALL_TOOL_CONSTRAINTS.items():
        for req in required:
            if not constraints.get(req):
                raise ValueError(
                    f"Tool '{tool_name}' missing required constraint: {req}"
                )
    
    return True
