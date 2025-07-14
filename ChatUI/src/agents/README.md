# ChatUI Agent Registry System

## Overview

The ChatUI Agent Registry System mirrors the core workflow registry pattern, ensuring that the **Core ChatUI never changes** while enabling dynamic agent registration and discovery.

## Architecture

### Core Principles

1. **Stable Core**: `agents/index.js` provides a stable interface that never changes
2. **Dynamic Registration**: New agents are added via registry decorators, not code changes
3. **Auto-Discovery**: Agents are automatically discovered and registered
4. **Plugin Architecture**: Agents can be loaded as plugins at runtime

### System Components

```
ChatUI/src/agents/
├── index.js                 # STABLE - Core agent system interface
├── registry/               # Registry system (mirrors core/workflow)
│   ├── agentRegistry.js    # Core registration system
│   ├── agentDiscovery.js   # Auto-discovery system
│   ├── agentBase.js        # Base classes and interfaces
│   └── index.js           # Registry exports
├── instances/              # Agent implementations
│   ├── initializer.js     # System initialization
│   └── *.js              # Individual agents
└── components/            # UI components (existing)
```

## Creating New Agents

### 1. Basic Agent

```javascript
import { registerAgent, BaseAgent, AgentCapabilities } from '../registry';

@registerAgent('my_agent', {
  capabilities: [AgentCapabilities.TEXT_GENERATION],
  category: 'general',
  description: 'My custom agent'
})
export default class MyAgent extends BaseAgent {
  async processMessage(message) {
    return {
      type: 'text',
      content: `Hello! You said: ${message.text}`
    };
  }
}
```

### 2. Interactive Agent

```javascript
import { registerAgent, InteractiveAgent, AgentCapabilities } from '../registry';

@registerAgent('interactive_agent', {
  capabilities: [AgentCapabilities.UI_GENERATION],
  category: 'ui',
  interactive: true
})
export default class InteractiveAgent extends InteractiveAgent {
  static allowedComponents = ['button', 'form', 'input'];

  async processMessage(message) {
    return this.createUIMessage('button', {
      text: 'Click me!',
      action: 'button_click'
    }, 'Here is an interactive button');
  }

  async handleAction(action) {
    if (action.type === 'button_click') {
      return {
        content: 'Button was clicked!',
        timestamp: Date.now()
      };
    }
  }
}
```

### 3. Agent with Initialization

```javascript
import { addAgentInitializer, registerAgent } from '../registry';

// Agent initialization (runs at startup)
export const myAgentInit = addAgentInitializer(async function myAgentSetup() {
  console.log('🔧 Setting up My Agent...');
  // Initialize resources, connections, etc.
});

@registerAgent('my_agent', {
  capabilities: ['custom_capability'],
  category: 'specialized'
})
export default class MyAgent extends BaseAgent {
  // ... agent implementation
}
```

## Usage

### Initialize the System

```javascript
import { initializeAgentSystem } from './agents';

// During app startup
await initializeAgentSystem();
```

### Use Agents

```javascript
import { processMessage, handleAction, getAgent } from './agents';

// Process a message
const response = await processMessage({ text: 'Hello!' });

// Use specific agent
const response = await processMessage({ text: 'Hello!' }, 'feedback_agent');

// Handle UI action
const result = await handleAction({
  type: 'button_click',
  agentType: 'interactive_agent'
});

// Get agent instance directly
const agent = await getAgent('my_agent');
const response = await agent.processMessage({ text: 'Hello!' });
```

### Discovery and Inspection

```javascript
import { getAllAgents, getAgentsByCapability, getAgentManifest } from './agents';

// Get all registered agents
const agents = getAllAgents();

// Find agents with specific capabilities
const textAgents = getAgentsByCapability('text_generation');

// Get full system manifest
const manifest = getAgentManifest();
```

## Comparison with Core Workflow System

| Core Workflow | ChatUI Agents |
|---------------|---------------|
| `@register_workflow()` | `@registerAgent()` |
| `@add_initialization_coroutine` | `addAgentInitializer()` |
| `register_workflow_tools()` | `registerAgentCapabilities()` |
| `get_workflow_handler()` | `getAgentHandler()` |
| Auto-discovery in Python | Auto-discovery in JavaScript |
| Transport-aware routing | Transport-aware agent loading |

## Benefits

1. **Modularity**: Agents can be added/removed without touching core code
2. **Dynamic Loading**: Agents can be loaded as plugins at runtime
3. **Auto-Discovery**: New agents are automatically found and registered
4. **Type Safety**: Strong typing and validation for agent metadata
5. **Metrics**: Built-in performance and usage tracking
6. **Compatibility**: Maintains backward compatibility with existing code

## Migration from Old System

The old hardcoded agent system is still supported but deprecated:

```javascript
// OLD WAY (deprecated)
import { ExampleAgent } from './agents';

// NEW WAY (recommended)
import { getAgent } from './agents';
const agent = await getAgent('example_agent');
```

## Development Tools

In development mode, additional utilities are available:

```javascript
import { dev } from './agents';

// Inspect registry
const manifest = dev.inspectRegistry();

// Trigger manual discovery
await dev.rediscoverAgents(['./custom-agents/**/*.js']);

// Debug registry internals
const debug = dev.debugRegistry();
```

## Future Enhancements

- **Plugin Loading**: Load agents from external packages
- **Hot Reloading**: Reload agents without restarting the app
- **Agent Marketplace**: Discover and install community agents
- **AI-Powered Routing**: Use LLM to route messages to best agents
- **Agent Composition**: Chain multiple agents for complex tasks

## Migration Status ✅

### ✅ COMPLETED CLEANUP
The ChatUI agent system has been fully migrated to the new registry-based architecture:

#### Files Removed (Legacy Code)
- `~/src/universal-manifest.json` - Static component manifest
- `~/src/workflows-manifest.json` - Static workflow manifest  
- `~/src/agents/instances/agents-manifest.json` - Static agent manifest
- `~/src/agents/components/ChatPane/manifest.json` - Static component manifest
- `~/src/core/pluginRegistry.js` - Legacy plugin loader
- `~/src/core/dynamicComponentLoader.js` - Legacy component loader
- `~/src/agents/components/ChatPane/componentRegistry.js` - Legacy component registry

#### Files Updated (Modern Registry System)
- `~/src/context/ChatUIContext.js` - Now initializes new agent system
- `~/src/core/agui.js` - Uses registry-based component loading
- `~/src/hooks/useDynamicComponents.js` - Uses new component registry
- `~/src/agents/index.js` - Updated exports, removed legacy references

#### New Registry System Files
- `~/src/agents/registry/` - Complete registry system
- `~/src/agents/instances/initializer.js` - System initialization
- `~/src/agents/components/ChatPane/index.js` - New component registry
- `~/src/agents/instances/FeedbackAgent.js` - Example updated agent

### ✅ BENEFITS ACHIEVED
1. **Zero Static Manifests**: All discovery is now dynamic
2. **Modular Architecture**: Core never changes when adding agents/components
3. **Auto-Discovery**: New agents/components are found automatically
4. **Transport Awareness**: Registry handles different transport types
5. **Performance**: Lazy loading and intelligent caching
6. **Developer Experience**: Clear patterns for adding new functionality

### ✅ USAGE PATTERNS
The system now follows consistent patterns that mirror the core workflow registry:

```javascript
// Add new agent - just create the file, no core changes needed
@registerAgent('my_agent', { capabilities: ['text_generation'] })
export default class MyAgent extends BaseAgent { ... }

// Use agents - stable interface that never changes  
import { getAgent, processMessage } from './agents';
const response = await processMessage(message, 'my_agent');

// System initialization - automatic via ChatUIProvider
// No manual setup required, agents auto-discovered and registered
```
