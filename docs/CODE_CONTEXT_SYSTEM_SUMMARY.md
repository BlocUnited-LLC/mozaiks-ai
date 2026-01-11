# MozaiksAI Generation-Time Systems (Dec 2025)

This repo has **two separate generation-time capabilities**:

1) **Patch/PR Update System (SHIPPED)**: deterministic snapshots + patchsets + conflicts, then the backend creates a branch + PR (MozaiksAI never pushes the default branch).
2) **Code Context Tools (OPTIONAL / PROTOTYPE)**: code indexing + intent-based context views to help agents understand a codebase before writing.

---

## A) Patch/PR Update System (SHIPPED)

Goal: update an existing exported repo **without overwriting user edits**.

### Initial export (new repo)
- Generate bundle -> backend deploy/export pipeline creates repo -> MozaiksAI records `WorkflowExports` and persists a snapshot.

### Update export (existing repo)
1. Resolve `repo_url` from `WorkflowExports`.
2. Fetch repo manifest (path -> sha256 + `baseCommitSha`) from backend.
3. Build baseline snapshot (prefer prior `snapshotId`, else hash-only snapshot from repo manifest).
4. Build target snapshot from the newly generated bundle.
5. Compute deterministic patchset + conflicts.
6. Ask backend to create a branch + PR from the patchset (no direct push).

Key modules:
- Snapshots + patchsets: `workflows/_shared/app_code_versions.py`
- AppGenerator update export orchestration: `workflows/AppGenerator/tools/export_app_code.py`
- Backend calls (repo manifest + PR creation): `workflows/AgentGenerator/tools/export_to_github.py`

---

## B) Code Context Tools (OPTIONAL / PROTOTYPE)

Goal: help agents write consistent code by exposing token-efficient context (imports/symbols/exports) before generating or modifying files.

Status:
- Implementations exist under `workflows/AppGenerator/tools/code_context/` and `workflows/AgentGenerator/tools/code_context/`.
- **Not enabled by default**: these tools are **not registered** in `workflows/AppGenerator/tools.json` or `workflows/AgentGenerator/tools.json`.
- Not required for the shipped PR-update workflow.

To enable (proposed wiring):
1. Add tool entries to each workflow `tools.json` for: `index_codebase`, `get_code_context`, `get_code_diff`.
2. Initialize tools in workflow runtime startup with a Mongo client (`initialize_code_context_tools(...)`).
3. Register `CODE_CONTEXT_TOOLS` with agents and update prompts to call them.

---

## Safety

Shipped update/export is safe-by-default:
- **Never pushes default branch**: updates always request a **branch + PR** from the backend.
- **Deterministic artifacts**: snapshots + patchsets use stable sha256-based IDs.
- **No secrets in artifacts**:
  - redacts secret-like keys/values from structured outputs before persistence
  - excludes sensitive paths like `.env` (except `.env.example`) and key material (e.g., `*.pem`, `*.key`) from snapshots/patchsets
