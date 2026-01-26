"""
Module des sections de profil pour ExtractedDataViewer.

Ce module contient toutes les sections modulaires du visualisateur de données extraites,
organisées en composants réutilisables et maintenables.
"""

from .base_section import BaseSection
from .personal_info_section import PersonalInfoSection
from .experience_section import ExperienceSection
from .education_section import EducationSection
from .skills_section import SkillsSection
from .soft_skills_section import SoftSkillsSection
from .projects_section import ProjectsSection
from .languages_section import LanguagesSection
from .certifications_section import CertificationsSection
from .publications_section import PublicationsSection
from .volunteering_section import VolunteeringSection
from .awards_section import AwardsSection
from .references_section import ReferencesSection
from .interests_section import InterestsSection

__all__ = [
    'BaseSection',
    'PersonalInfoSection',
    'ExperienceSection', 
    'EducationSection',
    'SkillsSection',
    'SoftSkillsSection',
    'ProjectsSection',
    'LanguagesSection',
    'CertificationsSection',
    'PublicationsSection',
    'VolunteeringSection',
    'AwardsSection',
    'ReferencesSection',
    'InterestsSection'
]
