from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
import yaml

from app.utils.text_match import norm_text, unique


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
        self._load_policies()

    def evaluate(self, prompt_text: str, response_text: str) -> List[GuardrailViolation]:
        prompt_text = prompt_text or ''
        response_text = response_text or ''
        normalized_prompt = norm_text(prompt_text)
        normalized_response = norm_text(response_text)

        violations: List[GuardrailViolation] = []

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
            if 'deprecated' in str(path):
                continue
            
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

    def _detect_homoglyphs(self, text: str, normalized: str) -> List[GuardrailViolation]:
        suspicious = [char for char in self._SUSPICIOUS_CHARS if char in text]
        if not suspicious:
            return []
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
