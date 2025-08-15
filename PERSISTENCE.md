# MozaiksAI Persistence Layer

The persistence layer in MozaiksAI is designed to be robust, real-time, and simple. It is built around the `AG2PersistenceManager` and uses MongoDB as the data store. Its primary responsibility is to save the state of every workflow as it happens, enabling features like chat resumption and live performance tracking.

## Core Component: `AG2PersistenceManager`

This class is the sole interface to the database for all workflow-related data. It does **not** contain complex business logic. Instead, it provides simple, event-driven methods:

-   `save_event(event, ...)`: This is the workhorse method. It receives an event from the `UIEventProcessor`, identifies its type, and performs the corresponding database operation.
-   `resume_chat(chat_id, ...)`: This method is called by the `Orchestrator` at the beginning of a session. It queries the database for a given `chat_id` and returns the message history, allowing the conversation to be resumed.

## Database Schema: The Session Document

We use a single, comprehensive document in the `chat_sessions` collection to store all data related to a single chat session. This denormalized approach is highly efficient for our use case, as it allows us to retrieve all information for a chat in a single database query.

Here is a sample structure of a session document:

```json
{
  "_id": "ObjectId('64a5e7d6f8e1d2c3b4a5e6f7')",
  "chat_id": "chat_abc123",
  "enterprise_id": "ent_xyz789",
  "user_id": "user_456",
  "workflow_name": "Generator",
  "created_at": "ISODate('2025-08-07T10:00:00Z')",
  "updated_at": "ISODate('2025-08-07T10:05:00Z')",
  "status": 1, // 0 = running, 1 = completed, -1 = failed
  "real_time_tracking": {
    "tokens": {
      "total_tokens": 1250,
      "prompt_tokens": 800,
      "completion_tokens": 450,
      "total_cost": 0.0025
    }
  },
  "messages": [
    {
      "sender": "user",
      "content": "Please generate a summary of the latest AI trends.",
      "role": "user",
      "timestamp": "ISODate('2025-08-07T10:00:05Z')",
      "event_type": "TextEvent",
      "event_id": "uuid_1"
    },
    {
      "sender": "ResearchAgent",
      "content": "Searching for the latest AI trends...",
      "role": "assistant",
      "timestamp": "ISODate('2025-08-07T10:01:10Z')",
      "event_type": "TextEvent",
      "event_id": "uuid_2"
    },
    {
      "sender": "WriterAgent",
      "content": "Here is the summary you requested...",
      "role": "assistant",
      "timestamp": "ISODate('2025-08-07T10:04:50Z')",
      "event_type": "TextEvent",
      "event_id": "uuid_3"
    }
  ]
}
```

### Field Descriptions

-   `chat_id`: The unique identifier for the chat session.
-   `enterprise_id`, `user_id`: Identifiers for multi-tenancy and user tracking.
-   `workflow_name`: The name of the workflow being executed (e.g., "Generator", "Chat").
-   `status`: The current status of the workflow.
-   `real_time_tracking`: An object containing live performance metrics.
    -   `tokens`: This sub-document is incremented in real-time by `UsageSummaryEvent`s.
-   `messages`: An array containing every message exchanged during the conversation.
    -   Each message is a self-contained object with the sender, content, role, and timestamp.
    -   We also store the `event_type` and `event_id` for complete traceability back to the source AG2 event.

## How Real-Time Persistence Works

1.  **`TextEvent`**: When `AG2PersistenceManager` receives a `TextEvent`, it performs a MongoDB `$push` operation to add a new message object to the `messages` array of the session document.
2.  **`UsageSummaryEvent`**: When it receives a `UsageSummaryEvent`, it performs a MongoDB `$inc` (increment) operation on the fields within the `real_time_tracking.tokens` object.

This event-driven, incremental update approach is extremely efficient and ensures that our data is always up-to-date without requiring expensive "read-modify-write" operations on the entire document.
