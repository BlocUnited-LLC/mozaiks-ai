# Competitor Analysis — Automation Creation

This document compares MozaiksAI with CrewAI, Toolhouse, Lindy, and n8n from an automation-creation perspective.

## TL;DR — Positioning
- CrewAI: Enterprise agent management platform (visual + API) built atop their OSS framework; strong orchestration, tracing, RBAC, serverless scaling.
- Toolhouse: Agentic Backend‑as‑a‑Service; define agents as code, deploy as APIs; curated MCP servers (RAG, memory, browser, code exec), CLI/schedules/observability.
- Lindy: Productized business agents with templates (sales, email, meetings, support), hundreds of integrations, web embed/mobile, compliance.
- n8n: Open‑source low‑code automation for technical teams; 500+ integrations, code+UI hybrid, self‑host, mature ops surface.
- MozaiksAI: Foundry + runtime that turns prompts into running, monetizable apps via declarative workflows, multi‑tenant runtime, observability, and token accounting.

## What they optimize for
- CrewAI: Managing fleets of agents reliably at enterprise scale.
- Toolhouse: Shipping agent backends quickly with MCP servers and developer tooling.
- Lindy: Getting business teams productive fast with packaged agents and templates.
- n8n: General-purpose automation with deep integrations and self-host choice.
- MozaiksAI: Turning ideas into full products (runtime+UI+orchestration+persistence+observability+billing hooks).

## Capability comparison (high-level)
- App generation vs. orchestration
  - MozaiksAI: Generator emits workflow JSON + code stubs; runtime executes; ships a working ChatUI-based app.
  - CrewAI/Toolhouse: Focus on orchestration/backends; UI/app surface is your responsibility.
  - n8n: Automation-first; not a product foundry.
  - Lindy: Prebuilt app surfaces; less developer-extensible runtime.

- Runtime production-readiness
  - MozaiksAI: Multi-tenant isolation, Mongo persistence, idempotency, retries/timeouts, structured logs, perf metrics, token accounting.
  - CrewAI: Tracing, training, guardrails, RBAC, serverless scaling; strong enterprise posture.
  - Toolhouse: Observability, execution logs, schedules; reliable BaaS.
  - n8n: Logs/replay, on‑prem, RBAC, audit; very mature.
  - Lindy: Business-facing compliance/security; less developer‑level runtime control.

- Tools/Integrations model
  - MozaiksAI: Declarative JSON tool manifests; structured outputs; auto‑tool binding; hot‑swappable workflows.
  - CrewAI: Studio + APIs + triggers; strong enterprise workflows.
  - Toolhouse: MCP-first; curated servers for common agent needs; custom MCP code allowed.
  - n8n: 500+ integrations; code nodes; templates.
  - Lindy: Many integrations for business tasks; templates and embeddings.

## When to choose which
- Pick MozaiksAI when you need “prompt → product” with: multi-tenant runtime, declarative workflows, token accounting, and UI transport wired in.
- Pick CrewAI if you need enterprise agent lifecycle management, RBAC, tracing/training, and centralized governance at scale.
- Pick Toolhouse if you want MCP-enabled agent backends as APIs with CLI/SDK ergonomics and scheduling/observability built-in.
- Pick n8n for general automation across 500+ integrations, with code+UI hybrid and strong self-hosting/ops.
- Pick Lindy for out-of-the-box business agents and templates with minimal setup.

## Honest gaps and risks

- Competitors
  - CrewAI/Toolhouse: May require more work to deliver complete app surfaces (frontend + UX + monetization hooks).
  - n8n: Not purpose-built for agent runtimes; AI is one modality.
  - Lindy: Less developer-extensible runtime for bespoke apps.

## Positioning talk track
“We ship apps, not just orchestrations. Your prompt becomes a running product with its own agent runtime, transport, persistence, observability, multi-tenant boundaries, and token accounting. Workflows are declarative and hot-swappable—update JSON, not the runtime.”
