from examples.lead_routing_demo import route_lead

def test_route_lead():
    assert route_lead(85) == "immediate_callback"
    assert route_lead(30) == "suppressed"
