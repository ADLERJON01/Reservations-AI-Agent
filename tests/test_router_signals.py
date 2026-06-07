"""RouterSignals constructs with safe defaults and enforces its bounds."""
import pytest
from pydantic import ValidationError

from app.models.router_signals import RouterSignals


def test_default_construction_is_safe():
    s = RouterSignals()
    assert s.schema_valid is True
    assert s.llm_parse_error is False
    assert s.validator_result == "skipped"
    assert s.audit_finding == "n/a"
    assert s.classifier_confidence is None
    assert s.kb_answerable is None
    assert s.validator_flagged_fields == []
    assert s.force_manual_review is False


def test_confidence_bounds_enforced():
    RouterSignals(classifier_confidence=0.0)
    RouterSignals(classifier_confidence=1.0)
    with pytest.raises(ValidationError):
        RouterSignals(classifier_confidence=1.2)
    with pytest.raises(ValidationError):
        RouterSignals(classifier_confidence=-0.1)


def test_invalid_validator_result_rejected():
    with pytest.raises(ValidationError):
        RouterSignals(validator_result="maybe")
