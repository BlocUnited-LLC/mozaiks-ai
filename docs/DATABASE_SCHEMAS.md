# MozaiksAI Database Schemas

This document outlines all the database schemas and data structures being stored in MongoDB by the MozaiksAI system.

## Collections Overview

The system uses two main databases:
- **Database 1**: `autogen_ai_agents_db1` (Workflows and AgentCapabilities)
- **Database 2**: `autogen_ai_agents` (Concepts, Enterprises, UsageTracking)

### Collections:
1. **Workflows** (Primary collection for chat sessions)
2. **UsageTracking** (Token usage tracking)
3. **Enterprises** (Enterprise information)
4. **Concepts** (Concept creation data)
5. **AgentCapabilities** (Agent capability definitions)

---

## 1. Workflows Collection Schema

### Actual Workflow Document Structure (VE-Style)

```javascript
{
  "_id": ObjectId("..."),
  "chat_id": "unique_chat_session_id",
  "enterprise_id": ObjectId("..."),
  "concept_id": ObjectId("..."),
  "workflow_type": "generator|analyzer|concept_creation|ag2",
  "user_id": "string_user_id",
  "created_at": ISODate("..."),
  "last_updated": ISODate("..."),
  "connection_state": "active|disconnected|reconnected",
  "is_complete": false,
  
  // Dynamic workflow-specific state (chat metadata)
  "VerificationChatState": {
    "SessionID": "e57b84bc-e277-4765-b074-6cfcca261bc5",
    "AgentHistory": [...], // Array of conversation messages
    "IterationCount": 0,
    "VerificationAgentCount": 0,
    "UserFeedbackCount": 0,
    "LastSpeaker": "verification_agent",
    "SessionTotals": {
      "session_id": {
        "PromptTokens": 9527,
        "CompletionTokens": 2646,
        "TotalTokens": 12173,
        "TotalCost": 0.022122100000000006
      }
    }
  },
  
  "CreationChatState": {
    "SessionID": "54e5e1af-f47b-4778-a8d2-fb93e7f01834",
    "AgentHistory": [...], // Array of conversation messages
    "IterationCount": 0,
    "overview_agent_count": 1,
    "UserFeedbackCount": 0,
    "LastSpeaker": "Personnel_Agent",
    "SessionTotals": {
      "session_id": {
        "PromptTokens": 14002,
        "CompletionTokens": 6309,
        "TotalTokens": 20311,
        "TotalCost": 0.0
      }
    }
  },
  
  // Dynamic workflow-specific conversations (stored separately)
  "ConceptVerificationConvo": [
    {
      "timestamp": "2025-02-22T18:03:52.678591",
      "sender": "user_proxy",
      "content": "message content",
      "role": "user",
      "name": "user_proxy"
    }
  ],
  
  "ConceptCreationConvo": [
    {
      "timestamp": "2025-02-22T18:07:18.535260",
      "sender": "user_proxy", 
      "content": "message content",
      "role": "user",
      "name": "user_proxy"
    }
  ],
  
  // Dynamic workflow-specific status (Resume Logic)
  "VerificationChatStatus": 1,  // 0 = in progress, 1 = completed
  "CreationChatStatus": 0,      // 0 = in progress, 1 = completed
  
  // Connection tracking
  "connection_info": {
    "transport_type": "websocket",
    "conversation_duration_ms": 45000,
    "max_turns_used": 10
  },
  "disconnected_at": ISODate("..."),
  "reconnected_at": ISODate("...")
}
```

---

## 2. UsageTracking Collection Schema

```javascript
{
  "_id": ObjectId("..."),
  "chat_id": "unique_chat_session_id",
  "enterprise_id": ObjectId("..."),
  "session_id": "session_identifier",
  "total_tokens": 2300,
  "prompt_tokens": 1500,
  "completion_tokens": 800,
  "total_cost": 0.0345,
  "turn_number": 7,
  "timestamp": ISODate("..."),
  
  // Additional context (kwargs)
  "model_used": "gpt-4o-mini",
  "agent_name": "APIKeyAgent",
  "workflow_type": "generator"
}
```

---

## 3. Enterprises Collection Schema

```javascript
{
  "_id": ObjectId("..."),
  "name": "Enterprise Name",
  "AvailableTokens": 10000,
  "created_at": ISODate("..."),
  "updated_at": ISODate("..."),
  // Additional enterprise fields...
}
```

---

## 4. Concepts Collection Schema

```javascript
{
  "_id": ObjectId("..."),
  "enterprise_id": ObjectId("..."),
  "ConceptCode": "CONCEPT_001",
  "created_at": ISODate("..."),
  // Additional concept fields...
}
```

---

## 5. AgentCapabilities Collection Schema

```javascript
{
  "_id": ObjectId("..."),
  "capability_name": "budget_tracking",
  "version": "1.0.0",
  "config": {},
  "created_at": ISODate("...")
}
```

---

## Schema Update Patterns

### 1. Workflow Creation (VE-Style)

```javascript
// Create workflow document
{
  "chat_id": "chat_identifier",
  "enterprise_id": ObjectId("..."),
  "concept_id": ObjectId("..."),
  "workflow_type": "concept_creation",
  "user_id": "user_id",
  "created_at": ISODate("..."),
  "last_updated": ISODate("..."),
  "concept_creation_state": {...},
  "concept_creation_conversation": [],
  "concept_creation_status": 0,
  "connection_state": "active",
  "is_complete": false
}
```

### 2. Token Usage Tracking (Separate Collection)

```javascript
// UsageTracking collection entry
{
  "chat_id": "chat_identifier",
  "enterprise_id": ObjectId("..."),
  "session_id": "session_identifier",
  "prompt_tokens": 1500,
  "completion_tokens": 800,
  "total_tokens": 2300,
  "total_cost": 0.0345,
  "timestamp": ISODate("...")
}

// Enterprise balance update
{
  "$inc": {
    "tokenBalance": -0.0345
  }
}
```

### 3. Connection State Updates

```javascript
// Simple connection tracking
{
  "$set": {
    "connection_state": "reconnected",
    "reconnected_at": ISODate("..."),
    "last_updated": ISODate("...")
  }
}
```

### 4. Resume Logic (Chat Status Pattern)

```javascript
// Check if can resume (status 0 = in progress, 1 = completed)
{
  "chat_id": "chat_identifier",
  "enterprise_id": ObjectId("..."),
  "VerificationChatStatus": 1,    // 1 = completed, can start next workflow
  "CreationChatStatus": 0,        // 0 = in progress, can resume
  "is_complete": false
}
```

---

## Key Data Flow Patterns (Actual Implementation)

1. **Chat Initialization**: Creates workflow document with simple VE-style structure
2. **Chat Metadata (ChatState)**: Stores session information, agent history, token usage per session
3. **Chat Status**: Uses 0 = in progress, 1 = completed for resume logic
4. **Token Tracking**: Session-based token totals within chat state plus separate UsageTracking collection
5. **Multi-Workflow Support**: Single document can contain multiple workflow states (VerificationChatState, CreationChatState)

---

## Critical Schema Notes (Current Reality)

1. **Multi-Workflow Documents**: Single document contains multiple workflow states and conversations
2. **Chat Status Values**: 0 = in progress (can resume), 1 = completed workflow
3. **Chat State Structure**: Contains SessionID, AgentHistory, IterationCount, LastSpeaker, SessionTotals
4. **Session Token Tracking**: Token usage tracked per session within ChatState.SessionTotals
5. **Resume Logic**: System checks status values to determine if new chat or resume existing

---

## Actual Update Patterns

### 1. Workflow Creation

```javascript
// Initial document creation
{
  "chat_id": "chat_123",
  "enterprise_id": ObjectId("..."),
  "concept_id": ObjectId("..."),
  "workflow_type": "concept_creation",
  "user_id": "user_456",
  "created_at": ISODate("..."),
  "last_updated": ISODate("..."),
  "VerificationChatState": {
    "SessionID": "e57b84bc-e277-4765-b074-6cfcca261bc5",
    "AgentHistory": [...],
    "IterationCount": 0,
    "VerificationAgentCount": 0,
    "UserFeedbackCount": 0,
    "LastSpeaker": "verification_agent",
    "SessionTotals": {
      "session_e57b84bc-e277-4765-b074-6cfcca261bc5": {
        "PromptTokens": 9527,
        "CompletionTokens": 2646,
        "TotalTokens": 12173,
        "TotalCost": 0.022122100000000006
      }
    }
  },
  "ConceptVerificationConvo": [...],
  "VerificationChatStatus": 1,
  "CreationChatState": {
    "SessionID": "54e5e1af-f47b-4778-a8d2-fb93e7f01834",
    "AgentHistory": [...],
    "IterationCount": 0,
    "overview_agent_count": 1,
    "UserFeedbackCount": 0,
    "LastSpeaker": "Personnel_Agent",
    "SessionTotals": {
      "session_54e5e1af-f47b-4778-a8d2-fb93e7f01834": {
        "PromptTokens": 14002,
        "CompletionTokens": 6309,
        "TotalTokens": 20311,
        "TotalCost": 0.0
      }
    }
  },
  "ConceptCreationConvo": [...],
  "CreationChatStatus": 0,
  "connection_state": "active",
  "is_complete": false
}
```

### 2. Message Updates

```javascript
// Add new message to conversation
{
  "$push": {
    "ConceptCreationConvo": {
      "timestamp": "2025-02-22T18:07:18.535260",
      "sender": "user_proxy",
      "content": "message content",
      "role": "user",
      "name": "user_proxy"
    }
  },
  "$set": {
    "last_updated": ISODate("...")
  }
}
```

### 3. Status Updates

```javascript
// Update workflow status (Resume Logic)
{
  "$set": {
    "CreationChatStatus": 1,  // Mark as complete
    "last_updated": ISODate("...")
  }
}
```

### 4. Chat State Updates

```javascript
// Update chat state metadata
{
  "$set": {
    "CreationChatState": {
      "SessionID": "54e5e1af-f47b-4778-a8d2-fb93e7f01834",
      "AgentHistory": [...],
      "IterationCount": 1,
      "overview_agent_count": 1,
      "UserFeedbackCount": 1,
      "LastSpeaker": "Personnel_Agent",
      "SessionTotals": {
        "session_54e5e1af-f47b-4778-a8d2-fb93e7f01834": {
          "PromptTokens": 14002,
          "CompletionTokens": 6309,
          "TotalTokens": 20311,
          "TotalCost": 0.0
        }
      }
    },
    "last_updated": ISODate("...")
  }
}

---

## Schema Validation Requirements (Actual)

- `enterprise_id`: Must be valid ObjectId or 24-character string
- `chat_id`: Must be unique string identifier
- `{workflow_type}_conversation`: Array of message objects with sender, content, timestamp, role, name
- `{workflow_type}_status`: Integer (0 = in progress, 1 = completed) - used for resume logic
- `{workflow_type}_state`: Chat metadata object with SessionID, AgentHistory, IterationCount, LastSpeaker, SessionTotals
- Connection states: "active", "disconnected", "reconnected"
