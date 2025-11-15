# Lifecycle Tools Context-Aware Visualization Update

## Overview
Redesigned the lifecycle operations visualization in the ActionPlan UI component to display hooks **in context** of where they execute, rather than as a separate timeline section.

## Problem
Previously, lifecycle operations were displayed as a standalone "Lifecycle Timeline" section at the top of the action plan, disconnected from the phases and agents they relate to. This made it difficult for users to understand:
- **When** lifecycle hooks execute
- **Which phase** they're associated with
- **Which agents** they target

## Solution
Lifecycle operations are now displayed contextually based on their trigger type:

### 1. **Workflow-Level Hooks** (Chat-Level)
- **before_chat**: Displayed as "Setup Hooks" section BEFORE all phases
- **after_chat**: Displayed as "Teardown Hooks" section AFTER all phases

### 2. **Agent-Level Hooks**
- **before_agent / after_agent**: Displayed WITHIN the specific agent they target
- Shown in a dedicated "Lifecycle Hooks" subsection when the agent accordion is expanded

## Visual Structure

### Before (Old Design)
```
┌─ Workflow Header ──────────────────┐
├─ Mermaid Diagram ─────────────────┤
├─ Lifecycle Timeline ──────────────┤  ← Separate, disconnected
│  • before_chat hook               │
│  • before_agent (TargetAgent)     │
│  • after_agent (TargetAgent)      │
│  • after_chat hook                │
├─ Execution Phases ────────────────┤
│  └─ Phase 1                       │
│     └─ TargetAgent                │  ← Agent here, but hook was above
└────────────────────────────────────┘
```

### After (New Design)
```
┌─ Workflow Header ──────────────────┐
├─ Mermaid Diagram ─────────────────┤
├─ Setup Hooks (before_chat) ───────┤  ← Context: Runs BEFORE workflow
│  • Initialize workflow state      │
│  • Load configuration             │
├─ Execution Phases ────────────────┤
│  └─ Phase 1                       │
│     └─ TargetAgent ───────────────┤  ← Agent with its hooks
│        ├─ Lifecycle Hooks         │
│        │  • before_agent hook     │  ← Context: Runs before THIS agent
│        │  • after_agent hook      │  ← Context: Runs after THIS agent
│        ├─ Operations              │
│        └─ Integrations            │
├─ Teardown Hooks (after_chat) ─────┤  ← Context: Runs AFTER workflow
│  • Cleanup resources              │
│  • Send notifications             │
└────────────────────────────────────┘
```

## Implementation Details

### New Components

#### 1. **LifecycleCard** (Reusable)
```javascript
const LifecycleCard = ({ operation, idx, compact = false }) => {
  // Renders a single lifecycle operation with:
  // - Operation name
  // - Trigger badge (before_chat, after_chat, before_agent, after_agent)
  // - Target agent (if applicable)
  // - Description
  // - Compact mode for agent-level hooks
}
```

#### 2. **WorkflowLifecycleSection** (Chat-Level Hooks)
```javascript
const WorkflowLifecycleSection = ({ operations, type }) => {
  // Renders workflow-level hooks (before_chat / after_chat)
  // - type: 'before_chat' → "Setup Hooks"
  // - type: 'after_chat' → "Teardown Hooks"
  // - Shows when operations execute relative to workflow
}
```

### Updated Components

#### 1. **AgentAccordionRow**
- Added `agentLifecycleHooks` prop
- Displays lifecycle hooks within agent's expanded view
- Shows "Lifecycle Hooks" subsection before Operations/Integrations
- Uses compact lifecycle cards to save space

#### 2. **PhaseAccordion**
- Added `lifecycleOperations` prop
- Filters lifecycle operations by agent target
- Passes relevant hooks to each AgentAccordionRow

#### 3. **ActionPlan** (Main Component)
- Separates lifecycle operations into:
  - `chatLevelHooks.before_chat` → Setup Hooks section
  - `chatLevelHooks.after_chat` → Teardown Hooks section
  - Agent-level hooks → Passed to phases/agents
- Renders Setup Hooks BEFORE "Execution Phases"
- Renders Teardown Hooks AFTER "Execution Phases"

## Lifecycle Operation Types

### Workflow-Level (No Target)
```json
{
  "name": "Initialize Database",
  "trigger": "before_chat",
  "target": null,
  "description": "Set up database connections before workflow starts"
}
```
**Displayed**: Setup Hooks section (before phases)

```json
{
  "name": "Send Completion Email",
  "trigger": "after_chat",
  "target": null,
  "description": "Notify stakeholders after workflow completes"
}
```
**Displayed**: Teardown Hooks section (after phases)

### Agent-Level (With Target)
```json
{
  "name": "Load User Context",
  "trigger": "before_agent",
  "target": "PersonalizationAgent",
  "description": "Load user preferences before personalization"
}
```
**Displayed**: Within PersonalizationAgent accordion

```json
{
  "name": "Cache Results",
  "trigger": "after_agent",
  "target": "RecommendationAgent",
  "description": "Cache recommendations after generation"
}
```
**Displayed**: Within RecommendationAgent accordion

## Visual Design

### Color Scheme
- **Lifecycle hooks**: Accent color (`--color-accent` / amber-ish)
- **Operations**: Primary color (`--color-primary` / blue-ish)
- **Integrations**: Secondary color (`--color-secondary` / purple-ish)

This helps users visually distinguish lifecycle hooks from regular tools.

### Badges
Each lifecycle card shows a trigger badge:
- 🟣 **Before Chat**: "Runs before the first agent turn"
- 🟠 **After Chat**: "Runs after the workflow concludes"
- 🔵 **Before Agent**: "Runs immediately before the target agent starts"
- 🟢 **After Agent**: "Runs immediately after the target agent finishes"

## Benefits

### 1. **Better Mental Model**
Users can now see:
- ✅ Setup hooks run FIRST (before phases)
- ✅ Agent hooks run WITH the agent (in context)
- ✅ Teardown hooks run LAST (after phases)

### 2. **Reduced Cognitive Load**
- No need to scroll up to a separate timeline section
- Hooks are co-located with the agents they affect
- Clear visual hierarchy shows execution order

### 3. **Scalability**
- Works well with many lifecycle hooks
- Agent-level hooks don't clutter phase overview
- Only visible when agent accordion is expanded

### 4. **Discoverability**
- Users exploring agents naturally discover their lifecycle hooks
- Setup/Teardown sections clearly labeled with execution timing

## Migration Path

### Generator Workflow Updates
The backend workflow structure remains unchanged:
```json
{
  "workflow": {
    "lifecycle_operations": [
      { "trigger": "before_chat", "target": null, ... },
      { "trigger": "before_agent", "target": "AgentName", ... },
      { "trigger": "after_agent", "target": "AgentName", ... },
      { "trigger": "after_chat", "target": null, ... }
    ]
  }
}
```

The ActionPlan component now automatically:
1. Filters `before_chat` → Setup Hooks section
2. Filters `after_chat` → Teardown Hooks section
3. Distributes `before_agent`/`after_agent` → Relevant agents

### Backward Compatibility
✅ Fully backward compatible
- Existing workflows with lifecycle_operations will display correctly
- Workflows without lifecycle_operations display no hooks (as before)
- No runtime changes required

## Testing Checklist

### Scenario 1: Workflow with Setup/Teardown Hooks
```
Expected:
- "Setup Hooks" section appears before phases
- "Teardown Hooks" section appears after phases
- Each section shows correct hooks
```

### Scenario 2: Workflow with Agent-Level Hooks
```
Expected:
- Agent accordion shows "Lifecycle Hooks" subsection
- Hooks display with target agent name
- Hooks appear before Operations/Integrations
```

### Scenario 3: Workflow with Mixed Hooks
```
Expected:
- Setup hooks at top
- Agent hooks within agents
- Teardown hooks at bottom
- No duplicate displays
```

### Scenario 4: Workflow with No Hooks
```
Expected:
- No Setup Hooks section
- No Teardown Hooks section
- No Lifecycle Hooks in agents
- UI looks clean (no empty sections)
```

### Scenario 5: Agent with Multiple Hooks
```
Expected:
- Multiple lifecycle cards display in agent
- before_agent hooks listed first
- after_agent hooks listed second
- Cards are compact to save space
```

## Files Modified

### 1. ActionPlan.js
**Location**: `ChatUI/src/workflows/Generator/components/ActionPlan.js`

**Changes**:
- Removed `LifecycleTimeline` component (162-204)
- Added `LifecycleCard` component (reusable)
- Added `WorkflowLifecycleSection` component (chat-level)
- Updated `AgentAccordionRow` to accept and display agent hooks
- Updated `PhaseAccordion` to filter and pass agent hooks
- Updated main `ActionPlan` to organize hooks contextually

**Lines Changed**: ~150 lines modified/added

## Visual Examples

### Setup Hooks Section (before_chat)
```
┌─ Setup Hooks ──────────────────────────────┐
│ Executed before the workflow starts        │
├─────────────────────────────────────────────┤
│ 🟣 Initialize Database Connection          │
│    Before Chat                              │
│    Establishes DB connection pool          │
├─────────────────────────────────────────────┤
│ 🟣 Load Configuration                       │
│    Before Chat                              │
│    Loads workflow configuration from env    │
└─────────────────────────────────────────────┘
```

### Agent with Lifecycle Hooks
```
┌─ RecommendationAgent ──────────────────────┐
│ Generates personalized recommendations     │
├─────────────────────────────────────────────┤
│ LIFECYCLE HOOKS                             │
│ ┌─────────────────────────────────────────┐ │
│ │ 🔵 Load User Preferences                │ │
│ │    Before Agent • Target: RecAgent      │ │
│ └─────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────┐ │
│ │ 🟢 Cache Results                        │ │
│ │    After Agent • Target: RecAgent       │ │
│ └─────────────────────────────────────────┘ │
├─────────────────────────────────────────────┤
│ OPERATIONS                                  │
│ • calculate_relevance_score                 │
│ • filter_recommendations                    │
├─────────────────────────────────────────────┤
│ INTEGRATIONS                                │
│ • GoogleAnalytics                           │
└─────────────────────────────────────────────┘
```

### Teardown Hooks Section (after_chat)
```
┌─ Teardown Hooks ───────────────────────────┐
│ Executed after the workflow completes      │
├─────────────────────────────────────────────┤
│ 🟠 Send Completion Notification            │
│    After Chat                               │
│    Notifies stakeholders via email         │
├─────────────────────────────────────────────┤
│ 🟠 Cleanup Resources                        │
│    After Chat                               │
│    Closes connections and frees memory     │
└─────────────────────────────────────────────┘
```

## Future Enhancements

### Potential Improvements
1. **Phase-level hooks**: Add support for before_phase/after_phase triggers
2. **Hook dependencies**: Visual indicators if hooks depend on each other
3. **Execution timeline**: Animated timeline showing hook execution order
4. **Hook performance**: Display execution time for each hook
5. **Conditional hooks**: Show conditions that trigger optional hooks

## Summary

✅ **Problem Solved**: Lifecycle operations are now displayed in context
✅ **Better UX**: Users understand when/where hooks execute
✅ **Cleaner UI**: No separate disconnected timeline section
✅ **Scalable**: Works well with many hooks across multiple agents
✅ **Backward Compatible**: Existing workflows display correctly

The new design makes the execution flow much clearer:
```
Setup → Phase 1 → Phase 2 → ... → Phase N → Teardown
         ↓         ↓                ↓
      [Agents]  [Agents]        [Agents]
         ↓         ↓                ↓
    [Hooks]   [Hooks]          [Hooks]
```

---

**Date**: 2025-10-28
**Component**: ActionPlan.js
**Change Type**: UI/UX Enhancement
