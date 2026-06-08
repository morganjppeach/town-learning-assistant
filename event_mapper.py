from typing import Dict, Any

class ZapierEventMapper:
    @staticmethod
    def map_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
        # Normalizes various Zapier formats into a flat dictionary
        normalized = {}
        if "data" in payload:
            normalized.update(payload["data"])
        else:
            normalized.update(payload)
        
        # Ensure key fields are extracted
        normalized["event_type"] = payload.get("event_type", "generic_zap")
        return normalized
