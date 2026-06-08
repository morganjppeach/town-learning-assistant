import json
import os
from typing import List, Optional
from routine_schema import Routine

class TownStore:
    def __init__(self, storage_path: str = "town_data.json"):
        self.storage_path = storage_path
        self._data = self._load()

    def _load(self):
        if os.path.exists(self.storage_path):
            with open(self.storage_path, "r") as f:
                return json.load(f)
        return {"profiles": {}, "routines": {}, "runs": {}}

    def save(self):
        with open(self.storage_path, "w") as f:
            json.dump(self._data, f, indent=2)

    def save_profile(self, profile_id: str, data: dict):
        self._data["profiles"][profile_id] = data
        self.save()

    def get_profile(self, profile_id: str) -> Optional[dict]:
        return self._data["profiles"].get(profile_id)

    def save_routine(self, routine: Routine):
        self._data["routines"][routine.routine_id] = routine.dict()
        self.save()

    def get_routine(self, routine_id: str) -> Optional[Routine]:
        data = self._data["routines"].get(routine_id)
        return Routine(**data) if data else None

    def load_all_routines(self) -> List[Routine]:
        return [Routine(**r) for r in self._data["routines"].values()]

    def save_run(self, run_id: str, state: dict):
        self._data["runs"][run_id] = state
        self.save()

    def get_run(self, run_id: str) -> Optional[dict]:
        return self._data["runs"].get(run_id)
