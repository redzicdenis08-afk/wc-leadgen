# Lead Routing Demo
def route_lead(score: int) -> str:
    if score >= 80:
        return "immediate_callback"
    elif score >= 50:
        return "sequence_outreach"
    return "suppressed"
