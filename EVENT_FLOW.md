# MozaiksAI Event Flow

The event-driven architecture of MozaiksAI ensures a clean, decoupled, and real-time system. This document details the journey of an event from its creation within the AutoGen (AG2) engine to its final destinations in the database and the user's browser.

## The Event Lifecycle

The entire system is orchestrated by the flow of events. Here is a step-by-step breakdown of the process:

```mermaid
sequenceDiagram
    participant User
    participant ChatUI
    participant API_Server as FastAPI Server
    participant Orchestrator
    participant AG2_Engine as AutoGen Engine
    participant Event_Processor as UIEventProcessor
    participant Persistence_Manager as AG2PersistenceManager
    participant Transport as SimpleTransport
    participant MongoDB

    User->>ChatUI: Sends message
    ChatUI->>API_Server: POST /initiate_chat
    API_Server->>Orchestrator: run_workflow_orchestration()
    Orchestrator->>AG2_Engine: a_run_group_chat()
    
    activate AG2_Engine
    AG2_Engine-->>Orchestrator: Returns Response object
    deactivate AG2_Engine
    
    Orchestrator->>Event_Processor: response.process(processor=self)
    
    loop For each event in Response
        Event_Processor->>Event_Processor: process_event(event)
        
        subgraph Real-Time Persistence
            Event_Processor->>Persistence_Manager: save_event(event)
            Persistence_Manager->>MongoDB: Update/Insert Document
            MongoDB-->>Persistence_Manager: Success
            Persistence_Manager-->>Event_Processor: Done
        end
        
        subgraph UI Update
            Event_Processor->>Transport: send_event_to_ui(event)
            Transport->>ChatUI: WebSocket push
        end
    end
```

### Step-by-Step Explanation

1.  **User Action**: The process begins when a user sends a message through the **React Chat UI**.

2.  **API Request**: The UI sends a POST request to the **FastAPI Server**, which triggers the `run_workflow_orchestration` function in the **Orchestrator**.

3.  **AG2 Execution**: The **Orchestrator** sets up the agents and tools, then calls `a_run_group_chat()` on the **AutoGen (AG2) Engine**. The engine runs the multi-agent conversation. Crucially, it *does not* return messages directly. Instead, it returns a `Response` object which contains an async generator of events.

4.  **Event Processing**: The **Orchestrator** immediately passes this `Response` object to the `UIEventProcessor` by calling `response.process()`.

5.  **The Event Loop**: The `UIEventProcessor` now takes control and iterates through every event produced by the AG2 `Response` object. For each event, it performs two actions in parallel:

    a.  **Persistence**: It calls `save_event()` on the **AG2PersistenceManager**.
        -   The `AG2PersistenceManager` inspects the event type.
        -   If it's a `TextEvent`, it appends the message to the `messages` array in the corresponding chat session document in **MongoDB**.
        -   If it's a `UsageSummaryEvent`, it increments the token and cost counters in the same document.
        -   Other events can be handled as needed, providing a single point for all database writes.

    b.  **UI Forwarding**: It calls `send_event_to_ui()` on the **SimpleTransport**.
        -   The `SimpleTransport` finds the active WebSocket connection for the `chat_id`.
        -   It serializes the event and pushes it directly to the **ChatUI**.
        -   The UI receives the event and updates the display accordingly (e.g., rendering a new message, updating a token counter).

## Key Benefits of this Flow

-   **Real-Time**: There is no waiting for the entire workflow to finish. Messages and metrics are persisted and displayed the moment they are generated.
-   **Single Source of Truth**: The AG2 `Event Stream` is the single source of truth for everything that happens in a workflow. All other components are subscribers to this stream.
-   **Resilience**: Because every event is saved as it happens, the system can recover from a crash. The `resume_chat()` function can reconstruct the exact state of the conversation from the persisted events.
-   **Scalability**: The components are decoupled. You can have multiple `UIEventProcessor` instances handling different chats, and the `SimpleTransport` can manage thousands of concurrent WebSocket connections. The database becomes the central, scalable store of record.
-   **Extensibility**: To add new functionality, you simply need to handle a new event type. For example, to add real-time logging to a separate system, you could add another call within the `UIEventProcessor`'s loop to send events to a logging service, without changing any other part of the application.
