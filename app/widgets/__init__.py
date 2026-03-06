"""
Reusable widgets package for CVMatch.

Exports are loaded lazily to avoid importing heavy UI/model modules during
application startup.
"""

from __future__ import annotations

from importlib import import_module

_EXPORTS = {
    # Audit header
    "AuditHeaderWidget": ("app.widgets.audit_header_widget", "AuditHeaderWidget"),
    # Model selector
    "CompactModelSelector": ("app.widgets.model_selector", "CompactModelSelector"),
    # Phone widget
    "PhoneNumberWidget": ("app.widgets.phone_widget", "PhoneNumberWidget"),
    "create_phone_widget": ("app.widgets.phone_widget", "create_phone_widget"),
    # Style manager
    "StyleManager": ("app.widgets.style_manager", "StyleManager"),
    "apply_button_style": ("app.widgets.style_manager", "apply_button_style"),
    "apply_input_style": ("app.widgets.style_manager", "apply_input_style"),
    "apply_section_header_style": ("app.widgets.style_manager", "apply_section_header_style"),
    # Dialog manager
    "DialogManager": ("app.widgets.dialog_manager", "DialogManager"),
    "show_success": ("app.widgets.dialog_manager", "show_success"),
    "show_error": ("app.widgets.dialog_manager", "show_error"),
    "show_warning": ("app.widgets.dialog_manager", "show_warning"),
    "ask_confirmation": ("app.widgets.dialog_manager", "ask_confirmation"),
    "select_file": ("app.widgets.dialog_manager", "select_file"),
    "save_file": ("app.widgets.dialog_manager", "save_file"),
    "select_directory": ("app.widgets.dialog_manager", "select_directory"),
    # Section headers
    "SectionHeaderWidget": ("app.widgets.section_header", "SectionHeaderWidget"),
    "CompactSectionHeader": ("app.widgets.section_header", "CompactSectionHeader"),
    "CategoryHeader": ("app.widgets.section_header", "CategoryHeader"),
    "create_section_header": ("app.widgets.section_header", "create_section_header"),
    "create_compact_header": ("app.widgets.section_header", "create_compact_header"),
    "create_category_header": ("app.widgets.section_header", "create_category_header"),
    # Collapsible sections
    "CollapsibleSection": ("app.widgets.collapsible_section", "CollapsibleSection"),
    "QuickCollapsibleGroup": ("app.widgets.collapsible_section", "QuickCollapsibleGroup"),
    "create_collapsible_section": ("app.widgets.collapsible_section", "create_collapsible_section"),
    # Generic fields
    "GenericFieldWidget": ("app.widgets.generic_fields", "GenericFieldWidget"),
    "GenericListSection": ("app.widgets.generic_fields", "GenericListSection"),
    "create_generic_section": ("app.widgets.generic_fields", "create_generic_section"),
    "create_languages_section": ("app.widgets.generic_fields", "create_languages_section"),
    "create_certifications_section": ("app.widgets.generic_fields", "create_certifications_section"),
    "create_publications_section": ("app.widgets.generic_fields", "create_publications_section"),
    "create_volunteering_section": ("app.widgets.generic_fields", "create_volunteering_section"),
    "create_awards_section": ("app.widgets.generic_fields", "create_awards_section"),
    "create_references_section": ("app.widgets.generic_fields", "create_references_section"),
    "create_projects_section": ("app.widgets.generic_fields", "create_projects_section"),
    "create_interests_section": ("app.widgets.generic_fields", "create_interests_section"),
    "LANGUAGE_FIELDS": ("app.widgets.generic_fields", "LANGUAGE_FIELDS"),
    "CERTIFICATION_FIELDS": ("app.widgets.generic_fields", "CERTIFICATION_FIELDS"),
    "PUBLICATION_FIELDS": ("app.widgets.generic_fields", "PUBLICATION_FIELDS"),
    "VOLUNTEERING_FIELDS": ("app.widgets.generic_fields", "VOLUNTEERING_FIELDS"),
    "AWARD_FIELDS": ("app.widgets.generic_fields", "AWARD_FIELDS"),
    "REFERENCE_FIELDS": ("app.widgets.generic_fields", "REFERENCE_FIELDS"),
    "PROJECT_FIELDS": ("app.widgets.generic_fields", "PROJECT_FIELDS"),
    "INTEREST_FIELDS": ("app.widgets.generic_fields", "INTEREST_FIELDS"),
}

__all__ = sorted(_EXPORTS.keys())


def __getattr__(name: str):
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = target
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
