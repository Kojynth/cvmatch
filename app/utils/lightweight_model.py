"""
Modèle ultra-léger local
========================

Modèle de génération de CV sans téléchargement, basé sur des templates intelligents.
"""

import re
from typing import Dict, Any, Optional
from loguru import logger


class LightweightCVGenerator:
    """Générateur de CV ultra-léger sans IA lourde."""
    
    def __init__(self):
        self.templates = self._load_templates()
        logger.info("🚀 Générateur léger initialisé - Aucun téléchargement requis")
    
    def _load_templates(self) -> Dict[str, str]:
        """Charge les templates de CV."""
        return {
            "tech": """# {name}

## Informations de contact
- **Email:** {email}
- **Téléphone:** {phone}
- **LinkedIn:** {linkedin}

## Objectif professionnel
Poste cible : **{job_title}** chez **{company}**.

{job_context}

## Profil
{profile_summary}

## Expérience professionnelle
{experience_section}

## Compétences
{skills_section}

## Formation
{education_section}

---
*CV généré avec le générateur léger pour {job_title}*""",

            "modern": """# {name}
> **{job_title}** chez **{company}**

### Contact
- {email} | {phone}
- {linkedin}

### Objectif
{job_context}

### Profil
{profile_summary}

### Expérience professionnelle
{experience_section}

### Compétences
{skills_section}

### Formation
{education_section}

---
*CV généré avec le générateur léger pour {company} - {job_title}*"""
        }
    
    def generate_cv(
        self, 
        profile: Any, 
        offer_data: Dict[str, Any], 
        template: str = "modern",
        progress_callback=None
    ) -> str:
        """Génère un CV rapidement sans IA lourde."""
        
        if progress_callback:
            progress_callback("[RAPID] Génération ultra-rapide en cours...")
        
        # Extraire informations
        name = getattr(profile, 'name', 'Candidat')
        email = getattr(profile, 'email', 'email@exemple.com')
        phone = getattr(profile, 'phone', 'Téléphone à renseigner')
        linkedin = getattr(profile, 'linkedin_url', 'LinkedIn à renseigner')
        master_cv = getattr(profile, 'master_cv_content', '')
        
        job_title = offer_data.get('job_title', 'Poste recherché')
        company = offer_data.get('company', 'Entreprise cible')
        offer_text = offer_data.get('text', '')
        
        if progress_callback:
            progress_callback("[ADAPT] Adaptation au poste...")
        
        # Contexte de l'offre
        job_context = self._extract_job_context(offer_text, job_title, company)
        
        # Sections du CV
        profile_summary = self._generate_profile_summary(master_cv, offer_text)
        experience_section = self._extract_experience(master_cv, offer_text)
        skills_section = self._extract_skills(master_cv, offer_text)
        education_section = self._extract_education(master_cv)
        
        if progress_callback:
            progress_callback("[FINAL] Finalisation du CV...")
        
        # Sélection template
        template_content = self.templates.get(template, self.templates["modern"])
        
        # Génération finale
        cv_content = template_content.format(
            name=name,
            email=email,
            phone=phone,
            linkedin=linkedin,
            job_title=job_title,
            company=company,
            job_context=job_context,
            profile_summary=profile_summary,
            experience_section=experience_section,
            skills_section=skills_section,
            education_section=education_section
        )
        
        if progress_callback:
            progress_callback("[OK] CV généré en <10 secondes!")
        
        logger.info(f"[OK] CV léger généré - {len(cv_content)} caractères")
        return cv_content
    
    def _extract_job_context(self, offer_text: str, job_title: str, company: str) -> str:
        """Extrait le contexte de l'offre."""
        if not offer_text:
            return f"Opportunité professionnelle au sein de {company}."
        
        # Résumer l'offre en 2-3 phrases
        sentences = offer_text.split('.')[:3]
        context = '. '.join(s.strip() for s in sentences if s.strip())
        
        return f"**Contexte :** {context}." if context else f"Poste de {job_title} chez {company}."
    
    def _generate_profile_summary(self, master_cv: str, offer_text: str) -> str:
        """Génère un résumé de profil adapté."""
        if not master_cv:
            return "Profil candidat à compléter depuis les informations source disponibles."
        
        # Extraire les premiers paragraphes pertinents
        lines = master_cv.split('\n')
        summary_lines = []
        
        for line in lines[:10]:  # 10 premières lignes
            line = line.strip()
            if line and not line.startswith('#') and len(line) > 20:
                summary_lines.append(line)
                if len(summary_lines) >= 3:
                    break
        
        if summary_lines:
            return ' '.join(summary_lines)[:300] + "..."
        
        return "Profil candidat fondé sur les informations source disponibles."
    
    def _extract_experience(self, master_cv: str, offer_text: str) -> str:
        """Extrait l'expérience pertinente."""
        if not master_cv:
            return """### Expérience à détailler
**Poste récent** | Période
- Responsabilités principales à compléter
- Réalisations mesurables à ajouter"""
        
        # Chercher section expérience
        experience_section = self._extract_section(master_cv, ['expérience', 'experience', 'emploi', 'poste'])
        
        if experience_section:
            return experience_section[:500] + "..." if len(experience_section) > 500 else experience_section
        
        return "Expérience professionnelle pertinente à détailler selon votre parcours."
    
    def _extract_skills(self, master_cv: str, offer_text: str) -> str:
        """Extrait les compétences."""
        if not master_cv:
            return """- Compétences à compléter depuis le profil source
- Outils ou méthodes étayés par le profil source
- Points forts à confirmer depuis le profil"""
        
        # Chercher section compétences
        skills_section = self._extract_section(master_cv, ['compétence', 'competence', 'skill', 'technique'])
        
        if skills_section:
            return skills_section[:300] + "..." if len(skills_section) > 300 else skills_section
        
        return "Compétences à compléter depuis les informations source disponibles."
    
    def _extract_education(self, master_cv: str) -> str:
        """Extrait la formation."""
        if not master_cv:
            return """**Formation à renseigner**
- Niveau d'études
- Spécialisation
- Établissement"""
        
        # Chercher section formation
        education_section = self._extract_section(master_cv, ['formation', 'education', 'diplôme', 'étude'])
        
        if education_section:
            return education_section[:200] + "..." if len(education_section) > 200 else education_section
        
        return "Formation adaptée au domaine professionnel."
    
    def _extract_section(self, text: str, keywords: list) -> str:
        """Extrait une section basée sur des mots-clés."""
        lines = text.split('\n')
        section_lines = []
        in_section = False
        
        for line in lines:
            line_lower = line.lower()
            
            # Début de section
            if any(keyword in line_lower for keyword in keywords):
                in_section = True
                section_lines.append(line)
                continue
            
            # Dans la section
            if in_section:
                if line.strip():
                    # Nouvelle section détectée (titre avec #)
                    if line.startswith('#') and not any(keyword in line_lower for keyword in keywords):
                        break
                    section_lines.append(line)
                else:
                    section_lines.append(line)
                    
                # Limiter la taille
                if len(section_lines) > 10:
                    break
        
        return '\n'.join(section_lines).strip()


# Instance globale
lightweight_generator = LightweightCVGenerator()
