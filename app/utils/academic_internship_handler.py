"""
Gestionnaire des stages académiques avec distinction cohérente école/expérience.
Implémente la logique de classification et de liaison pour éviter les incohérences.
"""

import re
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from ..logging.safe_logger import get_safe_logger
from ..config import (
    DEFAULT_PII_CONFIG, EXPERIENCE_CONF, SCHOOL_TOKENS, DEPART_TOKENS,
    EMPLOYMENT_KEYWORDS, COURSE_TOKENS, ACTION_VERBS_FR, DELIVERABLE_TOKENS
)
from .experience_filters import normalize_text_for_matching

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class AcademicInternshipHandler:
    """Gestionnaire pour la classification intelligente des stages académiques."""
    
    def __init__(self):
        self.config = EXPERIENCE_CONF
        self.logger = get_safe_logger(f"{__name__}.AcademicInternshipHandler", cfg=DEFAULT_PII_CONFIG)
    
    def classify_experience_context(self, text_lines: List[str], line_idx: int, 
                                  ner_entities: List[Dict] = None) -> Dict[str, Any]:
        """
        Classifie le contexte d'une expérience pour déterminer son type et ses attributs.
        
        Args:
            text_lines: Lignes de texte du CV
            line_idx: Index de la ligne centrale
            ner_entities: Entités NER détectées
        
        Returns:
            Classification avec subtype, organisations, flags de cohérence
        """
        context_window = self.config["context_window"]
        start_idx = max(0, line_idx - context_window)
        end_idx = min(len(text_lines), line_idx + context_window + 1)
        
        context_text = " ".join(text_lines[start_idx:end_idx]).lower()
        context_normalized = normalize_text_for_matching(context_text)
        
        # Initialisation de la classification
        classification = {
            "subtype": "employment",  # Défaut
            "employer_org": None,
            "host_institution": None,
            "department": None,
            "context_linked_education_id": None,
            "coherence_flags": {
                "school_as_employer": False,
                "mixed_edu_exp_signals": False,
                "low_role_signal": False
            },
            "context_scores": {
                "employment_signal": 0.0,
                "course_signal": 0.0,
                "action_signal": 0.0,
                "deliverable_signal": 0.0
            }
        }
        
        # Étape 1: Identifier l'institution hôte
        host_institution = self._identify_academic_host(text_lines, line_idx, ner_entities)
        if host_institution:
            classification["host_institution"] = host_institution
            self.logger.debug(f"ACADEMIC: host_institution_detected | host='{host_institution[:20]}...'")
        
        # Étape 2: Identifier le département/laboratoire
        department = self._identify_department(context_text)
        if department:
            classification["department"] = department
            self.logger.debug(f"ACADEMIC: department_detected | dept='{department[:20]}...'")
        
        # Étape 3: Calculer les signaux contextuels
        classification["context_scores"] = self._calculate_context_scores(context_normalized)
        
        # Étape 4: Déterminer le sous-type
        classification["subtype"] = self._determine_subtype(
            classification["context_scores"], 
            host_institution, 
            department
        )
        
        # Étape 5: Choisir employer_org
        employer_org = self._choose_employer_org(text_lines, line_idx, ner_entities, host_institution)
        classification["employer_org"] = employer_org
        
        # Étape 6: Définir les flags de cohérence
        classification["coherence_flags"] = self._set_coherence_flags(
            classification, context_normalized
        )
        
        self.logger.info(f"ACADEMIC: classification_complete | subtype='{classification['subtype']}' "
                        f"employer='{employer_org[:15] if employer_org else 'None'}...' "
                        f"host='{host_institution[:15] if host_institution else 'None'}...'")
        
        return classification
    
    def _identify_academic_host(self, text_lines: List[str], line_idx: int, 
                               ner_entities: List[Dict] = None) -> Optional[str]:
        """Identifie l'institution académique hôte dans le contexte."""
        context_window = self.config["context_window"]
        
        # Recherche dans les entités NER d'abord
        if ner_entities:
            for entity in ner_entities:
                if entity.get('label') != 'ORG':
                    continue
                    
                entity_line = entity.get('line_idx', -1)
                if abs(entity_line - line_idx) > context_window:
                    continue
                
                org_text = entity.get('text', '')
                if self._is_school_organization(org_text):
                    return org_text
        
        # Recherche textuelle si pas trouvé dans NER
        start_idx = max(0, line_idx - context_window)
        end_idx = min(len(text_lines), line_idx + context_window + 1)
        
        for i in range(start_idx, end_idx):
            line = text_lines[i]
            line_normalized = normalize_text_for_matching(line)
            
            for school_token in SCHOOL_TOKENS:
                school_normalized = normalize_text_for_matching(school_token)
                if school_normalized in line_normalized:
                    # Extraire le nom complet de l'organisation
                    return self._extract_full_org_name(line, school_token)
        
        return None
    
    def _identify_department(self, context_text: str) -> Optional[str]:
        """Identifie le département ou laboratoire dans le contexte."""
        for depart_token in DEPART_TOKENS:
            # Pattern plus flexible pour capturer les noms avec d', de, etc.
            patterns = [
                rf'\b{re.escape(depart_token)}\s+([^,\n.]{2,50})',  # Laboratoire Nom
                rf'\b{re.escape(depart_token)}\s+d[\'`\u2019]([^,\n.]{2,50})',  # Laboratoire d'Nom  
                rf'\b{re.escape(depart_token)}\s+de\s+([^,\n.]{2,50})',  # Laboratoire de Nom
                rf'\b{re.escape(depart_token)}\s*[:-]\s*([^,\n.]{2,50})',  # Laboratoire: Nom
            ]
            
            for pattern in patterns:
                match = re.search(pattern, context_text, re.IGNORECASE)
                if match:
                    dept_name = match.group(1).strip()
                    return f"{depart_token.title()} {dept_name}"
        
        return None
    
    def _calculate_context_scores(self, context_normalized: str) -> Dict[str, float]:
        """Calcule les scores des différents signaux contextuels."""
        scores = {
            "employment_signal": 0.0,
            "course_signal": 0.0,
            "action_signal": 0.0,
            "deliverable_signal": 0.0
        }
        
        # Signal d'emploi
        employment_count = sum(1 for keyword in EMPLOYMENT_KEYWORDS 
                             if normalize_text_for_matching(keyword) in context_normalized)
        scores["employment_signal"] = min(employment_count / 3.0, 1.0)
        
        # Signal de cours
        course_count = sum(1 for token in COURSE_TOKENS 
                          if normalize_text_for_matching(token) in context_normalized)
        scores["course_signal"] = min(course_count / 4.0, 1.0)
        
        # Signal d'action
        action_count = sum(1 for verb in ACTION_VERBS_FR 
                          if normalize_text_for_matching(verb) in context_normalized)
        scores["action_signal"] = min(action_count / 2.0, 1.0)
        
        # Signal de délivrable
        deliverable_count = sum(1 for token in DELIVERABLE_TOKENS 
                               if normalize_text_for_matching(token) in context_normalized)
        scores["deliverable_signal"] = min(deliverable_count / 2.0, 1.0)
        
        return scores
    
    def _determine_subtype(self, scores: Dict[str, float], host_institution: str, 
                          department: str) -> str:
        """Détermine le sous-type d'expérience basé sur les scores et le contexte."""
        
        # Si signal de cours très fort sans emploi, c'est probablement de l'éducation
        if scores["course_signal"] >= 0.5 and scores["employment_signal"] < 0.2:
            return "education_coursework"  # Sera rétrogradé
        
        # Si institution académique avec département, même avec signal d'emploi faible
        if host_institution and department:
            # Stage académique si on a délivrables OU action verbs OU signal d'emploi minimal
            if (scores["deliverable_signal"] >= 0.5 or 
                scores["action_signal"] >= 0.5 or 
                scores["employment_signal"] >= 0.2):
                return "internship_academic"
        
        # Si signal d'emploi fort, c'est un stage ou emploi
        if scores["employment_signal"] >= 0.33:
            if host_institution:
                return "internship"
            else:
                return "employment"
        
        # Si institution académique seule (sans département détaillé)
        if host_institution:
            return "internship"
        
        return "employment"
    
    def _choose_employer_org(self, text_lines: List[str], line_idx: int, 
                           ner_entities: List[Dict], host_institution: str) -> Optional[str]:
        """Choisit l'organisation employeuse prioritaire."""
        rebind_window = self.config["org_rebind_window"]
        
        # Recherche d'une organisation non-scolaire en priorité
        if ner_entities:
            non_school_orgs = []
            for entity in ner_entities:
                if entity.get('label') != 'ORG':
                    continue
                    
                entity_line = entity.get('line_idx', -1)
                if abs(entity_line - line_idx) > rebind_window:
                    continue
                
                org_text = entity.get('text', '')
                if not self._is_school_organization(org_text):
                    distance = abs(entity_line - line_idx)
                    non_school_orgs.append((distance, org_text))
            
            if non_school_orgs:
                # Retourner l'organisation non-scolaire la plus proche
                non_school_orgs.sort(key=lambda x: x[0])
                return non_school_orgs[0][1]
        
        # Si pas d'organisation externe, utiliser l'institution hôte
        return host_institution
    
    def _set_coherence_flags(self, classification: Dict[str, Any], 
                           context_normalized: str) -> Dict[str, bool]:
        """Définit les flags de cohérence pour l'expérience."""
        flags = {
            "school_as_employer": False,
            "mixed_edu_exp_signals": False,
            "low_role_signal": False
        }
        
        # École comme employeur
        if (classification["employer_org"] and 
            classification["host_institution"] and
            classification["employer_org"] == classification["host_institution"]):
            flags["school_as_employer"] = True
        
        # Signaux mixtes éducation/expérience
        scores = classification["context_scores"]
        if scores["course_signal"] > 0.3 and scores["employment_signal"] > 0.3:
            flags["mixed_edu_exp_signals"] = True
        
        # Signal de rôle faible
        if scores["employment_signal"] < 0.2 and scores["action_signal"] < 0.2:
            flags["low_role_signal"] = True
        
        return flags
    
    def _is_school_organization(self, org_text: str) -> bool:
        """Vérifie si une organisation est une institution scolaire."""
        if not org_text:
            return False
        
        org_normalized = normalize_text_for_matching(org_text)
        
        for school_token in SCHOOL_TOKENS:
            school_normalized = normalize_text_for_matching(school_token)
            if school_normalized in org_normalized:
                return True
        
        return False
    
    def _extract_full_org_name(self, line: str, school_token: str) -> str:
        """Extrait le nom complet de l'organisation depuis la ligne."""
        # Recherche du nom complet autour du token d'école
        pattern = rf'([A-Z][^,\n.]*{re.escape(school_token)}[^,\n.]*)'
        match = re.search(pattern, line, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        
        # Fallback: retourner le token trouvé
        return school_token
    
    def should_demote_to_education(self, classification: Dict[str, Any]) -> bool:
        """
        Détermine si une expérience doit être rétrogradée vers l'éducation.
        
        Règle: démotée si pas d'action verbs ET course tokens ≥ 2 
        ET employment keywords absent OU si subtype est education_coursework.
        """
        scores = classification["context_scores"]
        subtype = classification["subtype"]
        
        # Rétrogradation automatique pour coursework détecté
        if subtype == "education_coursework":
            return True
        
        # Critères de démotivation renforcés
        no_action_verbs = scores["action_signal"] < 0.2
        high_course_signal = scores["course_signal"] >= 0.5
        no_employment_signal = scores["employment_signal"] < 0.2
        
        # Exception: stages académiques avec département et délivrables
        is_academic_internship = (subtype == "internship_academic" and 
                                 classification["department"] and
                                 scores["deliverable_signal"] >= 0.5)
        
        if is_academic_internship:
            self.logger.debug("ACADEMIC: academic_internship_exception | kept_as_experience")
            return False
        
        # Démotivation si critères remplis
        if no_action_verbs and high_course_signal and no_employment_signal:
            self.logger.info(f"ACADEMIC: demote_to_education | action={scores['action_signal']:.2f} "
                            f"course={scores['course_signal']:.2f} employment={scores['employment_signal']:.2f}")
            return True
        
        return False
    
    def apply_confidence_adjustments(self, classification: Dict[str, Any], 
                                   base_confidence: float) -> float:
        """Applique les ajustements de confiance selon le type d'expérience."""
        confidence = base_confidence
        
        # Bonus pour stage académique avec département
        if (classification["subtype"] == "internship_academic" and 
            classification["department"]):
            confidence += 0.10
            self.logger.debug("ACADEMIC: confidence_boost | academic_internship_with_dept +0.10")
        
        # Pénalité pour école comme employeur (mais garder l'item)
        if classification["coherence_flags"]["school_as_employer"]:
            confidence -= 0.10
            self.logger.debug("ACADEMIC: confidence_penalty | school_as_employer -0.10")
        
        # Pénalité pour signal de rôle faible
        if classification["coherence_flags"]["low_role_signal"]:
            confidence -= 0.05
            self.logger.debug("ACADEMIC: confidence_penalty | low_role_signal -0.05")
        
        return max(0.0, min(1.0, confidence))
    
    def calculate_date_overlap_iou(self, period1: Dict[str, str], 
                                  period2: Dict[str, str]) -> float:
        """Calcule l'IoU (Intersection over Union) entre deux périodes."""
        try:
            # Parser les dates (format simplifié MM/YYYY ou YYYY)
            def parse_date(date_str: str) -> Optional[datetime]:
                if not date_str or date_str.lower() in ['present', 'présent', 'actuel']:
                    return datetime.now()
                
                if '/' in date_str:
                    parts = date_str.split('/')
                    if len(parts) == 2:
                        month, year = int(parts[0]), int(parts[1])
                        return datetime(year, month, 1)
                elif len(date_str) == 4 and date_str.isdigit():
                    return datetime(int(date_str), 1, 1)
                
                return None
            
            start1 = parse_date(period1.get('start_date', ''))
            end1 = parse_date(period1.get('end_date', ''))
            start2 = parse_date(period2.get('start_date', ''))
            end2 = parse_date(period2.get('end_date', ''))
            
            if not all([start1, end1, start2, end2]):
                return 0.0
            
            # Calculer l'intersection
            intersection_start = max(start1, start2)
            intersection_end = min(end1, end2)
            
            if intersection_start >= intersection_end:
                return 0.0
            
            # Calculer l'union
            union_start = min(start1, start2)
            union_end = max(end1, end2)
            
            intersection_days = (intersection_end - intersection_start).days
            union_days = (union_end - union_start).days
            
            if union_days == 0:
                return 0.0
            
            iou = intersection_days / union_days
            return max(0.0, min(1.0, iou))
            
        except Exception as e:
            self.logger.debug(f"ACADEMIC: date_overlap_calculation_error | error={e}")
            return 0.0


def create_academic_internship_handler() -> AcademicInternshipHandler:
    """Factory function pour créer un gestionnaire de stages académiques."""
    return AcademicInternshipHandler()
