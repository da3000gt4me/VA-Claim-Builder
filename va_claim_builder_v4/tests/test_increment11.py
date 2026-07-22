from core.analysis.unclaimed_conditions import PotentialClaimDiscoveryEngine

def test_requires_current_and_service_anchor():
    e=PotentialClaimDiscoveryEngine()
    r=e.discover([],[],[{"finding":"Diagnosed lumbar spondylosis"}])
    assert not r["candidates"]

def test_discovers_affirmative_not_negated_condition():
    e=PotentialClaimDiscoveryEngine()
    r=e.discover([], [{"description":"Carried heavy equipment and waterlogged logs over mountainous terrain"}], [{"finding":"Lumbar spondylosis with chronic low back pain"}])
    assert any(x["condition"]=="Lumbar spine condition" for x in r["candidates"])
    assert "Would you like me to build" in r["prompt"]

def test_negated_current_finding_is_excluded():
    e=PotentialClaimDiscoveryEngine()
    r=e.discover([], [{"description":"Heavy lifting during service"}], [{"finding":"No evidence of lumbar disorder; denies back pain"}])
    assert not any(x["condition"]=="Lumbar spine condition" for x in r["candidates"])

def test_existing_claim_is_not_recommended_again():
    e=PotentialClaimDiscoveryEngine()
    r=e.discover([{"condition_name":"Lumbar spine strain"}], [{"description":"Heavy lifting"}], [{"finding":"Lumbar spondylosis"}])
    assert not any(x["condition"]=="Lumbar spine condition" for x in r["candidates"])
