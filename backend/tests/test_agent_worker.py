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


def test_relevance_weights_entities_numbers_and_phrases():
    worker = AgentWorker(emit=None, scoring=ScoringEngine())
    relevance = worker._claim_relevance(
        "JPMorgan files lawsuit against Tesla for $162M over a 2014 stock warrant dispute",
        "Reuters reported JPMorgan sued Tesla over a 2014 stock warrant dispute worth $162 million.",
    )
    assert relevance >= 70


def test_heuristic_marks_reputable_direct_report_as_supporting():
    worker = AgentWorker(emit=None, scoring=ScoringEngine())
    score = worker.scoring.score_source(
        "reuters.com",
        "JPMorgan sues Tesla",
        "according to court documents and company filings " + "x" * 900,
    )
    stance = worker._heuristic_stance(
        "JPMorgan files lawsuit against Tesla for $162M over a 2014 stock warrant dispute",
        "JPMorgan sues Tesla over stock warrant dispute",
        "Reuters reported JPMorgan sued Tesla over the dispute.",
        "according to court documents and company filings",
        score,
        72,
        {"stance_bias": "support"},
    )
    assert stance == "supports"


def test_heuristic_refutes_wrong_office_holder_claim_from_official_source():
    worker = AgentWorker(emit=None, scoring=ScoringEngine())
    score = worker.scoring.score_source(
        "presidentofindia.gov.in",
        "President of India",
        "The current President of India is Smt. Droupadi Murmu. " + "x" * 900,
    )
    stance = worker._heuristic_stance(
        "Trump is the president of India in 2026",
        "President of India",
        "Droupadi Murmu is the current President of India.",
        "The official website of the President of India lists Droupadi Murmu as the current office holder.",
        score,
        72,
        {"stance_bias": "refute"},
    )
    assert stance == "refutes"
