# Gold Standard Routines Catalog

This catalog defines the high-value autonomous workflows implemented in the Town Learning Assistant.

## 1. Autonomous Research Brief
- **Goal**: Transform a broad topic into a structured professional brief.
- **Workflow**:
  1. `web_search`: Gathers multi-source data on the topic.
  2. `summarize_content`: Synthesizes raw data into key takeaways.
  3. `format_brief`: Applies executive formatting.
- **Trigger**: User request or strategic keyword.

## 2. Executive Daily Briefing
- **Goal**: Provide a synthesized morning agenda.
- **Workflow**:
  1. `fetch_calendar`: Pulls today's appointments.
  2. `fetch_emails`: Pulls priority inbox items.
  3. `synthesize_briefing`: Combines both into a natural language greeting.
- **Trigger**: Time-based (e.g., 7:00 AM) or "Good Morning" trigger.

## 3. Strategic Opportunity Monitor
- **Goal**: Filter external events for high-strategic alignment.
- **Workflow**:
  1. `analyze_event`: Parses the incoming Zapier payload.
  2. `check_alignment`: Compares event data against User Profile goals.
  3. **APPROVAL GATE**: Pauses for Executive sign-off.
  4. `notify_executive`: Sends the final alert.
- **Trigger**: External Webhook (Zapier).
