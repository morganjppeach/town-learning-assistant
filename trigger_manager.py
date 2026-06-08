from typing import Any, Dict, List, Optional
from routine_schema import Routine, RoutineTrigger, TriggerCondition
from town_brain import TownBrain

class TriggerManager:
    def __init__(self, brain: TownBrain, store):
        self.brain = brain
        self.store = store

    def process_event(self, event_name: str, event_data: Dict[str, Any], profile_id: str):
        routines = self.store.load_all_routines()
        triggered = []

        for routine in routines:
            if routine.trigger and routine.trigger.event_name == event_name:
                if self._evaluate_conditions(routine.trigger.conditions, event_data):
                    # Trigger the routine via the brain
                    result = self.brain.trigger_routine(routine.routine_id, profile_id, event_data)
                    triggered.append({"routine_id": routine.routine_id, "result": result})
        
        return triggered

    def _evaluate_conditions(self, conditions: List[TriggerCondition], data: Dict[str, Any]) -> bool:
        for cond in conditions:
            val = data.get(cond.field)
            if cond.operator == "eq" and val != cond.value: return False
            if cond.operator == "contains" and (not val or cond.value not in val): return False
            if cond.operator == "gt" and (val is None or val <= cond.value): return False
            if cond.operator == "lt" and (val is None or val >= cond.value): return False
        return True
