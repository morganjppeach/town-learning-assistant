from routine_schema import Routine, RoutineStep
from town_store import TownStore
import json

def populate():
    store = TownStore()
    
    gold_routines = [
        Routine(
            routine_id="autonomous_research_brief",
            name="Autonomous Research Brief",
            description="Performs deep research on a topic and produces a synthesized brief.",
            steps=[
                RoutineStep(step_id="search", action="web_search", params={"query": "{{topic}}"}, description="Search the web for relevant information on the topic.", requires_approval=False),
                RoutineStep(step_id="summarize", action="summarize_content", params={}, description="Summarize the search results into key takeaways.", requires_approval=False),
                RoutineStep(step_id="format", action="format_brief", params={}, description="Format the summary into a professional research brief.", requires_approval=False),
            ],
            required_profile_fields=["research_preferences"]
        ),
        Routine(
            routine_id="executive_daily_briefing",
            name="Executive Daily Briefing",
            description="Aggregates calendar and emails into a concise morning briefing.",
            steps=[
                RoutineStep(step_id="cal", action="fetch_calendar", params={}, description="Retrieve today's calendar events.", requires_approval=False),
                RoutineStep(step_id="mail", action="fetch_emails", params={}, description="Retrieve priority emails from the inbox.", requires_approval=False),
                RoutineStep(step_id="synth", action="synthesize_briefing", params={}, description="Synthesize events and emails into a concise daily briefing.", requires_approval=False),
            ],
            required_profile_fields=["briefing_style"]
        ),
        Routine(
            routine_id="strategic_opportunity_monitor",
            name="Strategic Opportunity Monitor",
            description="Analyzes external events for strategic alignment and notifies the executive.",
            steps=[
                RoutineStep(step_id="analyze", action="analyze_event", params={}, description="Analyze the incoming external event payload.", requires_approval=False),
                RoutineStep(step_id="align", action="check_alignment", params={}, description="Check the event analysis against the user's strategic goals.", requires_approval=False),
                RoutineStep(step_id="notify", action="notify_executive", params={}, description="Notify the executive of the high-alignment opportunity.", requires_approval=True), 
            ],
            required_profile_fields=["strategic_goals"]
        )
    ]

    for routine in gold_routines:
        store.save_routine(routine)
        print(f"Saved Gold Routine: {routine.name}")

if __name__ == "__main__":
    populate()
