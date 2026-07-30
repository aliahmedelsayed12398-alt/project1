def schedule_call(customer_id: str, time_slot: str) -> dict:
    return {"customer_id": customer_id, "time_slot": time_slot, "status": "scheduled"}
