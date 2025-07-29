
# ============================================================================== 
# Mozaiks Platform Architecture: The World's First AI-Driven Startup Foundry
# ==============================================================================

## Platform Vision


**Mozaiks is the world's first AI-driven startup foundry.**

With one prompt, a user's idea becomes a real, monetizable product—equipped with agentic features. Mozaiks delivers fully structured, feature-rich applications with agentic architecture from the first prompt. Every app is built with a modular AI-native stack (MozaiksCore) that supports complex, autonomous functionality by design. No endless prompting. Just smart, AI-powered products from the start.

**MozaiksCore**: The modular, production-ready foundation for every app, including user management, subscription management, and the agentic backbone (MozaiksAI Core runtime and ChatUI). 

**MozaiksAI**: The Core runtime and ChatUI for workflows to run on, powering agentic features for every app. This is the layer that executes workflows and provides the real-time agentic experience.

**MozaiksStream**: The token engine layer, managing tokens for each user and each app (enterprise). This enables subscription logic, usage-based billing, and analytics for both users and apps. App creators never have to worry about token management—it's all handled by MozaiksStream.

**Multi-App, Multi-Tenant**: In Mozaiks, each user can create multiple apps (called "enterprises"). Each app gets a unique `enterprise_id`, and each user has a unique `user_id`. Token tracking and billing are managed by both `user_id` and `enterprise_id`, so users can see usage/costs per app and per user.


### The Mozaiks System: Multi-App, Multi-Tenant Startup Foundry

```mermaid
graph TB
    subgraph "🏭 Mozaiks: Startup Foundry (Multi-App, Multi-Tenant)"
        MZ[mozaiks.ai]
        GW[Generator Workflow]
        MC[MozaiksCore]
        MAI[MozaiksAI Runtime]
        MS[MozaiksStream (Token Engine)]
        WF[Workflow Files]
    end
    
    subgraph "🎨 User Apps (Enterprises)"
        APP1[User App 1 (enterprise_id_1)]
        APP2[User App 2 (enterprise_id_2)]
        APP3[User App 3 (enterprise_id_3)]
        CUI1[ChatUI]
        CUI2[ChatUI]
        CUI3[ChatUI]
    end
    
    subgraph "🏢 Platform Infrastructure (shared_app.py, token_engine.py)"
        WE[WebSocket Engine]
        TE[MozaiksStream Token Engine]
        PE[Persistence Engine]
        EP1["/ws/generator/{enterprise_id}/{chat_id}/{user_id}"]
        EP2["/ws/{workflow}/{enterprise_id}/{chat_id}/{user_id}"]
    end
    
    MZ --> GW
    GW --> WF
    WF --> EP2
    MC --> MAI
    MAI --> WE
    WE --> EP1
    WE --> EP2
    TE --> WE
    PE --> WE
    APP1 --> CUI1
    APP2 --> CUI2
    APP3 --> CUI3
    CUI1 --> EP2
    CUI2 --> EP2
    CUI3 --> EP2
```

## Business Model: "Startup Foundry-as-a-Service"

**Mozaiks enables users to create multiple apps (enterprises), each with its own agentic features and monetization.**

- **Subscription + Usage-Based Billing**: Users pay for the ability to create apps (enterprises) and for the tokens their apps consume. MozaiksStream abstracts all token management, so app creators never have to worry about it.
- **Token Tracking by App and User**: All token usage is tracked by both `enterprise_id` (app) and `user_id` (user), enabling analytics and billing at both levels.
- **Generator Workflow as Build Process**: The generator workflow is part of the build process, filling the workflows folder and building out app functionality on top of MozaiksCore.
- **MozaiksCore as Foundation**: Every app is built on MozaiksCore, which includes user management, subscription management, and the agentic backbone (MozaiksAI runtime and ChatUI).

**This is not just "Shopify for AI Agents"—it's the world's first AI-driven startup foundry, where every user can launch fully agentic, monetizable apps from a single prompt. Users can create as many apps as they want, with each prompt creating one complete app.**

### 🏭 **Mozaiks.ai (Your Platform)**
- **App building platform**: Users come to build complete apps with agentic functionality
- **Generator workflow**: Takes high-level concepts and breaks them into functional workflows
- **Output**: Complete app foundation + multiple specialized workflow folders
- **MozaiksCore provides**: ChatUI source code + core logic + infrastructure
- **Revenue**: Subscription for app creation + usage fees

### 🎨 **User Apps (Enterprises)**
- **Get complete app foundation**: MozaiksCore + agentic workflow files included
- **Generator builds**: Agentic functions for their specific app requirements
- **Customize and deploy**: Complete apps with built-in agentic functionality
- **Pay usage fees** based on token consumption through MozaiksStream

## Platform Components

### 1. **Workflow Factory** (Tier 1: Your App)
```
mozaiks.ai/
├── Generator Workflow (the only workflow you run)
├── ChatUI (for workflow creation)
├── User Dashboard (manage created workflows)
└── Billing Portal (usage tracking)
```

### 2. **Platform Infrastructure** (shared_app.py Enhanced)
```python
# Enhanced shared_app.py - The Runtime Engine
class PlatformRuntime:
    """
    Hosts ALL workflow WebSocket endpoints.
    Handles real-time connections from third-party apps.
    """
    
    # Dynamic workflow registration
    @app.post("/api/workflows/register")
    async def register_workflow(workflow_definition):
        """Generator calls this to create new workflow endpoints"""
    
    # Live WebSocket endpoints (auto-created)
    @app.websocket("/ws/{workflow_name}/{enterprise_id}/{chat_id}/{user_id}")
    async def workflow_endpoint(websocket, workflow_name, enterprise_id, chat_id, user_id):
        """Real-time agent communication for any workflow"""
    
    # Discovery API for third-parties
    @app.get("/api/workflows/discover/{enterprise_id}")
    async def discover_workflows(enterprise_id):
        """App owners can see their available workflows"""
```

### 3. **MozaiksCore Foundation + Generated Workflows**
```javascript
// What users get from Mozaiks:
1. MozaiksCore foundation (complete infrastructure)
   - ChatUI/src/pages/ChatPage.js (React component)
   - User management, subscription management
   - WebSocket connection logic and infrastructure
   - Core logic and persistence layer

2. Generated workflow files (populated by Generator)
   - workflows/refund-handler/ (handles refund requests and processing)
   - workflows/order-tracker/ (tracks order status and updates)
   - workflows/customer-support/ (general support and routing)
   - Each workflow folder contains specific agentic functions for that app feature

// How it works together:
// MozaiksCore provides the foundation, Generator populates the workflows
function UserApp() {
  return (
    <MozaiksCoreApp 
      workflows={generatedWorkflows}
      branding={{ logo: "user-logo.png", colors: {...} }}
      enterprise_id="enterprise_123"
    />
  );
}
```

## Developer Journey

### Step 1: App Creation at Mozaiks.ai
```
1. User visits mozaiks.ai to build an app
2. Authenticates and selects plan
3. Uses Generator workflow via ChatUI:
   "Build a customer support app that handles refunds and tracks orders"
4. Generator breaks down the concept into specific functional workflows:
   - refund-handler/ (handles refund requests and processing)
   - order-tracker/ (tracks order status and updates)
   - customer-support/ (general support and routing)
5. User gets delivery package:
   - MozaiksCore foundation (ChatUI + core logic + infrastructure)
   - Multiple workflow folders (each handling specific app functions)
   - Complete app ready for deployment and customization
```

### Step 2: App Deployment and Customization
```
1. User receives MozaiksCore foundation with functional workflow folders:
   - workflows/refund-handler/ (refund processing logic)
   - workflows/order-tracker/ (order tracking logic)  
   - workflows/customer-support/ (general support routing)
2. Customizes branding/styling to match their vision (ChatUI themes, colors, logo)
3. Deploys their complete app with specialized agentic functions
4. App runs on MozaiksCore infrastructure with their custom functional workflows
5. End users interact with specialized agents through branded ChatUI interface
```

### Step 3: Production Usage
```
1. Their users chat with AI agents in real-time
2. All communication flows through your WebSocket infrastructure
3. Token usage tracked per conversation
4. Developer gets billed monthly based on usage
5. You handle all the AI complexity - they handle UX/branding
```

## Technical Architecture

### Enhanced shared_app.py Structure
```python
# Platform Runtime (enhanced shared_app.py)
class MozaiksPlatformRuntime:
    
    # ==========================================
    # Workflow Management
    # ==========================================
    async def register_workflow_from_generator(self, workflow_definition):
        """Called by Generator to create new workflow endpoints"""
        
    async def create_dynamic_websocket_endpoint(self, workflow_name, enterprise_id):
        """Dynamically create WebSocket endpoints for new workflows"""
        
    # ==========================================
    # Real-time Communication
    # ==========================================
    @app.websocket("/ws/{workflow_name}/{enterprise_id}/{chat_id}/{user_id}")
    async def unified_workflow_endpoint(self, websocket, workflow_name, enterprise_id, chat_id, user_id):
        """Single endpoint pattern for all workflows"""
        
        # 1. Authenticate connection
        # 2. Load workflow definition
        # 3. Initialize token tracking
        # 4. Execute workflow with real-time streaming
        # 5. Track usage and bill accordingly
        
    # ==========================================
    # App Management APIs (for app owners)
    # ==========================================
    @app.get("/api/app/workflows/{enterprise_id}")
    async def get_app_workflows(self, enterprise_id):
        """App owner can see their app's available workflows"""
        
    @app.get("/api/app/analytics/{enterprise_id}")
    async def get_app_analytics(self, enterprise_id):
        """App owner can see their app's usage analytics"""
        
    @app.get("/api/app/usage/{enterprise_id}")
    async def get_app_usage_data(self, enterprise_id):
        """Real-time usage tracking for the app owner's billing dashboard"""
```

### Unified Token Engine (No More Overlap!)
```python
# platform/core/token_engine.py
class TokenEngine:
    """Single source of truth for ALL token operations"""
    
    async def track_websocket_session(self, websocket, workflow_name, enterprise_id):
        """Track tokens for entire WebSocket connection lifecycle"""
        
    async def stream_usage_updates(self, websocket, usage_data):
        """Real-time usage updates to client during conversation"""
        
    async def calculate_session_billing(self, session_data):
        """Calculate final billing for completed session"""
```

### Clean Data Persistence (No More Token Logic!)
```python
# platform/core/persistence_engine.py  
class PersistenceEngine:
    """Pure data storage - NO token logic"""
    
    async def save_workflow_definition(self, workflow_name, definition):
        """Store workflow created by Generator"""
        
    async def save_chat_state(self, enterprise_id, chat_id, messages):
        """Store conversation state for resume"""
        
    async def load_workflow_for_execution(self, workflow_name, enterprise_id):
        """Load workflow definition for WebSocket execution"""
```

## File Structure After Migration

### Remove (Redundant/Conflicting)
```
❌ core/data/token_manager.py       # Redundant with unified usage_manager.py
❌ Multiple token tracking systems   # Unified in core/usage/usage_manager.py
❌ Separate platform/ folder        # Everything is part of MozaiksCore
❌ SDK and examples folders         # Not needed - users get complete MozaiksCore
```

## Revenue Model

### 💰 **Multiple Revenue Streams**

1. **Workflow Creation Subscription**
   - Monthly/yearly plans for using the Generator
   - Tiered based on number of workflows created

2. **Usage-Based Billing**  
   - Per-token charges for WebSocket conversations
   - Real-time tracking and monthly billing

3. **Enterprise Features**
   - Custom workflow hosting
   - White-label ChatUI packages  
   - Premium support and SLAs

4. **Developer Marketplace**
   - Revenue share on popular workflow templates
   - Premium component libraries

## Competitive Advantages

### ✅ **Real-Time by Design**
- WebSocket-first architecture
- Streaming agent responses
- Live usage tracking

### ✅ **Complete Package**
- AI infrastructure + UI components + hosting
- Developers get everything needed to integrate

### ✅ **Zero AI Complexity for Clients**
- They handle branding/UX, you handle AI
- No need to understand LLMs, agents, or prompting

### ✅ **Network Effects**
- More developers = more workflow variety
- More workflows = more developer attraction
- ChatUI becomes industry standard

## Success Metrics

### Technical KPIs
- WebSocket connection uptime: >99.9%
- Average agent response time: <2 seconds  
- Developer integration time: <4 hours
- ChatUI component adoption rate

### Business KPIs
- Monthly recurring revenue from subscriptions
- Usage-based revenue growth rate
- Number of active workflow endpoints
- Third-party app integrations per month

---

**You're building the infrastructure layer for the AI agent driven app economy.** Every business that wants AI agentic functionality in their app will use your platform - you handle the complexity, they handle the customer experience.

This is "Shopify for AI Driven Apps" - and just like Shopify enabled millions of e-commerce stores, MozaiksAI will enable millions of AI-powered applications!