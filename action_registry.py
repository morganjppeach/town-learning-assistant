import logging
from typing import Any, Dict, Callable

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ActionRegistry")

class ActionRegistry:
    """
    The Action Registry is the execution core of the Town Learning Assistant.
    It maps abstract action names (used in routine steps) to actual Python implementations.
    """
    def __init__(self):
        self._actions: Dict[str, Callable] = {}
        self._register_defaults()

    def register(self, name: str, func: Callable):
        """Registers a new action handler."""
        logger.info(f"Registering action: {name}")
        self._actions[name] = func

    def execute(self, action_name: str, params: Dict[str, Any], inputs: Dict[str, Any]) -> Any:
        """Executes a registered action by name."""
        if action_name not in self._actions:
            logger.error(f"Action '{action_name}' not found in registry.")
            raise ValueError(f"Unsupported action: {action_name}")
        
        logger.info(f"Executing action: {action_name} | Params: {params} | Inputs: {inputs}")
        return self._actions[action_name](params, inputs)

    def _register_defaults(self):
        """Initializes the system with core 'Gold Standard' action implementations."""
        # Utility actions
        self.register("fetch", self._fetch_impl)
        self.register("format", self._format_impl)
        
        # --- RESEARCH ACTIONS ---
        self.register("web_search", self._web_search_impl)
        self.register("summarize_content", self._summarize_impl)
        self.register("format_brief", self._format_brief_impl)

        # --- EXECUTIVE ACTIONS ---
        self.register("fetch_calendar", self._fetch_calendar_impl)
        self.register("fetch_emails", self._fetch_emails_impl)
        self.register("synthesize_briefing", self._synthesize_briefing_impl)

        # --- STRATEGIC ACTIONS ---
        self.register("analyze_event", self._analyze_event_impl)
        self.register("check_alignment", self._check_alignment_impl)
        self.register("notify_executive", self._notify_executive_impl)

    def _fetch_impl(self, params, inputs):
        return f"Fetched data for {params.get('url', 'default resource')}"

    def _format_impl(self, params, inputs):
        return f"Formatted content using style {params.get('style', 'default')}"

    # --- Implementations (Simulated but structured for real integration) ---

    def _web_search_impl(self, params, inputs):
        query = params.get("query") or inputs.get("topic")
        return {"results": [f"Found key info about {query} from Source A", f"Insight on {query} from Source B"]}

    def _summarize_impl(self, params, inputs):
        # In production, this calls an LLM
        content = inputs.get("results", "No content provided")
        return f"Summary of content: {content} synthesized into high-level takeaways."

    def _format_brief_impl(self, params, inputs):
        summary = inputs.get("summary", "No summary available")
        return f"--- RESEARCH BRIEF ---\\n{summary}\\n--- END BRIEF ---"

    def _fetch_calendar_impl(self, params, inputs):
        return {"events": ["10:00 AM: Board Meeting", "2:00 PM: Product Review"]}

    def _fetch_emails_impl(self, params, inputs):
        return {"emails": ["From: CEO - Urgent Strategy Update", "From: Ops - Weekly Report"]}

    def _synthesize_briefing_impl(self, params, inputs):
        events = inputs.get("events", [])
        emails = inputs.get("emails", [])
        return f"Good morning. You have {len(events)} events and {len(emails)} priority emails today."

    def _analyze_event_impl(self, params, inputs):
        event_data = inputs.get("event_payload", {})
        return {"analysis": f"Analyzed event: {event_data.get('event_type', 'unknown')}. Priority: High."}

    def _check_alignment_impl(self, params, inputs):
        analysis = inputs.get("analysis", "")
        profile = inputs.get("user_profile", {})
        goals = profile.get("goals", "general excellence")
        return {"aligned": True, "score": 0.9, "reason": f"Event aligns with goals: {goals}"}

    def _notify_executive_impl(self, params, inputs):
        reason = inputs.get("reason", "Strategic alignment detected")
        return f"NOTIFICATION SENT: High-priority opportunity detected. Reason: {reason}"

# Singleton instance for system-wide use
action_registry = ActionRegistry()
