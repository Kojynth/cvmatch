from __future__ import annotations

import sys
import types

from app.utils.cv_postprocessing import _normalize_experience_date_formats


def test_unrecognized_free_text_dates_are_preserved_in_display_formatting(
    monkeypatch,
) -> None:
    fake_date_normalize = types.ModuleType("app.rules.date_normalize")
    fake_date_normalize._normalize_single_date = lambda raw: raw
    fake_date_normalize.normalize_present_token = lambda raw: raw
    monkeypatch.setitem(sys.modules, "app.rules.date_normalize", fake_date_normalize)

    cv_json = {
        "experience": [
            {
                "start_date": "March 2021",
                "end_date": "April 2022",
            }
        ],
        "education": [],
    }

    _normalize_experience_date_formats(cv_json)

    assert cv_json["experience"][0]["start_date"] == "March 2021"
    assert cv_json["experience"][0]["end_date"] == "April 2022"
