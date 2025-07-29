# Token Manager & Persistence Architecture Mapping

## Overview

Your existing detailed token management logic now works within the new two-level billing schema while preserving all fine-grained functionality.

## Architecture Summary

### Platform Level (Level 1) - Existing Logic Enhanced
**Use Case**: Mozaiks User creating/modifying apps
**Database**: Platform Database (`MozaiksPlatform`)

### App Level (Level 2) - Existing Logic Enhanced  
**Use Case**: App end users using deployed apps
**Database**: App Databases (`MozaiksApp_{enterprise_id}`)

## Fine-Grained Data Structures Preserved

### Level 1: Platform Operations
Your existing enterprise token tracking now captures:

```json
{
  "level": "platform",
  "mozaiks_user_id": "user_123",
  "enterprise_id": "app_456", 
  "workflow_type": "app_generation",
  "tokens_used": 15000,
  "cost": 0.45,
  "billing_target": "mozaiks_user",
  
  // Your existing fine-grained fields preserved:
  "session_id": "sess_abc123",
  "chat_id": "chat_def456", 
  "workflow_name": "Generator",
  "user_id": "platform_user_001",
  "agent_usage": {
    "ConceptAgent": {"prompt_tokens": 5000, "completion_tokens": 3000},
    "ArchitectAgent": {"prompt_tokens": 4000, "completion_tokens": 3000}
  },
  "started_at": "2025-07-28T10:00:00Z",
  "ended_at": "2025-07-28T10:15:00Z",
  "is_free_trial": false,
  "connection_state": "completed",
  "can_resume": false
}
```

### Level 2: App Usage
Your existing chat/session tracking now captures:

```json
{
  "level": "app_usage",
  "enterprise_id": "app_456",
  "mozaiks_user_id": "user_123", 
  "platform_user_id": "enduser_789",
  "workflow_type": "chat_interaction", 
  "tokens_used": 500,
  "cost": 0.015,
  "billing_target": "platform_user",
  "revenue_share": 0.003,
  "mozaiks_fee": 0.001,
  
  // Your existing fine-grained fields preserved:
  "session_id": "sess_xyz789",
  "chat_id": "chat_app_001",
  "workflow_name": "default",
  "agent_usage": {
    "CustomerAgent": {"prompt_tokens": 200, "completion_tokens": 300}
  },
  "started_at": "2025-07-28T14:00:00Z", 
  "ended_at": "2025-07-28T14:05:00Z",
  "is_free_trial": true,
  "trial_tokens_used": 1250,
  "connection_state": "active",
  "can_resume": true,
  "pause_reason": null
}
```

## Database Collections Mapping

### Level 1: Platform Database (`MozaiksPlatform`)
- `MozaiksUsers` - Your existing enterprise data enhanced
- `Enterprises` - App metadata 
- `PlatformSessions` - Your existing session tracking
- `PlatformUsage` - Your existing usage aggregation

### Level 2: App Databases (`MozaiksApp_{enterprise_id}`)
- `AppUsers` - End user token balances 
- `AppSessions` - Your existing session tracking per app
- `RevenueSharing` - New revenue calculations
- `PausedChats` - Your existing pause/resume logic

### Shared Workflow Database (`autogen_ai_agents`)
- `Workflows` - Your existing VE workflow tracking
- `TokenSessions` - Your existing detailed session logs
- `ChatPauses` - Your existing pause state management
- `TokenChats` - Your existing chat completion summaries

## Method Mapping

### Your Existing Token Manager Methods (Preserved)
```python
# Level 1 (Platform) - platform_token_manager.py
initialize_platform_budget()    # Enhanced with mozaiks_user_id
can_continue()                  # Same logic, platform context
track_platform_usage()         # Enhanced with subscription tracking
handle_no_tokens()             # Same pause logic, platform level
finalize_platform_session()    # Enhanced with platform billing

# Level 2 (App) - token_manager.py  
initialize_budget()            # Enhanced with platform_user_id + revenue sharing
can_continue()                 # Same logic, app context + trial limits
track_usage()                  # Enhanced with revenue sharing calculations
handle_no_tokens()             # Same pause logic, app level
finalize_session()             # Enhanced with revenue sharing data
```

### Your Existing Persistence Methods (Preserved)
```python
# VE Workflow Methods (Unchanged)
update_workflow_status()       # Still works for all workflows
update_conversation()          # Still works for all chats
save_chat_state()             # Still works for resume logic
can_resume_chat() / resume_chat() # Still works across both levels

# Token Management Methods (Enhanced)
load_enterprise_data()         # Now works for Level 1 billing
save_session()                # Now supports both Level 1 & 2
save_chat_pause()             # Now supports both levels
deduct_tokens()               # Now supports both enterprise & app users

# New Level 2 Methods (Added)
load_app_user_data()          # App end user token data
track_trial_usage()           # Free trial tracking per app
deduct_app_tokens()           # App user token deduction
save_app_session()            # App session with revenue sharing
```

## Key Enhancements

### 1. Revenue Sharing Logic
- All app usage automatically calculates revenue split
- 70% to mozaiks_user_id, 30% to Mozaiks platform
- Tracked in separate RevenueSharing collections

### 2. Dual Database Architecture
- Platform operations use Platform Database
- App operations use App-specific databases  
- Clean data isolation between apps

### 3. Backward Compatibility
- All your existing method signatures preserved
- All your existing data structures enhanced, not replaced
- All your existing workflow logic still works

### 4. Enhanced Mock Data
- Both levels support USE_MOCK_API flag
- Complete test data for development
- Easy switching between mock and real billing

## Usage Examples

### Creating an App (Level 1)
```python
# Uses platform_token_manager.py + platform_persistence_manager.py
manager = PlatformTokenManager(
    mozaiks_user_id="user_123",
    enterprise_id="app_456", 
    workflow_name="Generator"
)
await manager.initialize_platform_budget()
# ... existing workflow logic ...
await manager.finalize_platform_session()
```

### App End User Chat (Level 2)  
```python
# Uses token_manager.py + persistence_manager.py
manager = TokenManager(
    enterprise_id="app_456",
    platform_user_id="enduser_789",
    workflow_name="chat",
    mozaiks_user_id="user_123"  # For revenue sharing
)
await manager.initialize_budget()
# ... existing chat logic ...
await manager.finalize_session()
```

## Real-Time Analytics Integration

### Enhanced TokenManager Capabilities
Your existing TokenManager now includes comprehensive analytics:

```python
# Analytics-enhanced TokenManager
token_manager = TokenManager(
    chat_id="chat_123",
    enterprise_id="enterprise_456",
    user_id="user_789", 
    workflow_name="generator"
)

# Performance tracking methods
token_manager.track_agent_response_time("ConceptAgent", 1250.5)
token_manager.track_agent_message("ConceptAgent", "Response", "assistant")

# Session finalization with analytics
result = await token_manager.finalize_session()
# Returns performance comparison + workflow averages
```

### GroupChat Manager Integration
Real-time cost monitoring integrated into workflow execution:

```python
from core.workflow.groupchat_manager import (
    create_core_response_tracking_hooks,
    check_workflow_cost_thresholds
)

# Automatic performance tracking
hooks = create_core_response_tracking_hooks(
    tracker=AgentResponseTimeTracker(chat_id, enterprise_id),
    enterprise_id=enterprise_id,
    chat_id=chat_id,
    workflow_name=workflow_name, 
    token_tracker=token_manager
)

# Real-time cost analysis
cost_analysis = await check_workflow_cost_thresholds(
    workflow_name=workflow_name,
    enterprise_id=enterprise_id,
    current_cost=token_manager.session_usage.total_cost,
    current_tokens=token_manager.session_usage.total_tokens
)
```

### Analytics Database Collections

#### PerformanceMetrics Collection
```json
{
  "chat_id": "chat_123",
  "enterprise_id": "enterprise_456",
  "workflow_name": "generator", 
  "session_summary": {
    "total_tokens": 15420,
    "total_cost": 0.462,
    "session_duration_seconds": 342.5,
    "agents_used": ["ConceptAgent", "ArchitectAgent"]
  },
  "agent_performance": {
    "ConceptAgent": {
      "total_response_time_ms": 2340.5,
      "message_count": 3,
      "avg_response_time_ms": 780.17
    }
  },
  "timestamp": "2025-07-29T10:30:00Z"
}
```

#### WorkflowAverages Collection  
```json
{
  "workflow_name": "generator",
  "enterprise_id": "enterprise_456",
  "performance_averages": {
    "avg_session_duration_seconds": 298.7,
    "avg_cost_per_session": 0.387,
    "avg_tokens_per_session": 12890,
    "avg_agents_per_session": 2.3
  },
  "session_count": 47,
  "last_updated": "2025-07-29T10:30:00Z"
}
```

## Migration Path

1. ✅ **Existing functionality preserved** - No breaking changes
2. ✅ **Enhanced with billing levels** - Clean separation of concerns  
3. ✅ **Revenue sharing added** - Automatic MozaiksStream integration
4. ✅ **Mock data support** - Easy testing and development
5. ✅ **Real-time analytics added** - Chat-level aggregation and performance monitoring
6. ✅ **Cost intelligence integrated** - Live threshold monitoring and optimization

Your detailed token management logic now powers both levels of the billing system while providing comprehensive analytics and maintaining all the fine-grained tracking and control you built!
