from app.scoring import ConfidenceScorer


def test_low_confidence_when_rag_and_guardrails_fail():
    scorer = ConfidenceScorer()
    metadata = {
        'rag': {
            'max_similarity': 0.18,
            'bm25_score': 5.0,
            'sources': 0,
            'recency_days': 500,
            'consistency': 0.2,
        },
        'llm': {
            'json_valid': False,
            'completeness': 0.3,
            'business_rules': {
                'thit_kho_tau_has_pork': False,
            },
            'self_contradiction': True,
        },
        'guardrails': {
            'action': 'safe-completion',
            'violations': [{'severity': 'high'}],
        },
        'entity_resolution': {
            'match_ratio': 0.4,
            'unresolved_entities': ['mystery ingredient'],
        },
        'domain': {
            'food_safety_alert': True,
        },
    }

    result = scorer.score(metadata)
    assert result.score < 25
    assert any('Guardrail' in msg for msg in result.penalties)
    assert any('JSON' in msg for msg in result.penalties)


def test_high_confidence_with_strong_signals():
    scorer = ConfidenceScorer()
    metadata = {
        'rag': {
            'max_similarity': 0.92,
            'bm25_score': 65.0,
            'sources': 4,
            'recency_days': 12,
            'consistency': 0.95,
        },
        'llm': {
            'json_valid': True,
            'completeness': 0.95,
            'business_rules': {
                'thit_kho_tau_has_pork': True,
                'has_caramelized_sauce': True,
            },
            'self_contradiction': False,
        },
        'entity_resolution': {
            'match_ratio': 0.92,
        },
        'guardrails': {
            'action': 'allow',
            'violations': [],
        },
        'domain': {
            'food_safety_alert': False,
            'allergen_alert': False,
        },
    }

    result = scorer.score(metadata)
    assert result.score > 80
    assert result.breakdown['rag'] > 30
    assert not result.penalties


def test_domain_penalties_reduce_score():
    scorer = ConfidenceScorer()
    metadata = {
        'rag': {'max_similarity': 0.6, 'bm25_score': 25.0, 'sources': 2, 'consistency': 0.6},
        'llm': {'json_valid': True, 'completeness': 0.7},
        'entity_resolution': {'match_ratio': 0.75},
        'guardrails': {'action': 'allow', 'violations': []},
        'domain': {'allergen_alert': True, 'nutrition_warning': True},
    }

    result = scorer.score(metadata)
    assert result.score < 60
    assert any('dị ứng' in msg or 'dinh dưỡng' in msg for msg in result.penalties)