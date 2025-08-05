# MozaiksAI Data & Monitoring Architecture

## 🏗️ **Component Roles & Responsibilities**

```
┌─────────────────────────────────────────────────────────────────┐
│                    MozaiksAI DATA ARCHITECTURE                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │ PERSISTENCE     │  │ PERFORMANCE     │  │ OPENLIT         │  │
│  │ MANAGER         │  │ MANAGER         │  │ OBSERVABILITY   │  │
│  │                 │  │                 │  │                 │  │
│  │ • Chat Sessions │  │ • Token Usage   │  │ • APM Tracing   │  │
│  │ • Message Store │  │ • Cost Tracking │  │ • Error Rates   │  │
│  │ • State Mgmt    │  │ • Agent Metrics │  │ • Response Time │  │
│  │ • DB Operations │  │ • Workflow KPIs │  │ • System Health │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
│           │                     │                     │          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │
│  │ MongoDB         │  │ Business        │  │ External APM    │  │
│  │ • chat_sessions │  │ Intelligence    │  │ • OpenTelemetry │  │
│  │ • enterprises   │  │ • Cost Reports  │  │ • Metrics Export│  │
│  │ • real_time_    │  │ • Usage Analytics│  │ • Trace Export  │  │
│  │   tracking      │  │ • Performance   │  │ • Dashboard     │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## 📊 **Data Flow & Integration**

### **Workflow Execution Flow**
```
1. User Request
   ↓
2. PersistenceManager.create_session()
   ↓
3. PerformanceManager.start_tracking()
   ↓
4. OpenLitObservability.start_trace()
   ↓
5. AG2 Workflow Execution
   ↓
6. PerformanceManager.update_from_agents() → PersistenceManager.update_real_time_tracking()
   ↓
7. OpenLitObservability.record_metrics()
   ↓
8. PersistenceManager.save_message() (for each message)
   ↓
9. PerformanceManager.finalize() → PersistenceManager.finalize_tracking()
   ↓
10. OpenLitObservability.end_trace()
```

## 🎯 **Key Distinctions**

### **PersistenceManager** (What Happened)
- **Purpose**: Store and retrieve data
- **Questions Answered**: 
  - What messages were sent?
  - What's the current session state?
  - What workflows are active?
- **Data Stored**: Messages, sessions, state, relationships

### **PerformanceManager** (How Much It Cost)
- **Purpose**: Track resource usage and business metrics  
- **Questions Answered**:
  - How many tokens were used?
  - What did this workflow cost?
  - Which agents are most expensive?
  - Are we staying within budget?
- **Data Tracked**: Tokens, costs, usage patterns, efficiency

### **OpenLitObservability** (How Well It Performed)
- **Purpose**: Monitor system performance and health
- **Questions Answered**:
  - How fast are responses?
  - Where are errors occurring?
  - Is the system healthy?
  - What's the user experience like?
- **Data Monitored**: Response times, error rates, system metrics, traces

## 🔄 **Integration Points**

### **PerformanceManager ↔ PersistenceManager**  
- PerformanceManager uses PersistenceManager to store business metrics
- Shared: `real_time_tracking` collection in MongoDB
- Data Flow: Performance metrics stored via persistence layer

### **OpenLitObservability ↔ Both**
- Wraps both with observability instrumentation  
- Monitors performance of persistence operations
- Tracks business metric calculation performance
- Exports to external APM systems

### **All Three Together**
- **PersistenceManager**: Stores the conversation
- **PerformanceManager**: Calculates what it cost
- **OpenLitObservability**: Measures how well it performed

## 💡 **Why Three Separate Systems?**

1. **Separation of Concerns**: Each handles a distinct aspect
2. **Scalability**: Can optimize each independently  
3. **Flexibility**: Can swap implementations without affecting others
4. **Monitoring**: Different stakeholders need different views
   - **Developers**: OpenLit metrics (performance, errors)
   - **Business**: Performance metrics (costs, usage)
   - **Users**: Persistence data (conversations, history)

## 🚀 **Current Status**
- ✅ **PersistenceManager**: Mature, handles all data operations
- ✅ **PerformanceManager**: Optimized, integrated with persistence layer
- ✅ **OpenLitObservability**: Basic implementation, can be enhanced

This architecture provides complete visibility into your AI platform from data, business, and technical perspectives.
