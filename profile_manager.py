from typing import Any, Dict, Optional
from town_store import TownStore

class ProfileManager:
    def __init__(self, store: TownStore):
        self.store = store

    def update_preference(self, profile_id: str, key: str, value: Any):
        profile = self.store.get_profile(profile_id) or {}
        profile[key] = value
        self.store.save_profile(profile_id, profile)

    def get_preference(self, profile_id: str, key: str, default: Any = None) -> Any:
        profile = self.store.get_profile(profile_id)
        return profile.get(key, default) if profile else default

    def resolve_fields(self, profile_id: str, fields: list) -> Dict[str, Any]:
        profile = self.store.get_profile(profile_id) or {}
        return {f: profile.get(f) for f in fields if f in profile}
