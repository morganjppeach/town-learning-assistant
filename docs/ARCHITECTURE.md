# Town Learning Assistant - System Architecture

## Overview
The Town Learning Assistant is a high-rigor, identity-aware autonomous agent system designed to execute "Gold Standard Routines" based on real-time triggers and persisted user profiles. It separates the **Orchestration (Brain)**, **Execution (Engine)**, and **Capabilities (Action Registry)**.

## Core Components

### 1. The Brain (`town_brain.py`)
The central orchestrator. It handles:
- **Intent Routing**: Mapping user text or external events to specific Routines.
- **Context Resolution**: Bridging the `ProfileManager` and the `RoutineEngine` to ensure a routine is executed with the correct identity-aware inputs.

### 2. The Engine (`routine_engine.py`)
The state-machine execution core. Key features:
- **Memory-Aware Caching**: Uses a SHA-256 hash of the current user profile (`memory_snapshot_hash`). If the profile changes, the cache is invalidated.
- **HITL Approval Gates**: Steps marked `requires_approval=True` pause execution and set the state to `AWAITING_APPROVAL`.
- **Template Resolution**: Dynamically replaces `{{variable}}` in step parameters with values from the run's resolved inputs.

### 3. The Action Registry (`action_registry.py`)
The system's capability layer. It decouples the "what" from the "how":
- **Abstract Actions**: Routines reference actions by name (e.g., `web_search`).
- **Concrete Implementations**: The registry maps these names to Python functions. This allows the system to be upgraded from simulated actions to real API calls without changing the routine definitions.

### 4. The Persistence Layer (`town_store.py`)
A JSON-backed storage system maintaining three primary collections:
- **Profiles**: User identity and preference data.
- **Routines**: The blueprint of workflows.
- **Run Logs**: Historical execution data and step results.

## Data Flow
`External Trigger (Zapier/User)` $\to$ `TownBrain` $\to$ `ProfileManager (Resolve Inputs)` $\to$ `RoutineEngine` $\to$ `ActionRegistry (Execute Step)` $\to$ `TownStore (Log Result)`
