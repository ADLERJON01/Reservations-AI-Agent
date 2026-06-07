"""The EmailExtraction contract gate validates and rejects correctly."""
import pytest
from pydantic import ValidationError

from app.models.llm_output import EmailExtraction

MINIMAL_VALID = {
    "classification": {
        "predicted_category": "booking_notification",
        "sender_type": "automated_system",
        "request_type": "none",
        "booking_lifecycle_stage": "new",
        "expects_human_response": "no",
        "urgency_signal": "routine",
        "confidence": 0.9,
        "evidence_short": "templated booking confirmation",
        "reasoning_short": "single booking lifecycle event",
    },
    "extraction": {},  # all extraction sub-objects default to empty
}


def test_minimal_valid_object_validates():
    obj = EmailExtraction.model_validate(MINIMAL_VALID)
    assert obj.classification.predicted_category == "booking_notification"
    # extraction defaults are populated, not None
    assert obj.extraction.guest.additional_travelers == []


def test_out_of_vocabulary_category_rejected():
    bad = {**MINIMAL_VALID, "classification": {**MINIMAL_VALID["classification"],
                                               "predicted_category": "not_a_real_category"}}
    with pytest.raises(ValidationError):
        EmailExtraction.model_validate(bad)


def test_confidence_out_of_range_rejected():
    bad = {**MINIMAL_VALID, "classification": {**MINIMAL_VALID["classification"],
                                               "confidence": 1.5}}
    with pytest.raises(ValidationError):
        EmailExtraction.model_validate(bad)


def test_missing_required_classification_field_rejected():
    cls = {k: v for k, v in MINIMAL_VALID["classification"].items() if k != "sender_type"}
    with pytest.raises(ValidationError):
        EmailExtraction.model_validate({**MINIMAL_VALID, "classification": cls})
