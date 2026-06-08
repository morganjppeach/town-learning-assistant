import unittest
from town_store import TownStore
from profile_manager import ProfileManager
from routine_schema import Routine, RoutineStep, RoutineTrigger, TriggerCondition
from town_brain import TownBrain
from trigger_manager import TriggerManager

class TestTownApp(unittest.TestCase):
    def setUp(self):
        self.store = TownStore("test_data.json")
        self.brain = TownBrain(self.store)
        self.trigger_mgr = TriggerManager(self.brain, self.store)
        self.profile_id = "test_user"

    def test_full_flow(self):
        # 1. Setup Profile
        self.brain.profiles.update_preference(self.profile_id, "tone", "concise")
        
        # 2. Setup Routine
        routine = Routine(
            routine_id="briefing",
            name="Daily Briefing",
            description="Sends a concise briefing",
            required_profile_fields=["tone"],
            trigger=RoutineTrigger(
                event_name="daily_trigger",
                conditions=[TriggerCondition(field="hour", operator="eq", value=9)]
            ),
            steps=[
                RoutineStep(step_id="s1", description="Fetch data", action="fetch", params={}),
                RoutineStep(step_id="s2", description="Format", action="format", params={})
            ]
        )
        self.store.save_routine(routine)
        
        # 3. Trigger Event
        event_data = {"hour": 9, "date": "2026-06-08"}
        results = self.trigger_mgr.process_event("daily_trigger", event_data, self.profile_id)
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["routine_id"], "briefing")
        self.assertEqual(results[0]["result"]["status"], "success")

if __name__ == "__main__":
    unittest.main()
