import uuid
import hashlib
import json
from datetime import datetime
from typing import Any, Dict, Optional
from routine_schema import Routine, RunState, RoutineStatus, RoutineStep
from town_store import TownStore
from action_registry import action_registry

class RoutineRunner:
    def __init__(self, store: TownStore):
        self.store = store

    def _calculate_memory_hash(self, profile_id: str) -> str:
        profile = self.store.get_profile(profile_id) or {}
        dump = json.dumps(profile, sort_keys=True)
        return hashlib.sha256(dump.encode()).hexdigest()

    def execute(self, run_state: RunState, routine: Routine, profile_id: str):
        run_state.status = RoutineStatus.RUNNING
        run_state.memory_snapshot_hash = self._calculate_memory_hash(profile_id)
        
        for step in routine.steps:
            if step.step_id in run_state.step_results:
                continue # Cache hit
            
            if step.requires_approval:
                run_state.status = RoutineStatus.AWAITING_APPROVAL
                self.store.save_run(run_state.run_id, run_state.dict())
                return {"status": "paused", "step": step.step_id}

            # Resolve template variables in params
            resolved_params = {}
            for k, v in step.params.items():
                if isinstance(v, str) and v.startswith("{{") and v.endswith("}}"):
                    var_name = v[2:-2]
                    resolved_params[k] = run_state.inputs.get(var_name, v)
                else:
                    resolved_params[k] = v

            # Execute real action from registry
            result = self._perform_action(step.action, resolved_params, run_state.inputs)
            run_state.step_results[step.step_id] = result
            
        run_state.status = RoutineStatus.COMPLETED
        run_state.end_time = datetime.now()
        self.store.save_run(run_state.run_id, run_state.dict())
        return {"status": "success", "results": run_state.step_results}

    def _perform_action(self, action: str, params: dict, inputs: dict) -> Any:
        return action_registry.execute(action, params, inputs)
