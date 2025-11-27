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

### **MozaiksCore Foundation + Generated Workflows**

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

### **Stateless Semantic Context Strategy**

To ensure high cohesion between generated agents without introducing stateful dependencies, the runtime employs a **Semantic Context Injection** strategy.

- **Mechanism**: The runtime hooks (`update_agent_state`) inspect the `context_variables` for structured outputs from upstream agents (e.g., `WorkflowStrategy`, `TechnicalBlueprint`).
- **Injection**: A concise summary of these upstream decisions (Phases, UI Components, Tools) is dynamically generated and injected into the system prompt of the current agent.
- **Result**: Agents "remember" and align with the specific architectural decisions made earlier in the session, ensuring the final generated code is internally consistent and follows the user's unique requirements, all while remaining purely stateless.

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
---

**You're building the infrastructure layer for the AI agent driven app economy.** Every business that wants AI agentic functionality in their app will use your platform - you handle the complexity, they handle the customer experience.

This is "Shopify for AI Driven Apps" - and just like Shopify enabled millions of e-commerce stores, MozaiksAI will enable millions of AI-powered applications!

---

## Core Architectural Components

- **Human Interaction**: Three-layer stateless model (Strategy → Architect → Implementation) ensuring UI consistency. See `docs/workflows/HUMAN_INTERACTION_STATELESS_STRATEGY.md`.
- **Agent Taxonomy**: Stateless role propagation (Implementation → ContextVariables → Agents) ensuring architectural consistency. See `docs/workflows/AGENT_TAXONOMY_STATELESS_STRATEGY.md`.
- **Context Variables**: Six-type taxonomy (config, data_reference, data_entity, computed, state, external) defined in `CONTEXT_VARIABLES_SIX_TYPE_ALIGNMENT.md`.