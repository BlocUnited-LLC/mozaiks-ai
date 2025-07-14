# ==============================================================================
# FILE: core/capabilities/config.py  
# DESCRIPTION: Configuration for modular capabilities including budget settings
# ==============================================================================

# Budget Mode Configuration
# Change this value to switch between different budget modes:
# - "commercial": Full TokenManager with free trials and API billing
# - "opensource": Unlimited usage without commercial features
# - "testing": Development mode without real API calls

BUDGET_MODE = "commercial"

# Open Source Distribution Settings
# When preparing for open source release, set OPEN_SOURCE_MODE = False
# This will automatically use "opensource" budget mode and disable commercial features
OPEN_SOURCE_MODE = False

# Free Trial Configuration
FREE_TRIAL_LOOPS = 3           # Number of free loops for new users
FREE_TRIAL_TURN_LIMIT = 10     # Turn limit during free trial
MIN_TOKEN_THRESHOLD = 50       # Minimum tokens before showing warnings

# Feature Flags
ENABLE_FREE_TRIALS = not OPEN_SOURCE_MODE
ENABLE_TOKEN_BILLING = not OPEN_SOURCE_MODE
ENABLE_USAGE_LIMITS = not OPEN_SOURCE_MODE

def get_budget_mode() -> str:
    """Get the current budget mode, respecting open source distribution setting."""
    if OPEN_SOURCE_MODE:
        return "opensource"
    return BUDGET_MODE

def get_free_trial_config() -> dict:
    """Get free trial configuration settings."""
    return {
        "loops": FREE_TRIAL_LOOPS,
        "turn_limit": FREE_TRIAL_TURN_LIMIT,
        "min_token_threshold": MIN_TOKEN_THRESHOLD
    }
