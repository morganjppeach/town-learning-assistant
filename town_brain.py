import uuid
from typing import Any, Dict, Optional
from routine_schema import Routine, RunState, RoutineStatus
from town_store import TownStore
from profile_manager import ProfileManager
from routine_engine import RoutineRunner

class TownBrain:
    def __init__(self, store: TownStore):
        self.store = store
        self.profiles = ProfileManager(store)
        self.runner = RoutineRunner(store)

    def handle_input(self, profile_id: str, text: str):
        # Simplified Intent Routing
        if "set preference" in text.lower():
            # Basic parser: "set preference tone concise"
            parts = text.split()
            if len(parts) >= 4:
                key, val = parts[2], parts[3]
                self.profiles.update_preference(profile_id, key, val)
                return f"Updated {key} to {val}."
        
        # Assume everything else is a request for a specific routine (by name)
        routine = self.store.get_routine(text) # Simplified: treat text as routine_id
        if not routine:
            return "No matching routine found."
        
        return self.trigger_routine(routine.routine_id, profile_id, {"user_query": text})

    def trigger_routine(self, routine_id: str, profile_id: str, event_context: Dict[str, Any]):
        routine = self.store.get_routine(routine_id)
        if not routine:
            raise ValueError("Routine not found")

        # Resolve profile fields into inputs
        resolved_inputs = self.profiles.resolve_fields(profile_id, routine.required_profile_fields)
        resolved_inputs.update(event_context)

        run_id = str(uuid.uuid4())
        run_state = RunState(
            run_id=run_id,
            routine_id=routine_id,
            inputs=resolved_inputs,
            trigger_context=event_context
        )

        return self.execute_routine(run_state, profile_id)

    def execute_routine(self, run_state: RunState, profile_id: str):
        """Executes a routine using a specific run state."""
        routine = self.store.get_routine(run_state.routine_id)
        if not routine:
            raise ValueError("Routine not found")
        
        return self.runner.execute(run_state, routine, profile_id)
