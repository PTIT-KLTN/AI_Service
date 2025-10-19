from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple


@dataclass
class ConfidenceBreakdown:
    score: float
    breakdown: Dict[str, float]
    penalties: List[str]


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


class ConfidenceScorer:
    """Aggregate heterogeneous quality signals into a 0–100 confidence score."""

    def __init__(self) -> None:
        self.base_score = 5.0

    def score(self, metadata: Dict[str, Any]) -> ConfidenceBreakdown:
        penalties: List[str] = []

        rag_score, rag_penalties = self._score_rag(metadata.get('rag', {}))
        penalties.extend(rag_penalties)

        llm_score, llm_penalties = self._score_llm(metadata.get('llm', {}))
        penalties.extend(llm_penalties)

        entity_score, entity_penalties = self._score_entity_resolution(metadata.get('entity_resolution', {}))
        penalties.extend(entity_penalties)

        guardrail_penalty, guardrail_notes = self._penalize_guardrails(metadata.get('guardrails', {}))
        penalties.extend(guardrail_notes)

        domain_penalty, domain_notes = self._penalize_domain(metadata.get('domain', {}))
        penalties.extend(domain_notes)

        total = rag_score + llm_score + entity_score + self.base_score
        total -= guardrail_penalty + domain_penalty
        total = _clamp(total, 0.0, 100.0)

        breakdown = {
            'rag': round(rag_score, 2),
            'llm': round(llm_score, 2),
            'entity_resolution': round(entity_score, 2),
            'base': round(self.base_score, 2),
            'guardrail_penalty': round(guardrail_penalty, 2),
            'domain_penalty': round(domain_penalty, 2),
        }

        return ConfidenceBreakdown(score=round(total, 2), breakdown=breakdown, penalties=penalties)

    # ---------------------------- RAG -----------------------------

    def _score_rag(self, rag_meta: Dict[str, Any]) -> Tuple[float, List[str]]:
        penalties: List[str] = []
        similarity = float(rag_meta.get('max_similarity', 0.0) or 0.0)
        similarity_component = _clamp(similarity, 0.0, 1.0) * 20.0

        bm25 = rag_meta.get('bm25_score') or rag_meta.get('bm25') or 0.0
        bm25_component = _clamp(float(bm25) / 60.0, 0.0, 1.0) * 5.0

        sources = int(rag_meta.get('sources', 0) or 0)
        if sources >= 3:
            sources_component = 8.0
        elif sources == 2:
            sources_component = 6.0
        elif sources == 1:
            sources_component = 4.0
        else:
            sources_component = 0.0
            penalties.append('RAG không cung cấp nguồn tham khảo đáng tin cậy.')

        recency_days = rag_meta.get('recency_days')
        if recency_days is None and rag_meta.get('latest_source_date'):
            try:
                latest = datetime.fromisoformat(str(rag_meta['latest_source_date']).replace('Z', '+00:00'))
                recency_days = (datetime.now(timezone.utc) - latest).days
            except ValueError:
                recency_days = None
        if recency_days is None:
            recency_component = 2.5
        else:
            recency_days = max(0, float(recency_days))
            if recency_days <= 30:
                recency_component = 5.0
            elif recency_days <= 90:
                recency_component = 4.0
            elif recency_days <= 180:
                recency_component = 3.0
            elif recency_days <= 365:
                recency_component = 1.5
            else:
                recency_component = 0.5
                penalties.append('Nguồn tham khảo quá cũ (>1 năm).')

        consistency = float(rag_meta.get('consistency', 1.0) or 0.0)
        consistency_component = _clamp(consistency, 0.0, 1.0) * 5.0
        if consistency_component < 2.5:
            penalties.append('Các nguồn RAG thiếu nhất quán.')

        rag_score = similarity_component + bm25_component + sources_component + recency_component + consistency_component
        return _clamp(rag_score, 0.0, 40.0), penalties

    # ---------------------------- LLM -----------------------------

    def _score_llm(self, llm_meta: Dict[str, Any]) -> Tuple[float, List[str]]:
        penalties: List[str] = []
        json_valid = bool(llm_meta.get('json_valid', False))
        json_component = 12.0 if json_valid else 0.0
        if not json_valid:
            penalties.append('JSON trả về không hợp lệ theo schema.')

        completeness = llm_meta.get('completeness', 0.0) or 0.0
        completeness_component = _clamp(float(completeness), 0.0, 1.0) * 8.0
        if completeness_component < 4.0:
            penalties.append('Thông tin trả về thiếu nhiều trường bắt buộc.')

        business_rules = llm_meta.get('business_rules', {}) or {}
        if isinstance(business_rules, dict) and business_rules:
            passed = sum(1 for value in business_rules.values() if value)
            total = len(business_rules)
            business_component = (passed / total) * 6.0
            if passed < total:
                failed = [name for name, ok in business_rules.items() if not ok]
                penalties.append(f"Vi phạm quy tắc nghiệp vụ: {', '.join(failed)}")
        else:
            business_component = 4.0  # assume neutral when no rules supplied

        if llm_meta.get('self_contradiction'):
            penalties.append('Phát hiện mô hình tự mâu thuẫn trong câu trả lời.')
            contradiction_penalty = 6.0
        else:
            contradiction_penalty = 0.0

        llm_score = json_component + completeness_component + business_component - contradiction_penalty
        return _clamp(llm_score, 0.0, 30.0), penalties

    # ------------------------ Entity Resolution -------------------

    def _score_entity_resolution(self, entity_meta: Dict[str, Any]) -> Tuple[float, List[str]]:
        penalties: List[str] = []
        match_ratio = entity_meta.get('match_ratio')
        if match_ratio is None:
            return 8.0, penalties  # default moderate confidence
        ratio = _clamp(float(match_ratio), 0.0, 1.0)
        entity_score = ratio * 15.0
        if ratio < 0.7:
            penalties.append('Ontology map có nhiều nguyên liệu không khớp.')
        if entity_meta.get('unresolved_entities'):
            penalties.append('Một số nguyên liệu không map được ontology.')
            entity_score -= 3.0
        return _clamp(entity_score, 0.0, 15.0), penalties

    # -------------------------- Guardrails ------------------------

    def _penalize_guardrails(self, guard_meta: Dict[str, Any]) -> Tuple[float, List[str]]:
        if not guard_meta:
            return 0.0, []
        penalties: List[str] = []
        action = (guard_meta.get('action') or 'allow').lower()
        action_penalty_map = {
            'block': 30.0,
            'safe-completion': 25.0,
            'redact': 15.0,
            'allow': 0.0,
        }
        penalty = action_penalty_map.get(action, 20.0)

        violations = guard_meta.get('violations') or []
        severity_penalty = 0.0
        severity_map = {'high': 8.0, 'medium': 5.0, 'low': 2.0}
        for violation in violations:
            severity = (violation.get('severity') or 'medium').lower()
            severity_penalty += severity_map.get(severity, 4.0)
        penalty = max(penalty, severity_penalty)

        if penalty > 0:
            penalties.append('Guardrail kích hoạt do vi phạm chính sách an toàn.')
        return penalty, penalties

    # ---------------------------- Domain --------------------------

    def _penalize_domain(self, domain_meta: Dict[str, Any]) -> Tuple[float, List[str]]:
        penalty = 0.0
        penalties: List[str] = []
        if domain_meta.get('food_safety_alert'):
            penalty += 15.0
            penalties.append('Cảnh báo an toàn thực phẩm cần được xử lý.')
        if domain_meta.get('allergen_alert'):
            penalty += 12.0
            penalties.append('Có nguy cơ dị ứng trong gợi ý.')
        if domain_meta.get('nutrition_warning'):
            penalty += 8.0
            penalties.append('Câu trả lời liên quan đến dinh dưỡng nhạy cảm.')
        return penalty, penalties