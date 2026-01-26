"""
Package de widgets réutilisables pour CVMatch
============================================

Ce package centralise tous les widgets réutilisables pour garantir la cohérence
et faciliter la maintenance de l'interface utilisateur.

Widgets disponibles:
- PhoneNumberWidget: Sélection de téléphone avec code pays
- StyleManager: Gestionnaire de styles centralisé  
- DialogManager: Gestionnaire de dialogues cohérents
- SectionHeaderWidget: En-têtes de section standardisés
- ValidationUtils: Utilitaires de validation de données
"""

# Imports existants
from .model_selector import CompactModelSelector

# Nouveaux imports pour faciliter l'utilisation
from .phone_widget import PhoneNumberWidget, create_phone_widget
from .style_manager import StyleManager, apply_button_style, apply_input_style, apply_section_header_style
from .dialog_manager import DialogManager, show_success, show_error, show_warning, ask_confirmation, select_file, save_file, select_directory
from .section_header import SectionHeaderWidget, CompactSectionHeader, CategoryHeader, create_section_header, create_compact_header, create_category_header
from .collapsible_section import CollapsibleSection, QuickCollapsibleGroup, create_collapsible_section
from .generic_fields import (
    GenericFieldWidget, GenericListSection, create_generic_section,
    create_languages_section, create_certifications_section, create_publications_section,
    create_volunteering_section, create_awards_section, create_references_section, 
    create_projects_section, create_interests_section,
    LANGUAGE_FIELDS, CERTIFICATION_FIELDS, PUBLICATION_FIELDS, VOLUNTEERING_FIELDS,
    AWARD_FIELDS, REFERENCE_FIELDS, PROJECT_FIELDS, INTEREST_FIELDS
)

# Widgets réutilisables
__all__ = [
    # Existing widgets
    'CompactModelSelector',
    
    # Phone widget
    'PhoneNumberWidget',
    'create_phone_widget',
    
    # Style management
    'StyleManager', 
    'apply_button_style',
    'apply_input_style', 
    'apply_section_header_style',
    
    # Dialog management
    'DialogManager',
    'show_success',
    'show_error', 
    'show_warning',
    'ask_confirmation',
    'select_file',
    'save_file',
    'select_directory',
    
    # Section headers
    'SectionHeaderWidget',
    'CompactSectionHeader', 
    'CategoryHeader',
    'create_section_header',
    'create_compact_header',
    'create_category_header',
    
    # Collapsible sections
    'CollapsibleSection',
    'QuickCollapsibleGroup',
    'create_collapsible_section',
    
    # Generic fields
    'GenericFieldWidget',
    'GenericListSection',
    'create_generic_section',
    'create_languages_section',
    'create_certifications_section', 
    'create_publications_section',
    'create_volunteering_section',
    'create_awards_section',
    'create_references_section',
    'create_projects_section',
    'create_interests_section',
    'LANGUAGE_FIELDS',
    'CERTIFICATION_FIELDS',
    'PUBLICATION_FIELDS', 
    'VOLUNTEERING_FIELDS',
    'AWARD_FIELDS',
    'REFERENCE_FIELDS',
    'PROJECT_FIELDS',
    'INTEREST_FIELDS'
]
