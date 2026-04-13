from __future__ import annotations

from app.utils.mass_apply.contract_types import (
    format_contract_type_label,
    infer_contract_type,
)


def test_infer_contract_type_prefers_raw_value() -> None:
    assert infer_contract_type("full_time", "Stage QA") == "full_time"


def test_infer_contract_type_detects_alternance_from_title() -> None:
    assert (
        infer_contract_type(None, "Alternant Ingenieur QA", ["Jira"])
        == "apprenticeship"
    )


def test_format_contract_type_label_uses_expected_labels() -> None:
    assert format_contract_type_label("internship") == "Stage"
    assert format_contract_type_label("apprenticeship") == "Alternance"
    assert format_contract_type_label(None) == "—"
