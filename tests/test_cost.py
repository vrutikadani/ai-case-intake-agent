from case_intake.cost import UnitCosts, Volumes, monthly_cost

V = Volumes(emails=3000, routine_share=0.6, case_share=0.15)
C = UnitCosts(filter_cost=0.0, inference_cost=0.01, workflow_cost=0.02, review_cost=0.5)


def test_prefilter_cuts_model_calls_by_the_routine_share():
    gated = monthly_cost(V, C)
    ungated = monthly_cost(V, C, prefilter=False)
    assert gated["model_events"] == 1200 and ungated["model_events"] == 3000


def test_ungated_writes_produce_bad_writes():
    assert monthly_cost(V, C, gate_writes=False)["bad_writes"] > 0
    assert monthly_cost(V, C)["bad_writes"] == 0
