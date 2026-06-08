from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
from enum import Enum
from datetime import datetime

class RoutineStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    AWAITING_APPROVAL = "awaiting_approval"

class TriggerCondition(BaseModel):
    field: str
    operator: str  # "eq", "contains", "gt", "lt"
    value: Any

class RoutineTrigger(BaseModel):
    event_name: str
    conditions: List[TriggerCondition] = []

class RoutineStep(BaseModel):
    step_id: str
    description: str
    action: str
    params: Dict[str, Any] = {}
    requires_approval: bool = False

class Routine(BaseModel):
    routine_id: str
    name: str
    description: str
    trigger: Optional[RoutineTrigger] = None
    required_profile_fields: List[str] = []
    steps: List[RoutineStep]
    version: str = "1.0.0"

class RunState(BaseModel):
    run_id: str
    routine_id: str
    status: RoutineStatus = RoutineStatus.PENDING
    inputs: Dict[str, Any] = {}
    trigger_context: Dict[str, Any] = {}
    step_results: Dict[str, Any] = {}
    start_time: datetime = Field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    memory_snapshot_hash: str = ""
