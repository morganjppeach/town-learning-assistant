import unittest
from town_brain import TownBrain
from town_store import TownStore
from routine_schema import RunState, RoutineStatus
from action_registry import action_registry

class TestGoldRoutines(unittest.TestCase):
    def setUp(self):
        self.store = TownStore()
        self.brain = TownBrain(self.store)
        
        # Setup a test profile
        self.profile_id = "test_user"
        self.store.save_profile(self.profile_id, {
            "id": self.profile_id,
            "name": "JP",
            "research_preferences": "High-detail, academic sources",
            "briefing_style": "Concise, bullet-points",
            "strategic_goals": "Expand AI infrastructure and automate executive workflows"
        })

    def test_autonomous_research_flow(self):
        routine = self.store.get_routine("autonomous_research_brief")
        inputs = {"topic": "Quantum Computing in 2026"}
        
        run_state = RunState(run_id="res_001", routine_id=routine.routine_id, inputs=inputs)
        result = self.brain.execute_routine(run_state, self.profile_id)
        
        self.assertEqual(result["status"], "success")
        self.assertIn("RESEARCH BRIEF", result["results"]["format"])
        self.assertTrue(any("Quantum Computing" in str(v) for v in result["results"].values()))

    def test_executive_briefing_flow(self):
        routine = self.store.get_routine("executive_daily_briefing")
        inputs = {}
        
        run_state = RunState(run_id="exec_001", routine_id=routine.routine_id, inputs=inputs)
        result = self.brain.execute_routine(run_state, self.profile_id)
        
        self.assertEqual(result["status"], "success")
        self.assertIn("Good morning", result["results"]["synth"])
        self.assertTrue(len(result["results"]["cal"]["events"]) > 0)

    def test_strategic_monitor_approval_gate(self):
        routine = self.store.get_routine("strategic_opportunity_monitor")
        inputs = {"event_payload": {"event_type": "new_partnership_request", "detail": "AI chip supply"}}
        
        run_state = RunState(run_id="strat_001", routine_id=routine.routine_id, inputs=inputs)
        result = self.brain.execute_routine(run_state, self.profile_id)
        
        # Should be paused at the 'notify' step
        self.assertEqual(result["status"], "paused")
        self.assertEqual(result["step"], "notify")
        
        # Verify state in store
        saved_run = self.store.get_run("strat_001")
        self.assertEqual(saved_run["status"], RoutineStatus.AWAITING_APPROVAL)

if __name__ == "__main__":
    unittest.main()
