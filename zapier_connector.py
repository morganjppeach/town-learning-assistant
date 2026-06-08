from fastapi import FastAPI, BackgroundTasks, HTTPException, Header
from typing import Dict, Any
from trigger_manager import TriggerManager
from town_brain import TownBrain
from town_store import TownStore

app = FastAPI()
store = TownStore()
brain = TownBrain(store)
trigger_mgr = TriggerManager(brain, store)

SECRET_TOKENS = {"test-token-123": "jp_user_1"}

@app.post("/hooks/zapier/{token}")
async def zapier_webhook(token: str, payload: Dict[str, Any], background_tasks: BackgroundTasks):
    if token not in SECRET_TOKENS:
        raise HTTPException(status_code=403, detail="Invalid token")
    
    profile_id = SECRET_TOKENS[token]
    
    # Normalize payload via simple mapping
    event_type = payload.get("event_type", "zapier_trigger")
    event_data = payload.get("data", payload)
    
    # Run the routine in the background
    background_tasks.add_task(trigger_mgr.process_event, event_type, event_data, profile_id)
    
    return {"status": "accepted", "message": "Event queued for processing"}
