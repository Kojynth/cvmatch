import json
import sys
from pathlib import Path

# Ensure project root is on sys.path
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def run_normalize_text_for_matching_cases():
    from app.utils import experience_filters as filt
    from app.utils import experience_validation as vali

    cases = [
        "DÃ©veloppeur Python",
        "  ADMINISTRATEUR  SYSTÃˆMES  ",
        "IngÃ©nieur d'Ã©tudes",
        "MÃ©diation â€“ Ã‰cole @ Paris",
        "",
        "C++/C# DÃ©v. â€” Lyon",
    ]

    results = {
        "experience_filters": [filt.normalize_text_for_matching(x) for x in cases],
        "experience_validation": [vali.normalize_text_for_matching(x) for x in cases],
        "cases": cases,
    }
    return results


def main():
    out = {
        "normalize_text_for_matching": run_normalize_text_for_matching_cases(),
    }

    # Optional UI/Qt baseline for duplicated styles and buttons
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        # Languages/Projects style helpers and delete button
        from app.views.profile_sections.languages_section import LanguagesSection
        from app.views.profile_sections.projects_section import ProjectsSection

        lang = LanguagesSection(profile=None)
        proj = ProjectsSection(profile=None)

        def btn_info(btn):
            size = btn.size()
            return {
                'w': size.width(),
                'h': size.height(),
                'style': btn.styleSheet(),
            }

        out["ui_section_styles"] = {
            'languages': {
                'add_style': lang._get_add_button_style(),
                'frame_style': lang._get_widget_style(),
                'delete_btn': btn_info(lang.create_delete_button()),
            },
            'projects': {
                'add_style': proj._get_add_button_style(),
                'frame_style': proj._get_widget_style(),
                'delete_btn': btn_info(proj.create_delete_button()),
            },
        }
    except Exception as e:
        out["ui_section_styles"] = {"skipped": str(e)}

    # Emoji utils vs legacy
    try:
        from app.utils import emoji_utils as eu
        from app.utils import emoji_utils_old as eold
        samples = ["\U0001F464", "\u2699\ufe0f", "plain text", "ðŸ˜€"]
        out["emoji_utils"] = {
            'get_display_text_new': [eu.get_display_text(x) for x in samples],
            'get_display_text_old': [eold.get_display_text(x) for x in samples],
            'safe_emoji_new': [eu.safe_emoji(x) for x in samples],
            'safe_emoji_old': [eold.safe_emoji(x) for x in samples],
        }
    except Exception as e:
        out["emoji_utils"] = {"skipped": str(e)}

    # Universal GPU adapter snapshot (best-effort)
    try:
        from app.utils.universal_gpu_adapter import UniversalGPUAdapter
        uga = UniversalGPUAdapter()
        cfg = uga.get_optimal_model_config()
        out["universal_gpu_adapter"] = {
            'model_name': cfg.get('model_name'),
            'device': cfg.get('device'),
            'quantization': cfg.get('quantization'),
            'max_new_tokens': cfg.get('max_new_tokens'),
            'batch_size': cfg.get('batch_size'),
            'gpu_memory_utilization': cfg.get('gpu_memory_utilization'),
        }
    except Exception as e:
        out["universal_gpu_adapter"] = {"skipped": str(e)}

    # Backup viewer re-export sanity
    try:
        from app.views.extracted_data_viewer_backup import ExtractedDataViewer as BackupViewer
        from app.views.extracted_data_viewer import ExtractedDataViewer as MainViewer
        out["backup_viewer"] = {
            'backup_name': BackupViewer.__name__,
            'main_name': MainViewer.__name__,
            'same_name': BackupViewer.__name__ == MainViewer.__name__,
        }
    except Exception as e:
        out["backup_viewer"] = {"skipped": str(e)}

    # SettingsWidget ML handlers baseline (headless-safe)
    try:
        from PySide6.QtWidgets import QApplication
        app = QApplication.instance() or QApplication([])
        from app.views.main_window import SettingsWidget
        from app.models.user_profile import UserProfile
        prof = UserProfile(name='Test', email='test@example.com')
        sw = SettingsWidget(prof)
        # Determine available API
        has_progress = hasattr(sw, '_ensure_ml_progress_dialog')
        has_modal = hasattr(sw, '_ensure_ml_modal')
        # Start -> Stage -> Finish
        if hasattr(sw, '_on_ml_started'):
            sw._on_ml_started()
        if hasattr(sw, '_on_ml_stage'):
            sw._on_ml_stage('Baseline stage')
        before = bool(getattr(sw, '_ml_progress_dialog', None) or getattr(sw, '_ml_modal', None))
        if hasattr(sw, '_on_ml_finished'):
            sw._on_ml_finished()
        after = bool(getattr(sw, '_ml_progress_dialog', None) or getattr(sw, '_ml_modal', None))
        out["ml_settings_widget"] = {
            'has_progress_api': has_progress,
            'has_modal_api': has_modal,
            'dialog_visible_during': before,
            'dialog_present_after': after,
        }
    except Exception as e:
        out["ml_settings_widget"] = {"skipped": str(e)}
    # Parser metrics semantics
    try:
        from app.parsers.project_parser import ProjectParser
        from app.parsers.soft_skills_parser import SoftSkillsParser
        from app.parsers.experience_parser import ExperienceParser
        from app.parsers.education_parser import EducationParser
        def probe(cls):
            try:
                inst = cls()
                if not hasattr(inst, 'metrics') or not isinstance(getattr(inst, 'metrics'), dict):
                    inst.metrics = {'init': 1}
                got = inst.get_metrics()
                try:
                    got['__probe__'] = 999
                except Exception:
                    pass
                mutated = '__probe__' in inst.metrics
                return {'len': len(got), 'mutates_original_on_write': mutated, 'has_reset': hasattr(inst, 'reset_metrics')}
            except Exception as e:
                return {'error': str(e)}
        out['parser_metrics'] = {
            'ProjectParser': probe(ProjectParser),
            'SoftSkillsParser': probe(SoftSkillsParser),
            'ExperienceParser': probe(ExperienceParser),
            'EducationParser': probe(EducationParser),
        }
    except Exception as e:
        out['parser_metrics'] = {'skipped': str(e)}

    # Extraction mapping helpers behavior
    try:
        from app.utils.extraction_mapper import ExtractionMapper as _EM
        import app.utils.extraction_mapper_improved as emi
        em = _EM()
        samples = {
            'dates': ['2020-05', '05/2020', '2015 - 2019', 'foo'],
            'years': ['1989', '1995', 2025, 'abc'],
            'conf': ['high','low','unknown','medium','3','0',None]
        }
        out['mapping_validations'] = {
            'em_dates': [em._is_valid_date_format(s) for s in samples['dates']],
            'emi_dates': [emi._is_valid_date_format(s) for s in samples['dates']],
            'em_years': [em._is_valid_year(s) for s in samples['years']],
            'emi_years': [emi._is_valid_year(s) for s in samples['years']],
            'em_conf': [em._normalize_confidence(s) for s in samples['conf']],
            'emi_conf': [emi._normalize_confidence(s) for s in samples['conf']],
        }
    except Exception as e:
        out['mapping_validations'] = {'skipped': str(e)}

    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

