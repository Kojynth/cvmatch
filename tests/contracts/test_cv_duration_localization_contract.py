from __future__ import annotations

from app.utils.cv_postprocessing import _format_duration_label


def test_duration_labels_follow_target_language_without_french_leakage() -> None:
    assert _format_duration_label(14, language_code="de-DE") == "1 Jahr 2 Monate"
    assert _format_duration_label(14, language_code="ja-JP") == "1\u5e74 2\u304b\u6708"
    assert _format_duration_label(14, language_code="zh-CN") == "1\u5e74 2\u4e2a\u6708"
    assert _format_duration_label(14, language_code="pt-BR") == "1 ano 2 meses"
    assert _format_duration_label(14, language_code="xx") == "1 yr 2 mos"
