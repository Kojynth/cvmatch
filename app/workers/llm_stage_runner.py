"""
LLM Stage Runner
================

Run a single LLM stage in an isolated process to fully release VRAM on exit.
"""

from __future__ import annotations

import argparse
import json
from typing import Any, Dict

from .worker_data import ProfileWorkerData
from .llm_worker import CVGenerationWorker
from ..utils.memory_debug import log_memory_snapshot


def _load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: str, payload: Any) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a single CVMatch LLM stage.")
    parser.add_argument(
        "--stage",
        required=True,
        choices=[
            "offer_keywords",
            "draft",
            "critic",
            "final",
            "cover_letter",
            "cover_letter_critic",
        ],
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    payload = _load_json(args.input)
    profile_data = ProfileWorkerData(**(payload.get("profile_data") or {}))
    offer_data = payload.get("offer_data") or {}
    template = payload.get("template") or profile_data.preferred_template or "modern"
    user_instruction = str(payload.get("user_instruction") or "").strip()
    application_id = payload.get("application_id")
    previous_generation_audit = (
        payload.get("previous_generation_audit")
        if isinstance(payload.get("previous_generation_audit"), dict)
        else None
    )

    worker = CVGenerationWorker(
        profile_data,
        offer_data,
        template,
        application_id=application_id,
        user_instruction=user_instruction,
        cv_only_regen=bool(payload.get("cv_only_regen", False)),
        previous_generation_audit=previous_generation_audit,
    )
    stage = args.stage
    worker.qwen_manager._load_selected_model_config()
    try:
        worker.qwen_manager.set_runtime_stage(stage)
    except Exception:
        pass
    log_memory_snapshot(
        label="stage_runner_start",
        stage=stage,
        extra={"subprocess": True},
    )
    stage_model_id = str(payload.get("stage_model_id") or "").strip()
    if stage_model_id:
        try:
            worker.qwen_manager.apply_model_profile(
                stage_model_id,
                reason=f"stage_runner:{stage}",
            )
        except Exception as exc:
            raise RuntimeError(
                f"Stage model override failed ({stage_model_id}): {exc}"
            ) from exc

    result: Any
    log_memory_snapshot(
        label="stage_runner_before_execute",
        stage=stage,
        extra={"subprocess": True},
    )
    if stage == "offer_keywords":
        result = worker.generate_offer_keywords_json()
    elif stage == "draft":
        profile_json = payload.get("profile_json") or {}
        result = worker.generate_cv_json_draft(profile_json=profile_json)
        worker._ensure_cv_json_language_consistency(result, stage="draft")
        worker._apply_contact_fallback(result, profile_json)
        worker._apply_target_fallback(result)
    elif stage == "critic":
        cv_html = payload.get("cv_html") or ""
        result = worker.generate_critic_json(cv_html=cv_html)
    elif stage == "final":
        profile_json = payload.get("profile_json") or {}
        critic_json = payload.get("critic_json") or {}
        result = worker.generate_cv_json_final(
            profile_json=profile_json,
            critic_json=critic_json,
        )
        worker._ensure_cv_json_language_consistency(result, stage="final")
        worker._apply_contact_fallback(result, profile_json)
        worker._apply_target_fallback(result)
    elif stage == "cover_letter":
        letter_prompt = payload.get("letter_prompt") or ""
        cover_letter = worker.qwen_manager.generate_cover_letter(letter_prompt)
        result = {"cover_letter": cover_letter}
    elif stage == "cover_letter_critic":
        cover_letter = str(payload.get("cover_letter") or "")
        language_code = payload.get("language_code")
        result = worker.critique_and_rewrite_cover_letter(
            cover_letter=cover_letter,
            language_code=language_code,
        )
    else:
        raise SystemExit(f"Unknown stage: {stage}")

    log_memory_snapshot(
        label="stage_runner_after_execute",
        stage=stage,
        extra={"subprocess": True},
    )
    try:
        worker.qwen_manager.cleanup_memory()
    except Exception:
        pass
    log_memory_snapshot(
        label="stage_runner_after_cleanup",
        stage=stage,
        extra={"subprocess": True},
    )

    _write_json(args.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
