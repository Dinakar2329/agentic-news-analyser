from app.agents.worker import AgentWorker
from app.scoring.engine import ScoringEngine


def test_parse_model_stance_response_from_json_block():
    worker = AgentWorker(emit=None, scoring=ScoringEngine())
    parsed = worker._parse_stance_response(
        '```json\n{"stance":"refutes","reason":"The source says no evidence exists.","summary":"The claim is denied."}\n```'
    )
    assert parsed["stance"] == "refutes"
    assert parsed["source"] == "model"


def test_parse_model_stance_rejects_unknown_stance():
    worker = AgentWorker(emit=None, scoring=ScoringEngine())
    assert worker._parse_stance_response('{"stance":"maybe","reason":"x"}') is None
