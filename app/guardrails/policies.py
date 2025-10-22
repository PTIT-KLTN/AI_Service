from __future__ import annotations
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
import yaml

from app.utils.text_match import norm_text, unique

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

        # 1) Similarity: trọng số lớn nhất
        similarity = float(rag_meta.get('max_similarity', 0.0) or 0.0)
        SIM_W = 32.0
        similarity_component = _clamp(similarity, 0.0, 1.0) * SIM_W

        # 2) Consistency: ưu tiên dùng margin (top1 - top2). Fallback: dùng 'consistency' cũ.
        CONS_W = 8.0
        margin = None
        if 'sim_margin' in rag_meta:
            try:
                margin = float(rag_meta.get('sim_margin') or 0.0)
            except Exception:
                margin = None
        if margin is None:
            top2 = rag_meta.get('second_best_similarity') or rag_meta.get('top2_similarity')
            if top2 is not None:
                try:
                    margin = max(0.0, float(similarity) - float(top2))
                except Exception:
                    margin = None

        if margin is not None:
            norm = _clamp(margin / 0.15, 0.0, 1.0)
            consistency_component = norm * CONS_W
        else:
            consistency = float(rag_meta.get('consistency', 1.0) or 0.0)
            consistency_component = _clamp(consistency, 0.0, 1.0) * CONS_W

        # 3) Recency: luôn trung lập (không phạt/không thưởng theo thời gian)
        BASE_NEUTRAL = 2.5

        rag_score = similarity_component + consistency_component + BASE_NEUTRAL
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
            penalties.append('Có nguy cơ dị ứng trong gợi ý. Người dùng cần tự đánh giá mức độ chấp nhận.')
        if domain_meta.get('nutrition_warning'):
            penalty += 8.0
            penalties.append('Câu trả lời liên quan đến dinh dưỡng nhạy cảm.')
        return penalty, penalties


@dataclass
class GuardrailViolation:
    policy_id: str
    rule_id: str
    action: str
    severity: str
    message: str
    remediation: str
    matches: List[str] = field(default_factory=list)
    policy_name: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            'policy_id': self.policy_id,
            'rule_id': self.rule_id,
            'action': self.action,
            'severity': self.severity,
            'message': self.message,
            'remediation': self.remediation,
            'matches': list(self.matches),
        }
        if self.policy_name:
            payload['policy_name'] = self.policy_name
        if self.metadata:
            payload['metadata'] = self.metadata
        return payload


class GuardrailPolicyEvaluator:
    """Evaluate text against YAML guardrail policies and local keyword filters."""

    _SUSPICIOUS_CHARS = {'†', '‡', '※', '‧', '•'}
    _ALLERGY_TRIGGERS = {'dị ứng', 'di ung', 'allergy', 'allergic'}

    def __init__(
        self,
        policy_dir: Optional[str | Path] = None,
        keyword_file: Optional[str | Path] = None,
    ) -> None:
        self.policy_dir = Path(policy_dir or Path(__file__).parent)
        self.keyword_file = Path(keyword_file or (self.policy_dir / 'keywords_vi.json'))
        self._rules: List[Dict[str, Any]] = []
        self._keyword_bans: List[str] = []

        self._load_policies()
        self._load_keyword_filters()


    def evaluate(self, prompt_text: str, response_text: str) -> List[GuardrailViolation]:
        prompt_text = prompt_text or ''
        response_text = response_text or ''
        normalized_prompt = norm_text(prompt_text)
        normalized_response = norm_text(response_text)

        violations: List[GuardrailViolation] = []

        # Prompt injection & keyword bans
        violations.extend(self._detect_prompt_injection(normalized_prompt))

        # Unicode homoglyph probing to bypass regex filters
        violations.extend(self._detect_homoglyphs(prompt_text + response_text, normalized_response))

        for rule in self._rules:
            matches: List[str] = []
            if rule['type'] == 'regex':
                matches = self._match_regex(rule, prompt_text, response_text)
            elif rule['type'] == 'keyword':
                matches = self._match_keywords(rule, normalized_prompt, normalized_response)
            elif rule['type'] == 'allergy':
                matches = self._match_allergy(rule, normalized_prompt, normalized_response)
            else:
                continue

            if not matches:
                continue

            violation = GuardrailViolation(
                policy_id=rule['policy_id'],
                policy_name=rule.get('policy_name'),
                rule_id=rule['rule_id'],
                action=rule['action'],
                severity=rule['severity'],
                message=rule['message'],
                remediation=rule.get('remediation', ''),
                matches=unique(matches),
                metadata={
                    'sources': rule.get('sources', []),
                    'redaction': rule.get('redaction'),
                    'patterns': rule.get('raw_patterns', []),
                },
            )
            violations.append(violation)

        return violations


    def build_safe_completion(self, violations: Iterable[GuardrailViolation]) -> str:
        violations = list(violations)
        warnings: List[Dict[str, Any]] = []
        summary_parts: List[str] = []
        for violation in violations:
            warnings.append(
                {
                    'policy_id': violation.policy_id,
                    'rule_id': violation.rule_id,
                    'severity': violation.severity,
                    'message': violation.message,
                    'remediation': violation.remediation,
                }
            )
            name = violation.policy_name or violation.policy_id
            summary_parts.append(f"{name}: {violation.message}")

        summary = '; '.join(summary_parts) if summary_parts else 'Yêu cầu vi phạm chính sách.'
        response = (
            'Xin lỗi, tôi không thể hỗ trợ yêu cầu này vì vi phạm chính sách an toàn: '
            f'{summary}'
        )

        payload = {
            'dish_name': None,
            'ingredients': [],
            'response': response,
            'warnings': warnings,
            'violations': [violation.to_dict() for violation in violations],
        }
        return json.dumps(payload, ensure_ascii=False)


    def redact_text(self, raw_text: str, violations: Iterable[GuardrailViolation]) -> str:
        text = raw_text or ''
        violations = list(violations)
        for violation in violations:
            redaction = violation.metadata.get('redaction')
            if not redaction:
                continue
            for pattern in violation.metadata.get('patterns', []):
                try:
                    compiled = re.compile(pattern, re.IGNORECASE)
                except re.error:
                    continue
                text = compiled.sub(redaction, text)

        # Enrich JSON payloads with warnings when possible
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return text

        warning_entries = [
            {
                'policy_id': violation.policy_id,
                'rule_id': violation.rule_id,
                'severity': violation.severity,
                'message': violation.message,
                'remediation': violation.remediation,
            }
            for violation in violations
        ]

        existing = data.get('warnings')
        if isinstance(existing, list):
            existing.extend(warning_entries)
        else:
            data['warnings'] = warning_entries

        data.setdefault('response', 'Một số thông tin nhạy cảm đã được ẩn khỏi kết quả.')
        data.setdefault('violations', [violation.to_dict() for violation in violations])
        return json.dumps(data, ensure_ascii=False)


    def _load_policies(self) -> None:
        if not self.policy_dir.exists():
            return
        for path in sorted(self.policy_dir.glob('*_policy.yaml')):
            try:
                config = yaml.safe_load(path.read_text(encoding='utf-8'))
            except Exception:
                continue
            if not isinstance(config, dict):
                continue
            policy_id = config.get('policy_id')
            if not policy_id:
                continue
            policy_name = config.get('name')
            for rule in config.get('rules', []) or []:
                rule_id = rule.get('id')
                if not rule_id:
                    continue
                rule_type = (rule.get('type') or 'regex').lower()
                entry = {
                    'policy_id': policy_id,
                    'policy_name': policy_name,
                    'rule_id': rule_id,
                    'type': rule_type,
                    'action': (rule.get('action') or 'safe-completion').lower(),
                    'severity': (rule.get('severity') or 'medium').lower(),
                    'message': rule.get('message', ''),
                    'remediation': rule.get('remediation', ''),
                    'sources': rule.get('sources', []),
                    'redaction': rule.get('redaction'),
                    'raw_patterns': rule.get('patterns', []),
                    'allergens': [a for a in rule.get('allergens', []) if a],
                }
                if rule_type == 'regex':
                    patterns = []
                    for pattern in entry['raw_patterns']:
                        try:
                            patterns.append(re.compile(pattern, re.IGNORECASE))
                        except re.error:
                            continue
                    entry['compiled_patterns'] = patterns
                elif rule_type == 'keyword':
                    entry['keywords'] = [norm_text(k) for k in rule.get('keywords', []) if k]
                self._rules.append(entry)

    def _load_keyword_filters(self) -> None:
        if not self.keyword_file.exists():
            return
        try:
            payload = json.loads(self.keyword_file.read_text(encoding='utf-8'))
        except Exception:
            return
        banned = payload.get('banned_terms') if isinstance(payload, dict) else None
        if isinstance(banned, list):
            self._keyword_bans = [norm_text(term) for term in banned if term]

    # ------------------------------------------------------------------
    def _detect_prompt_injection(self, normalized_prompt: str) -> List[GuardrailViolation]:
        matches = [term for term in self._keyword_bans if term and term in normalized_prompt]
        if not matches:
            return []
        violation = GuardrailViolation(
            policy_id='prompt_injection',
            policy_name='Prompt Injection Filter',
            rule_id='keyword-filter',
            action='safe-completion',
            severity='high',
            message='Phát hiện từ khóa nghi ngờ prompt injection.',
            remediation='Từ chối và giữ nguyên ràng buộc an toàn.',
            matches=unique(matches),
        )
        return [violation]

    def _detect_homoglyphs(self, text: str, normalized: str) -> List[GuardrailViolation]:
        suspicious = [char for char in self._SUSPICIOUS_CHARS if char in text]
        if not suspicious:
            return []
        # Sau khi loại ký tự lạ, kiểm tra cụm liên quan an toàn thực phẩm
        simplified = text
        for char in suspicious:
            simplified = simplified.replace(char, '')
        simplified_norm = norm_text(simplified)
        danger_keywords = [
            'ngoai tu lanh',
            'nhiet do phong',
            'thit song',
            'uop thit',
        ]
        if not any(keyword in simplified_norm for keyword in danger_keywords):
            return []
        violation = GuardrailViolation(
            policy_id='food_safety',
            policy_name='Food Safety Guardrail',
            rule_id='unicode-homoglyph',
            action='safe-completion',
            severity='medium',
            message='Phát hiện ký tự Unicode bất thường được dùng để vượt kiểm duyệt an toàn thực phẩm.',
            remediation='Chuẩn hóa văn bản và nhắc lại hướng dẫn an toàn của CDC/USDA.',
            matches=unique(suspicious),
        )
        return [violation]

    def _match_regex(self, rule: Dict[str, Any], prompt_text: str, response_text: str) -> List[str]:
        matches: List[str] = []
        for pattern in rule.get('compiled_patterns', []):
            matches.extend(self._extract_matches(pattern.findall(prompt_text)))
            matches.extend(self._extract_matches(pattern.findall(response_text)))
        return matches

    def _match_keywords(
        self,
        rule: Dict[str, Any],
        normalized_prompt: str,
        normalized_response: str,
    ) -> List[str]:
        keywords = rule.get('keywords') or []
        matches = [kw for kw in keywords if kw in normalized_prompt or kw in normalized_response]
        return matches

    def _match_allergy(
        self,
        rule: Dict[str, Any],
        normalized_prompt: str,
        normalized_response: str,
    ) -> List[str]:
        if not any(trigger in normalized_prompt for trigger in self._ALLERGY_TRIGGERS):
            return []
        matches = []
        for allergen in rule.get('allergens', []):
            allergen_norm = norm_text(allergen)
            if allergen_norm in normalized_prompt and allergen_norm in normalized_response:
                matches.append(allergen)
        return matches

    @staticmethod
    def _extract_matches(raw_matches: Iterable[Any]) -> List[str]:
        results: List[str] = []
        for match in raw_matches:
            if isinstance(match, tuple):
                text = ' '.join([m for m in match if m])
            else:
                text = str(match)
            text = text.strip()
            if text:
                results.append(text)
        return results