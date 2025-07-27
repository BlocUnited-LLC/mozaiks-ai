# Modular Budget Capability System

## Overview

The budget capability system provides a clean, modular way to handle budget management, free trials, and token billing. This design makes it easy to switch between different deployment modes or completely remove commercial features for open source distribution.

## Architecture

### Core Components

1. **`BudgetCapability`** - Abstract base class defining the interface
2. **`CommercialBudgetCapability`** - Full TokenManager integration with free trials and API billing
3. **`OpenSourceBudgetCapability`** - Unlimited usage without commercial restrictions
4. **`TestingBudgetCapability`** - Development mode without real API calls
5. **`BudgetCapabilityFactory`** - Creates appropriate capability based on configuration

### Configuration

The system is controlled by simple configuration in `core/capabilities/config.py`:

```python
# Budget Mode Configuration
BUDGET_MODE = "testing"  # "commercial", "opensource", or "testing"

# Open Source Distribution Settings  
OPEN_SOURCE_MODE = False  # Set to True for open source release
```

## Usage Modes

### 1. Commercial Mode (`BUDGET_MODE = "commercial"`)

**Features:**
- Full TokenManager integration
- Free trial system (3 loops for new enterprises)
- Token billing via external API
- Usage limits and budget enforcement
- Turn limits (10 for free trial, unlimited for paid)

**Use Case:** Production SaaS deployment with monetization

### 2. Open Source Mode (`BUDGET_MODE = "opensource"`)

**Features:**
- Unlimited usage for all users
- No token billing or API calls
- No budget restrictions
- Minimal logging without commercial tracking

**Use Case:** Open source distribution, community deployments

### 3. Testing Mode (`BUDGET_MODE = "testing"`)

**Features:**
- Mock budget functionality
- No real API calls
- Development-friendly logging
- Safe for local development

**Use Case:** Development, testing, CI/CD

## Easy Mode Switching

### Method 1: Configuration File

Edit `core/capabilities/config.py`:

```python
# For open source release
OPEN_SOURCE_MODE = True  # Automatically uses "opensource" mode

# For commercial deployment  
OPEN_SOURCE_MODE = False
BUDGET_MODE = "commercial"

# For development
OPEN_SOURCE_MODE = False  
BUDGET_MODE = "testing"
```

### Method 2: Script-Based Switching

Use the provided script:

```bash
# Check current mode
python switch_mode.py status

# Switch to open source mode
python switch_mode.py opensource

# Switch to commercial mode  
python switch_mode.py commercial
```

## Integration

The modular capability integrates seamlessly with the existing groupchat manager:

```python
# Old tightly-coupled approach
token_manager = TokenManager(chat_id, enterprise_id, workflow_name, user_id)
budget_info = await token_manager.initialize_budget(user_id)

# New modular approach
budget_capability = get_budget_capability(chat_id, enterprise_id, workflow_name, user_id)
budget_info = await budget_capability.initialize_budget()
```

## Benefits for Open Source Distribution

### Clean Separation
- All commercial logic is isolated in specific capability classes
- Core groupchat functionality works without any budget dependencies
- Easy to remove commercial files entirely for open source

### Zero Configuration Required
- Open source users get unlimited usage by default
- No need to configure external APIs or token systems
- Works out-of-the-box for community deployments

### Professional Architecture
- Follows AG2's capability pattern from their documentation
- Clean interfaces and dependency injection
- Easy to extend with additional capability types

## Migration Path

### From Current System
1. Replace hardcoded TokenManager initialization with `get_budget_capability()`
2. Update token tracking calls to use `budget_capability.update_usage()`
3. Replace budget checks with `budget_capability.check_budget_limits()`

### For Open Source Release
1. Set `OPEN_SOURCE_MODE = True` in config
2. Optional: Remove commercial capability files entirely
3. Optional: Remove TokenManager and related infrastructure
4. Test with "opensource" mode to ensure full functionality

## Code Examples

### Basic Usage

```python
from core.capabilities import get_budget_capability

# Get appropriate capability for current mode
budget_capability = get_budget_capability(chat_id, enterprise_id, workflow_name, user_id)

# Initialize budget (works in all modes)
budget_info = await budget_capability.initialize_budget()

# Check if can continue (respects mode-specific limits)
check_result = await budget_capability.check_budget_limits()
if not check_result.get("can_continue", True):
    raise ValueError(check_result.get("message", "Budget limits exceeded"))

# Update usage (tracks appropriately for each mode)
await budget_capability.update_usage(agents)
```

### Mode-Specific Behavior

```python
# Commercial mode
budget_capability = CommercialBudgetCapability(...)
await budget_capability.initialize_budget()  # Sets up free trials, checks API balance
await budget_capability.update_usage(agents)  # Bills tokens via API

# Open source mode  
budget_capability = OpenSourceBudgetCapability(...)
await budget_capability.initialize_budget()  # Returns unlimited budget
await budget_capability.update_usage(agents)  # Logs usage without billing

# Testing mode
budget_capability = TestingBudgetCapability(...)
await budget_capability.initialize_budget()  # Mock budget setup
await budget_capability.update_usage(agents)  # Mock usage tracking
```

This modular design makes it trivial to switch between commercial and open source modes, while maintaining clean architecture and full functionality in both scenarios.
