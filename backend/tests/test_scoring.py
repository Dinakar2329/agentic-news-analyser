from app.scoring.engine import ScoringEngine


def test_official_source_scores_above_social_source():
    engine = ScoringEngine()
    official = engine.score_source("sec.gov", "SEC filing", "x" * 1200)
    social = engine.score_source("twitter.com", "viral post", "x" * 80)
    assert official.reliability_score > social.reliability_score
    assert official.official_badge is True


def test_verdict_with_no_sources_is_unverified():
    verdict = ScoringEngine().aggregate_verdict([], 0)
    assert verdict["verdict"] == "UNVERIFIED"


def test_reliable_but_irrelevant_sources_do_not_become_true():
    engine = ScoringEngine()
    score = engine.score_source("reuters.com", "Market update", "general news")
    score.relevance_score = 10
    verdict = engine.aggregate_verdict([score], 0)
    assert verdict["verdict"] == "UNVERIFIED"


def test_multiple_reliable_supporting_sources_can_be_true():
    engine = ScoringEngine()
    scores = [
        engine.score_source("sec.gov", "SEC filing", "filing document according to court statement " + "x" * 1200),
        engine.score_source("reuters.com", "Reuters confirmed", "according to source statement data " + "x" * 1200),
        engine.score_source("apnews.com", "AP confirmed", "according to filing statement data " + "x" * 1200),
    ]
    for score in scores:
        score.relevance_score = 95
    verdict = engine.aggregate_verdict(scores, 0, {"supports": 3})
    assert verdict["verdict"] == "TRUE"


def test_reliable_refuting_sources_can_be_false():
    engine = ScoringEngine()
    scores = [
        engine.score_source("reuters.com", "Reuters debunked", "no evidence false denied " + "x" * 1200),
        engine.score_source("apnews.com", "AP fact check", "false fake debunked " + "x" * 1200),
    ]
    for score in scores:
        score.relevance_score = 90
    verdict = engine.aggregate_verdict(scores, 2, {"refutes": 2})
    assert verdict["verdict"] == "FALSE"
