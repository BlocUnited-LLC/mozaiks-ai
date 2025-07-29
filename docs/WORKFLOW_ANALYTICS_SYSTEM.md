# Workflow Analytics System

## Overview

The Mozaiks platform includes a comprehensive **real-time analytics system** that provides chat-level aggregation, performance monitoring, and cost analysis across all workflow uses. This system was built to answer the question: *"Is there any way we can create some sort of averages for agent/groupchat outputs across all the uses of a workflow?"*

## Key Features

### 🔄 **Real-Time Analytics**
- **Chat-level aggregation** across all workflow sessions
- **Live cost monitoring** during conversations  
- **Performance tracking** for individual agents
- **Session comparison** against workflow averages

### 📊 **Performance Metrics**
- **Agent response times** with millisecond precision
- **Token usage patterns** by agent and conversation
- **Cost analysis** with threshold monitoring
- **Session duration tracking** for optimization insights

### 💰 **Cost Intelligence**
- **Real-time cost thresholds** with automated alerts
- **Budget-aware workflows** that adapt to spending limits
- **Historical cost trends** for business insights
- **Trial token management** with usage forecasting

## Architecture

### Core Components

```
┌─────────────────┐    Real-time     ┌──────────────────┐
│   TokenManager  │◄─────────────────│  GroupChat       │
│   (Analytics)   │   Integration    │  Manager         │
└─────────────────┘                  └──────────────────┘
        │                                      │
        │ Persists Data                        │ Performance Hooks
        ▼                                      ▼
┌─────────────────┐    Aggregates    ┌──────────────────┐
│ PersistenceManager│◄─────────────────│ AgentResponseTime│
│  (Chat-level)   │    Analytics     │    Tracker      │
└─────────────────┘                  └──────────────────┘
```

### Database Collections

#### **PerformanceMetrics Collection**
```json
{
  "_id": ObjectId,
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

#### **WorkflowAverages Collection**
```json
{
  "_id": ObjectId,
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

## Implementation

### TokenManager Analytics Integration

The `TokenManager` class provides comprehensive session tracking:

```python
# Initialize with analytics
token_manager = TokenManager(
    chat_id="chat_123",
    enterprise_id="enterprise_456", 
    user_id="user_789",
    workflow_name="generator"
)

# Track agent performance
token_manager.track_agent_response_time("ConceptAgent", 1250.5)
token_manager.track_agent_message("ConceptAgent", "Generated concept", "assistant")

# Finalize with analytics persistence
result = await token_manager.finalize_session()
# Returns session summary + workflow comparison
```

### Real-Time Cost Monitoring

Integrated into the GroupChat Manager for live monitoring:

```python
from core.workflow.groupchat_manager import check_workflow_cost_thresholds

cost_analysis = await check_workflow_cost_thresholds(
    workflow_name="generator",
    enterprise_id="enterprise_456",
    current_cost=0.462,
    current_tokens=15420
)

# Returns:
# {
#   "status": "within_limits|approaching_limit|exceeded_limit",
#   "recommendations": [...],
#   "threshold_analysis": {...}
# }
```

### GroupChat Integration Hooks

Automatic performance tracking through AG2 integration:

```python
from core.workflow.groupchat_manager import create_core_response_tracking_hooks

# Create tracking hooks for AG2
hooks = create_core_response_tracking_hooks(
    tracker=AgentResponseTimeTracker(chat_id, enterprise_id),
    enterprise_id=enterprise_id,
    chat_id=chat_id, 
    workflow_name=workflow_name,
    token_tracker=token_manager
)

before_reply_hook, before_send_hook = hooks
# These hooks automatically track all agent interactions
```

## Analytics Capabilities

### 1. **Session-Level Analytics**
- Individual chat performance metrics
- Agent response time analysis
- Token usage breakdown by agent
- Cost tracking with precision

### 2. **Workflow-Level Aggregation** 
- Cross-session performance averages
- Historical trend analysis
- Workflow optimization insights
- Comparative performance metrics

### 3. **Enterprise-Level Insights**
- Multi-workflow performance comparison
- Resource utilization patterns
- Cost optimization opportunities
- Usage forecasting for business planning

### 4. **Real-Time Monitoring**
- Live cost threshold checking
- Performance anomaly detection
- Resource usage alerts
- Session optimization recommendations

## Cost Monitoring Features

### Threshold Management
```python
# Configurable cost thresholds
COST_THRESHOLDS = {
    "warning_percentage": 75,    # Warn at 75% of expected cost
    "critical_percentage": 90,   # Alert at 90% of expected cost  
    "max_cost_multiplier": 1.5   # Hard stop at 150% of expected
}
```

### Real-Time Analysis
- **Live cost tracking** during workflow execution
- **Predictive analysis** based on current usage patterns
- **Automatic recommendations** for cost optimization
- **Historical comparison** against similar sessions

## Performance Insights

### Agent Performance Metrics
- **Response time analysis** with statistical breakdown
- **Message efficiency** tracking (tokens per message)
- **Collaboration patterns** between agents
- **Performance trending** over time

### Workflow Optimization
- **Bottleneck identification** in agent interactions
- **Resource utilization** analysis per workflow step
- **Performance correlation** with conversation outcomes
- **Optimization recommendations** based on data

## Usage Examples

### Basic Analytics Integration
```python
# Start session with analytics
async def run_workflow_with_analytics():
    token_manager = TokenManager(
        chat_id=generate_chat_id(),
        enterprise_id="my_enterprise",
        workflow_name="my_workflow"
    )
    
    # Initialize with trial token management
    await token_manager.initialize_async()
    
    # Your workflow logic here...
    # (Analytics automatically tracked via hooks)
    
    # Finalize with performance comparison
    result = await token_manager.finalize_session()
    
    return {
        "session_completed": result["session_finalized"],
        "performance_vs_average": result["performance_comparison"],
        "cost_analysis": result.get("cost_analysis", {})
    }
```

### Advanced Cost Monitoring
```python
# Real-time cost monitoring during workflow
async def monitored_workflow_execution():
    # Set up cost monitoring
    cost_monitor = WorkflowCostMonitor(
        workflow_name="generator",
        enterprise_id="my_enterprise",
        warning_threshold=0.50,  # $0.50 warning
        critical_threshold=0.75  # $0.75 critical
    )
    
    # Execute with monitoring
    async for step in workflow_steps:
        await execute_step(step)
        
        # Check cost status
        status = await cost_monitor.check_current_status()
        
        if status["should_pause"]:
            await handle_cost_threshold_reached(status)
            break
            
    return await finalize_with_analytics()
```

## Testing & Validation

### Integration Testing
The system includes comprehensive integration tests:

```bash
# Run the complete analytics system test
python test_integrated_analytics.py
```

### Test Coverage
- ✅ TokenManager initialization and async setup
- ✅ Token deduction with trial management  
- ✅ Performance tracking for multiple agents
- ✅ Session finalization with persistence
- ✅ Workflow averages calculation
- ✅ Real-time cost monitoring
- ✅ GroupChat manager integration
- ✅ End-to-end analytics pipeline

## Business Value

### For Platform Operators
- **Cost optimization** through usage pattern analysis
- **Performance monitoring** across all deployed workflows
- **Resource planning** based on usage forecasting
- **Quality assurance** through performance trending

### For App Creators
- **Workflow optimization** based on real usage data
- **Cost transparency** with detailed breakdown
- **Performance insights** for improving user experience
- **Usage analytics** for business intelligence

### For End Users
- **Transparent costs** with real-time tracking
- **Optimized performance** through continuous monitoring
- **Predictable pricing** based on usage patterns
- **Quality assurance** through performance tracking

## Future Enhancements

### Planned Features
- **Machine learning insights** for performance prediction
- **Advanced dashboard** with interactive analytics
- **Custom alert systems** for enterprise users
- **Performance optimization** recommendations using AI

### Scalability Considerations
- **Distributed analytics** for high-volume deployments
- **Real-time streaming** analytics for immediate insights
- **Data archival** strategies for long-term analysis
- **Multi-tenant** analytics with data isolation

---

## Getting Started

1. **Initialize Analytics**: Include TokenManager in your workflow setup
2. **Configure Monitoring**: Set cost thresholds appropriate for your use case
3. **Integrate Hooks**: Use GroupChat manager integration for automatic tracking
4. **Monitor Results**: Review analytics through session finalization data
5. **Optimize Performance**: Use insights to improve workflow efficiency

The analytics system is production-ready and automatically integrates with existing workflow logic, providing immediate visibility into performance and costs without requiring changes to existing code.
