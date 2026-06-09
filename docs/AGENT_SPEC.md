# Town Learning Assistant - Agent Specification (Machine Readable)

This document provides the technical specification required for an AI Agent to operate, extend, or integrate with the Town Learning Assistant.

## 1. Core Data Models (`routine_schema.py`)

### Routine
- `routine_id` (str): Unique identifier.
- `required_profile_fields` (List[str]): Fields that MUST be resolved from the User Profile before execution.
- `steps` (List[RoutineStep]): Ordered sequence of actions.

### RoutineStep
- `step_id` (str): Unique ID for caching/results.
- `action` (str): The key used to look up the function in `ActionRegistry`.
- `params` (Dict): Arguments for the action. Supports `{{var}}` syntax for dynamic resolution.
- `requires_approval` (bool): If True, pauses execution for Human-in-the-loop (HITL) sign-off.

### RunState
- `status`: `PENDING` $\to$ `RUNNING` $\to$ (`AWAITING_APPROVAL` | `COMPLETED` | `FAILED`).
- `memory_snapshot_hash`: SHA-256 of the profile at start time.

## 2. API Reference (Internal)

### TownBrain.handle_input(profile_id, text)
- **Purpose**: Entry point for user interaction.
- **Logic**: 
  1. If text contains "set preference", updates the profile.
  2. Otherwise, treats text as a `routine_id` and triggers execution.

### TownBrain.trigger_routine(routine_id, profile_id, event_context)
- **Purpose**: Programmatic trigger for a routine.
- **Inputs**: `event_context` (Dict) - data from the trigger (e.g., Zapier payload).

### RoutineRunner.execute(run_state, routine, profile_id)
- **Purpose**: Executes the logic of a routine.
- **Caching**: Skips steps already present in `run_state.step_results` IF `memory_snapshot_hash` is unchanged.

## 3. Extension Guide: Adding New Capabilities

To add a new tool to the system, follow these steps:

1. **Implement the Action**: Create a Python function in `action_registry.py` with the signature `def func(params, inputs)`. If the action requires external APIs, use the `_Provider` base class pattern to ensure tiered fallback.
2. **Register the Action**: Call `self.register("action_name", func)` in `ActionRegistry._register_defaults()`.
3. **Define the Routine**: Create a `Routine` object (via `populate_gold_routines.py` or direct JSON) using the `action_name` in a `RoutineStep`.

### 3.1 Configuration (Environment Variables)
The `ActionRegistry` uses the following optional environment variables for production-grade capabilities:
- **Execution Mode**: `TOWN_EXECUTION_MODE` (`api` or `cli`). Determines if the system uses direct API calls or wraps CLI tools like `claude-code`.
- **Search**: `TAVILY_API_KEY`, `SERPAPI_API_KEY`
- **LLM**: `OPENAI_API_KEY`, `OPENAI_MODEL`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`
- **Fallback**: If no keys are provided and mode is `api`, the system defaults to a keyless DuckDuckGo scrape and a deterministic heuristic summarizer. If mode is `cli`, it attempts to use `claude-code` before falling back to API/heuristic.

## 4. State Transition Table

| Current Status | Event | Next Status | Action |
| :--- | :--- | :--- | :--- |
| `PENDING` | `execute()` | `RUNNING` | Resolve profile $\to$ Start steps |
| `RUNNING` | `step.requires_approval == True` | `AWAITING_APPROVAL` | Save state $\to$ Pause |
| `AWAITING_APPROVAL` | `approval_received` | `RUNNING` | Resume from paused step |
| `RUNNING` | `all steps complete` | `COMPLETED` | Log end_time $\to$ Return results |
| `RUNNING` | `Exception raised` | `FAILED` | Log error $\to$ Stop |
