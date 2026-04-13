from __future__ import annotations

from types import SimpleNamespace

from app.utils.mass_apply.review_payload_builder import build_review_payload


def test_review_payload_includes_missing_required_legal_field() -> None:
    raw = SimpleNamespace(
        label="I agree to the privacy policy",
        input_type="checkbox",
        required=True,
    )
    mapped = SimpleNamespace(raw=raw)
    resolved = SimpleNamespace(
        mapped=mapped,
        value=None,
        source="legal_skip",
        needs_human=True,
    )

    payload = build_review_payload(
        row=SimpleNamespace(id=1, job_title="Role", company="Company"),
        qualification=SimpleNamespace(to_payload=lambda: {"decision": "qualified"}),
        report=SimpleNamespace(score=55, blocking_reasons=["legal field"]),
        prepared=SimpleNamespace(
            application_id=99,
            cv_pdf_path="cv.pdf",
            cover_letter_pdf_path="letter.pdf",
            preview_data={},
        ),
        resolved_fields=[resolved],
        screenshot_path=None,
    )

    assert payload["filled_fields"] == [
        {
            "label": "I agree to the privacy policy",
            "value": "",
            "source": "legal_skip",
            "needs_human": True,
            "required": True,
            "input_type": "checkbox",
            "missing": True,
        }
    ]
    assert payload["blocking_reasons"] == ["legal field"]
