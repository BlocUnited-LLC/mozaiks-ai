# MozaiksAI Events System Architecture Overview

> **🔧 Implementation Details**: For technical documentation, code examples, and API reference, see [Transport System Documentation](./TRANSPORT_SYSTEM.md)

## Executive Summary

The MozaiksAI events system is a unified, transport-agnostic communication framework designed to enable real-time, bidirectional communication between AI workflows and frontend interfaces. The system abstracts away the complexity of different transport mechanisms (SSE, WebSocket) while maintaining compatibility with the AG2 (AutoGen) framework and providing a simplified event model for developers.

## Core Design Principles

### 1. **Transport Agnosticism**
The system allows workflows to operate identically regardless of whether they're using Server-Sent Events (SSE) or WebSocket transport. This is achieved through a unified `SimpleCommunicationChannel` protocol that abstracts the underlying transport mechanism.

### 2. **Simplified Event Model**
Instead of complex event hierarchies, the system uses just six core event types that cover all essential communication patterns:
- Chat messages
- Content routing to artifacts
- Content routing to chat panels
- UI tool interactions
- Status updates
- Error handling

### 3. **AG2 Framework Integration**
The system maintains full compatibility with AutoGen's IOStream and GroupChat systems while adding modern real-time capabilities for web interfaces.

### 4. **Modular Architecture**
Clear separation of concerns allows individual components to be modified or extended without affecting the entire system.

## System Architecture Overview

### High-Level Data Flow

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐    ┌──────────────────┐
│   AI Workflows  │────│ Communication    │────│  Transport      │────│   Frontend       │
│   (Backend)     │    │  Channel         │    │  Layer          │    │   Interface      │
│                 │    │  (Protocol)      │    │  (SSE/WS)       │    │   (React)        │
└─────────────────┘    └──────────────────┘    └─────────────────┘    └──────────────────┘
```

## Detailed Component Architecture

### 1. Events Core Layer

#### **SimpleEvent Structure**
The fundamental unit of communication in the system. Every event contains:
- **Type**: One of six predefined event types
- **Data**: Flexible payload containing the event's information
- **Timestamp**: Automatically generated for chronological ordering
- **Agent Name**: Optional identifier for multi-agent scenarios

#### **Event Type Categories**
- **CHAT_MESSAGE**: Standard conversational exchanges between users and AI agents
- **ROUTE_TO_ARTIFACT**: Directs content to artifact components (e.g., code editors, document viewers)
- **ROUTE_TO_CHAT**: Routes content to inline UI components (e.g., text prompts, simple input forms)
- **UI_TOOL_ACTION**: Handles interactive UI element events and responses
- **STATUS**: System status updates, connection states, and progress indicators
- **ERROR**: Error conditions, validation failures, and exception handling

#### **SimpleCommunicationChannel Protocol**
A protocol-based interface that defines the contract all transport implementations must follow. This ensures that workflows can send events without knowing whether they're using SSE, WebSocket, or any future transport mechanism.

Key protocol methods:
- `send_event()`: Primary event transmission method
- `send_custom_event()`: Extensibility for custom event types
- `send_ui_component_route()`: Specialized UI routing
- `send_ui_tool()`: UI tool interaction handling

### 2. Transport Management Layer

#### **SimpleTransport (Unified Architecture)**
The consolidated transport system that replaces multiple complex managers:
- **Single-file architecture**: All transport functionality in `simple_transport.py`
- **Protocol compatibility**: Implements `SimpleCommunicationChannel` interface
- **Built-in filtering**: Automatic AutoGen noise removal
- **AG2 resume**: Native groupchat persistence and recovery
- **Dynamic UI support**: Production-ready component routing
- **Transport agnostic**: Works with SSE, WebSocket, and future protocols

#### **Simplified Transport Selection**
The system uses intelligent defaults with minimal configuration:
- **Protocol detection**: Automatic SSE vs WebSocket selection
- **Configuration-driven**: Single config object for all transport settings
- **Smart defaults**: Sensible defaults for production deployment
- **Minimal setup**: No complex configuration required

### 3. SSE (Server-Sent Events) Implementation

#### **SSEConnection Class**
Manages individual SSE connections with features including:
- **Asynchronous event queue** for non-blocking event delivery
- **Auto-start capability** for workflows that don't require initial user input
- **Connection state management** with automatic reconnection
- **Streaming text support** for real-time content delivery
- **Heartbeat mechanism** to maintain connection health

#### **Use Cases for SSE**
- **One-way communication** from server to client
- **Streaming content** like real-time text generation
- **Status updates** and progress notifications
- **Workflows with minimal user interaction**
- **Mobile-friendly** connections with lower overhead

### 4. WebSocket Implementation

#### **AG2WebSocketConnection Class**
Provides full-duplex communication with advanced features:
- **Native AG2 IOWebsockets integration** for seamless AutoGen compatibility
- **Conversation pause/resume** capabilities for complex multi-turn dialogs
- **Message queuing** to handle temporary connection interruptions
- **Real-time bidirectional** communication for interactive workflows
- **State persistence** across connection interruptions

#### **Use Cases for WebSocket**
- **Interactive workflows** requiring frequent user input
- **Real-time collaboration** features
- **Complex multi-agent** conversations with branching logic
- **Low-latency applications** requiring immediate responses
- **Stateful conversations** that need to maintain context

### 5. Frontend Integration

#### **Transport Abstraction Layer**
The frontend implements a sophisticated abstraction system that:
- **Automatically detects** the appropriate transport for each workflow
- **Provides consistent APIs** regardless of underlying transport
- **Handles reconnection logic** and error recovery
- **Manages event processing** through the SimpleBridge system
- **Maintains backward compatibility** with existing components

#### **SimpleBridge System**
Acts as an intelligent message router that:
- **Processes incoming events** from any transport mechanism
- **Converts legacy event formats** for backward compatibility
- **Routes events to appropriate UI components**
- **Handles event validation** and error recovery
- **Provides debugging** and monitoring capabilities

#### **Event Processing Pipeline**
1. **Transport Reception**: Raw events received from backend
2. **Bridge Processing**: Events validated and converted to standard format
3. **Component Routing**: Events directed to appropriate UI components
4. **State Management**: UI state updated based on event content
5. **User Feedback**: Visual updates reflected in the interface

### 6. Workflow Integration

#### **Transport-Agnostic Workflow Design**
Workflows receive a `communication_channel` parameter that provides:
- **Consistent interface** regardless of transport type
- **Event sending capabilities** through standardized methods
- **Real-time streaming** support for progressive content delivery
- **UI routing decisions** for directing content to appropriate panels
- **Error handling** and status reporting capabilities

#### **Workflow Communication Patterns**

**Streaming Text Pattern**:
- Workflows can send progressive text updates
- Frontend receives and displays content in real-time
- Supports both word-by-word and chunk-based streaming

**Artifact Creation Pattern**:
- Workflows generate complex content (documents, code, visualizations)
- Content automatically routed to dedicated artifact panels
- Supports categorization and metadata attachment

**Interactive Tool Pattern**:
- Workflows can present UI tools for user interaction
- User actions sent back to workflows for processing
- Supports complex form interactions and data collection

## Key System Benefits

### 1. **Developer Experience**
- **Simplified APIs**: Developers work with six event types instead of complex hierarchies
- **Transport Transparency**: Workflows work identically across all transport mechanisms
- **Consistent Patterns**: Same development patterns apply to all communication scenarios
- **Rich Debugging**: Comprehensive logging and monitoring across all layers

### 2. **Scalability**
- **Modular Design**: Components can be modified independently
- **Transport Flexibility**: Easy to add new transport mechanisms
- **Event Extensibility**: Custom event types can be added without system changes
- **Performance Optimization**: Each transport optimized for its use cases

### 3. **Reliability**
- **Connection Recovery**: Automatic reconnection and message queuing
- **Error Handling**: Comprehensive error recovery at all levels
- **State Management**: Conversation state preserved across interruptions
- **Graceful Degradation**: System continues operating with reduced functionality

### 4. **User Experience**
- **Real-time Feedback**: Immediate visual feedback for all user actions
- **Seamless Interactions**: No visible difference between transport mechanisms
- **Responsive Design**: Optimized for both desktop and mobile experiences
- **Rich Content**: Support for text, artifacts, and interactive elements

## Monitoring and Observability

### **Event Tracking**
- Every event transmission logged with timestamps and metadata
- Performance metrics collected for optimization
- Error rates monitored across all transport mechanisms
- User interaction patterns analyzed for UX improvements

### **System Health**
- Connection state monitoring across all active sessions
- Transport performance metrics and optimization opportunities
- Workflow execution times and resource utilization
- Frontend rendering performance and user engagement metrics

## Future Extensibility

### **Transport Mechanisms**
The architecture is designed to easily accommodate:
- **HTTP/2 Server Push** for enhanced web performance
- **gRPC streaming** for high-performance applications
- **Message queues** for asynchronous processing
- **Custom protocols** for specialized use cases

### **Event Types**
The system can be extended with additional event types for:
- **Voice/audio communication** for speech-enabled interfaces
- **Video streaming** for visual AI interactions
- **File transfer** for document processing workflows
- **Collaborative editing** for multi-user document creation

### **Integration Capabilities**
Future integrations can include:
- **Third-party services** through standardized event adapters
- **External AI frameworks** beyond AG2/AutoGen
- **Enterprise systems** through custom transport implementations
- **IoT devices** for physical world interactions

## Conclusion

The MozaiksAI events system represents a sophisticated yet approachable solution for real-time AI-human interaction. By abstracting transport complexity while maintaining flexibility and performance, the system enables developers to focus on creating compelling AI experiences rather than managing communication infrastructure. The architecture's modular design ensures that the system can evolve with changing requirements while maintaining backward compatibility and developer productivity.
