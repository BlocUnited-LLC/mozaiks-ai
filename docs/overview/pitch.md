# MozaiksAI — Pitch

## One‑liner (elevator pitch)
MozaiksAI turns plain‑English ideas into working, monetizable AI apps by orchestrating multiple agents that design, build, and run your product—end to end.

## 30‑second non‑technical pitch
Tell us what you want to build, and MozaiksAI does the rest. It plans the product, assembles the right AI “team,” and generates the code and workflows to launch a real app—complete with chat interfaces, automations, and observability. Unlike normal AI chats that give you a document or a snippet, MozaiksAI ships a running product and keeps improving it as your needs evolve. It’s like hiring a startup team that executes instantly.

## 90‑second technical pitch
MozaiksAI is an AG2-based, multi-agent runtime that executes declarative, hot‑swappable workflows to build and operate AI‑native apps. The runtime provides:
- Transport: WebSocket/HTTP ChatUI integration, event streaming, correlation IDs
- Orchestration: GroupChat, tool binding, lifecycle hooks, retries, timeouts
- Persistence: Mongo-backed session/state with idempotency and audit trails
- Observability: Unified logs, perf metrics, runtime logging export
- Multi‑tenant boundaries: app_id/user_id isolation; cache seeds per chat
- Monetization hooks: token tracking via MozaiksPay (usage/cost per tenant/user)
- Extensibility: Tools declared in JSON and loaded at runtime; no hardcoded routes

The Generator doesn't just output JSON—it writes working code: tool stubs (.py/.js) and UI interaction components that wire directly into the React ChatUI. The runtime loads these declarative specs, validates structured outputs, auto‑calls tools (including custom UI elements), and streams live results. You get a running app with interactive UI, not just a spec file. Because workflows are declarative and hot‑swappable, you can iterate quickly without refactoring the runtime. The result isn't just an LLM demo—it's a production‑ready, instrumented app that ships with agentic features and cost controls.

## Value props and differentiators
- From idea to running app: Not just code suggestions—MozaiksAI outputs working apps with agentic automations, UI wiring, and persistence.
- Generated UI interactions: The Generator produces not only workflow JSON but also tool stubs (.py/.js) and UI components that provide rich, interactive experiences in the ChatUI—no manual wiring required.
- Declarative workflows, hot‑swappable: Update JSON specs to change behavior; no hardcoded orchestration.
- Multi‑tenant and production‑minded: Built‑in isolation, idempotency, retries, timeouts, and structured logging.
- Tooling neutrality: Load tools from manifests; align to stable AG2 patterns—no lock‑in to brittle, private APIs.
- First‑class observability and token accounting: Track per app/user, making ops and monetization practical from day one.
- UI/tool contract without schema coupling: The runtime forwards and correlates UI/tool events while keeping schemas modular and replaceable.

## Competitor comparison (lite)
- vs LangChain/LangGraph: Those are great libraries; MozaiksAI is a full runtime with transport, multi‑tenant boundaries, observability, and declarative workflow loading—less DIY glue to reach production.
- vs Crew/Agent orchestrators: Many focus on planning or chat. MozaiksAI covers the full lifecycle: planning → code/workflows → transport → persistence → observability → monetization hooks.
- vs Zapier/Pipedream/Make: Those automate APIs well. MozaiksAI generates the app itself (front/back/runtime) and embeds agentic reasoning, while still integrating tools/APIs as steps.
- vs Retool/Builder.io: They speed up UI and data apps; MozaiksAI starts earlier (turns ideas into workflows + agents + tools) and runs them with a production agent runtime.

## Plain‑language metaphors
- Movie director + film crew: You describe the movie (your app). MozaiksAI directs specialist agents (crew) to write scenes (workflows), assemble sets (tools), and ship the premiere (running product).
- Factory assembly line: Your prompt is the blueprint; MozaiksAI configures stations (agents/tools) that fabricate a working product with QA, metrics, and cost tracking.
- Orchestra conductor: You set the theme; MozaiksAI coordinates instruments (agents/tools) using a score (workflow JSON) to produce a polished performance (live app).

## Taglines
- “From prompt to product—automatically.”
- “Your AI startup team, on demand.”
- “Describe it. We ship it.”

## Simple demo talk track
1) “I’ll describe an app in plain English.”  
2) “MozaiksAI drafts an action plan and structured workflow.”  
3) “It generates the code and wires tools, then the runtime executes it live.”  
4) “You’ll see the app running in the ChatUI with logs, metrics, and auto‑tool calls.”  
5) “From here, we can change the JSON workflow and hot‑swap behavior—no refactor.”

---

Want to see how we compare? Read the Competitor Analysis in `docs/overview/competitors.md`.
