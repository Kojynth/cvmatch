"""
Constantes partagées pour les sections de CV.

Ce module définit la liste canonique des sections supportées
par CVMatch. Utilisée par l'extracteur, le mapper et le contrôleur
pour garantir la cohérence des comptages de sections.
"""

# Liste canonique des sections supportées par CVMatch
ALL_SECTIONS = [
    "personal_info",
    "experiences", 
    "education",
    "skills",
    "soft_skills",
    "languages",
    "projects",
    "certifications",
    "publications",
    "volunteering",
    "interests",
    "awards",
    "references"
]

# Sections qui sont des listes (toutes sauf personal_info)
LIST_SECTIONS = [s for s in ALL_SECTIONS if s != "personal_info"]

# Nombre total de sections (pour les comptages "X/13")
TOTAL_SECTIONS_COUNT = len(ALL_SECTIONS)

# Sections essentielles (pour les comptages "X/5")
ESSENTIAL_SECTIONS = [
    "personal_info",
    "experiences", 
    "education",
    "skills",
    "soft_skills"
]

ESSENTIAL_SECTIONS_COUNT = len(ESSENTIAL_SECTIONS)
