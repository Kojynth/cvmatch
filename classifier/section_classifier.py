#!/usr/bin/env python3
"""
Classificateur de sections CV avec règles explicites et scoring
Corrige les confusions: bénévolat, sabbatique, open-source, startup perso, clients, memberships
"""

import re
import yaml
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict
import unicodedata
import sys
import os

# Ajouter le chemin app au Python path pour les imports
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(__file__)), 'app'))

try:
    from logging.safe_logger import get_safe_logger
    from config import DEFAULT_PII_CONFIG
    logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)
except ImportError:
    # Fallback si imports relatifs ne marchent pas
    logger = logging.getLogger(__name__)

@dataclass
class ClassificationResult:
    """Résultat de classification avec provenance"""
    section: str
    score: float
    confidence: float
    triggered_rules: List[str] = field(default_factory=list)
    original_section: Optional[str] = None
    text_snippet: str = ""
    method: str = "heuristic"
    page: int = 1
    reclassified: bool = False
    reason: str = ""

@dataclass 
class SectionEntry:
    """Entrée de section avec métadonnées"""
    title: str
    content: str
    dates: Optional[str] = None
    location: Optional[str] = None
    classification: Optional[ClassificationResult] = None
    raw_text: str = ""

class SectionClassifier:
    """Classificateur de sections CV avec règles négatives strictes"""
    
    def __init__(self, rules_path: str = None, lexicons_path: str = None):
        self.base_path = Path(__file__).parent.parent
        
        # Charger règles de précédence
        if rules_path:
            self.rules_path = Path(rules_path)
        else:
            self.rules_path = self.base_path / "rules" / "precedence.yaml"
        
        # Charger lexiques multilingues
        if lexicons_path:
            self.lexicons_path = Path(lexicons_path)
        else:
            self.lexicons_path = self.base_path / "resources" / "lexicons" / "section_keywords.yaml"
        
        self.rules = self._load_rules()
        self.lexicons = self._load_lexicons()
        self.negative_rules = self.rules.get('negative_rules', {})
        self.thresholds = self.rules.get('scoring_thresholds', {})
        
        logger.info(f"Classificateur initialisé avec {len(self.negative_rules)} règles négatives")
    
    def _load_rules(self) -> Dict:
        """Charger table de précédence depuis YAML"""
        try:
            with open(self.rules_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Erreur chargement règles {self.rules_path}: {e}")
            return {}
    
    def _load_lexicons(self) -> Dict:
        """Charger lexiques multilingues depuis YAML"""
        try:
            with open(self.lexicons_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Erreur chargement lexiques {self.lexicons_path}: {e}")
            return {}
    
    def _normalize_text(self, text: str) -> str:
        """Normaliser texte (casse, accents, OCR)"""
        if not text:
            return ""
        
        # Normalisation Unicode pour accents
        normalized = unicodedata.normalize('NFD', text.lower())
        normalized = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
        
        # Correction OCR commune
        ocr_fixes = {
            '0': 'o',  '1': 'i', '3': 'e', 
            'rn': 'm', 'cl': 'd', 'vv': 'w'
        }
        for wrong, correct in ocr_fixes.items():
            normalized = normalized.replace(wrong, correct)
        
        return normalized.strip()
    
    def _extract_dates(self, text: str) -> Optional[str]:
        """Extraire dates du texte"""
        # Patterns de dates variés
        date_patterns = [
            r'\d{4}\s*[-–]\s*\d{4}',
            r'\d{4}\s*[-–]\s*(?:présent|present|aujourd\'hui|now)',
            r'(?:janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+\d{4}',
            r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{4}',
            r'\d{1,2}/\d{4}\s*[-–]\s*\d{1,2}/\d{4}'
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0)
        return None
    
    def _calculate_base_score(self, section: str, text: str, title: str = "") -> float:
        """Calculer score de base selon lexiques multilingues"""
        score = 0.0
        normalized_text = self._normalize_text(text + " " + title)
        
        section_lexicon = self.lexicons.get(section, {})
        
        # Parcourir toutes les langues
        for lang, keywords in section_lexicon.items():
            if not isinstance(keywords, dict):
                continue
                
            # Mots-clés positifs
            positive_keywords = keywords.get('positive', [])
            for keyword in positive_keywords:
                if self._normalize_text(keyword) in normalized_text:
                    score += 0.2
            
            # Mots-clés négatifs (pénalité)
            negative_keywords = keywords.get('negative', [])
            for keyword in negative_keywords:
                if self._normalize_text(keyword) in normalized_text:
                    score -= 0.3
        
        # Bonus pour présence dates si attendues
        if section == 'experience' and self._extract_dates(text):
            score += 0.1
        
        return max(-1.0, min(1.0, score))  # Clamp entre -1 et 1
    
    def _apply_negative_rules(self, section: str, text: str, title: str = "") -> Tuple[str, List[str], float]:
        """Appliquer règles négatives strictes"""
        original_section = section
        triggered_rules = []
        penalty = 0.0
        
        full_text = self._normalize_text(text + " " + title)
        
        for rule_id, rule in self.negative_rules.items():
            rule_triggered = False
            
            # Vérifier triggers
            triggers = rule.get('triggers', [])
            for trigger in triggers:
                if self._normalize_text(trigger) in full_text:
                    rule_triggered = True
                    break
            
            # Vérifier pattern regex si défini
            pattern = rule.get('pattern')
            if pattern and re.search(pattern, full_text, re.IGNORECASE | re.MULTILINE):
                rule_triggered = True
            
            if rule_triggered:
                # Vérifier anti-signaux (empêchent déclenchement)
                anti_signals = rule.get('anti_signals', [])
                anti_signal_found = False
                for anti_signal in anti_signals:
                    if self._normalize_text(anti_signal) in full_text:
                        anti_signal_found = True
                        break
                
                if not anti_signal_found:
                    confidence_threshold = rule.get('confidence_threshold', 0.8)
                    
                    if rule.get('action') == 'force_reclassify':
                        section = rule.get('target_section', 'other')
                        penalty = confidence_threshold
                        triggered_rules.append(rule_id)
                        logger.debug(f"Règle {rule_id} déclenchée: {original_section} → {section}")
                    
                    elif rule.get('action') == 'consolidate_as_one':
                        # Ne pas éclater liste clients
                        triggered_rules.append(rule_id)
                        penalty = 0.3
        
        return section, triggered_rules, penalty
    
    def classify_section(self, text: str, title: str = "", initial_section: str = "other") -> ClassificationResult:
        """Classifier une section avec règles et scoring"""
        
        # Score de base selon lexiques
        base_score = self._calculate_base_score(initial_section, text, title)
        
        # Application règles négatives OBLIGATOIRES
        final_section, triggered_rules, penalty = self._apply_negative_rules(initial_section, text, title)
        reclassified = (final_section != initial_section)
        
        # Score final avec pénalité
        final_score = base_score - penalty
        confidence = abs(final_score)
        
        # Logique de reclassification si score trop bas
        reclassification_threshold = self.thresholds.get('reclassification_threshold', -0.5)
        if final_score < reclassification_threshold and not reclassified:
            # Tenter reclassification automatique vers meilleure section
            best_section = self._find_best_section(text, title)
            if best_section != initial_section:
                final_section = best_section
                reclassified = True
                triggered_rules.append("AUTO-RECLASS")
        
        # Déterminer raison du reclassement
        reason = ""
        if reclassified:
            if triggered_rules:
                reason = f"Règle(s) {','.join(triggered_rules)}"
            else:
                reason = "Score insuffisant"
        
        return ClassificationResult(
            section=final_section,
            score=final_score,
            confidence=confidence,
            triggered_rules=triggered_rules,
            original_section=initial_section if reclassified else None,
            text_snippet=text[:100] + "..." if len(text) > 100 else text,
            method="rules_based",
            reclassified=reclassified,
            reason=reason
        )
    
    def _find_best_section(self, text: str, title: str = "") -> str:
        """Trouver meilleure section selon scores lexiques"""
        section_scores = {}
        
        for section in ['experience', 'education', 'volunteer', 'projects', 
                       'certifications', 'memberships', 'awards', 'skills', 'personal']:
            score = self._calculate_base_score(section, text, title)
            section_scores[section] = score
        
        # Retourner section avec meilleur score
        best_section = max(section_scores, key=section_scores.get)
        return best_section if section_scores[best_section] > 0.1 else "other"
    
    def classify_cv_sections(self, sections: List[Dict]) -> List[SectionEntry]:
        """Classifier toutes les sections d'un CV"""
        results = []
        
        for section_data in sections:
            title = section_data.get('title', '')
            content = section_data.get('content', '')
            initial_section = section_data.get('initial_classification', 'other')
            
            # Classification avec règles
            classification = self.classify_section(content, title, initial_section)
            
            # Extraire métadonnées
            dates = self._extract_dates(content)
            location = self._extract_location(content)
            
            entry = SectionEntry(
                title=title,
                content=content,
                dates=dates,
                location=location,
                classification=classification,
                raw_text=section_data.get('raw_text', content)
            )
            
            results.append(entry)
        
        return results
    
    def _extract_location(self, text: str) -> Optional[str]:
        """Extraire localisation (ville, pays)"""
        # Pattern simple pour localisation
        location_pattern = r'\b(?:Paris|Lyon|Marseille|Toulouse|Nice|Nantes|Strasbourg|Montpellier|Bordeaux|Lille|Rennes|Le Havre|Saint-Étienne|Toulon|Grenoble|Dijon|Angers|Nîmes|Villeurbanne|Clermont-Ferrand|London|Berlin|Madrid|Barcelona|Milan|Rome|Amsterdam|Brussels|Geneva|Zurich|New York|San Francisco|Los Angeles|Chicago|Toronto|Montreal|Vancouver|Tokyo|Seoul|Singapore|Sydney|Melbourne|São Paulo|Mexico City)\b'
        
        match = re.search(location_pattern, text, re.IGNORECASE)
        return match.group(0) if match else None
    
    def generate_classification_report(self, entries: List[SectionEntry]) -> Dict:
        """Générer rapport de classification"""
        total = len(entries)
        reclassified = sum(1 for entry in entries if entry.classification.reclassified)
        
        # Statistiques par section
        section_stats = defaultdict(int)
        rule_stats = defaultdict(int)
        
        for entry in entries:
            section_stats[entry.classification.section] += 1
            for rule in entry.classification.triggered_rules:
                rule_stats[rule] += 1
        
        return {
            'total_sections': total,
            'reclassified_count': reclassified,
            'reclassification_rate': reclassified / total if total > 0 else 0,
            'section_distribution': dict(section_stats),
            'triggered_rules': dict(rule_stats),
            'avg_confidence': sum(entry.classification.confidence for entry in entries) / total if total > 0 else 0
        }


def load_cv_from_text(text_path: str) -> List[Dict]:
    """Charger CV depuis fichier texte et détecter sections"""
    with open(text_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    sections = []
    current_section = {'title': '', 'content': '', 'initial_classification': 'other'}
    
    lines = content.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # Détection simple de titre de section (ligne en majuscules ou avec mots-clés)
        if _is_section_header(line):
            if current_section['content']:
                sections.append(current_section)
            current_section = {
                'title': line,
                'content': '',
                'initial_classification': _guess_initial_section(line)
            }
        else:
            current_section['content'] += line + '\n'
    
    # Ajouter dernière section
    if current_section['content']:
        sections.append(current_section)
    
    return sections

def _is_section_header(line: str) -> bool:
    """Détecter si une ligne est un titre de section"""
    # Ligne courte, majoritairement en majuscules
    if len(line) > 50:
        return False
    
    upper_ratio = sum(1 for c in line if c.isupper()) / len(line) if line else 0
    if upper_ratio > 0.5:
        return True
    
    # Ou contient mots-clés de section
    section_keywords = [
        'expérience', 'experience', 'formation', 'education', 'compétences', 'skills',
        'projets', 'projects', 'bénévolat', 'volunteer', 'certifications', 'langues', 'languages'
    ]
    
    line_normalized = unicodedata.normalize('NFD', line.lower())
    line_normalized = ''.join(c for c in line_normalized if unicodedata.category(c) != 'Mn')
    
    return any(keyword in line_normalized for keyword in section_keywords)

def _guess_initial_section(title: str) -> str:
    """Deviner section initiale selon titre"""
    title_norm = unicodedata.normalize('NFD', title.lower())
    title_norm = ''.join(c for c in title_norm if unicodedata.category(c) != 'Mn')
    
    if any(kw in title_norm for kw in ['experience', 'expérience', 'emploi', 'parcours', 'carrière']):
        return 'experience'
    elif any(kw in title_norm for kw in ['formation', 'education', 'diplôme', 'études']):
        return 'education'
    elif any(kw in title_norm for kw in ['bénévolat', 'volunteer', 'volontariat', 'associatif']):
        return 'volunteer'
    elif any(kw in title_norm for kw in ['projet', 'project', 'réalisation']):
        return 'projects'
    elif any(kw in title_norm for kw in ['compétence', 'skill', 'expertise']):
        return 'skills'
    elif any(kw in title_norm for kw in ['certification', 'licence', 'permis']):
        return 'certifications'
    else:
        return 'other'


if __name__ == "__main__":
    # Test rapide
    classifier = SectionClassifier()
    
    # Test cas bénévolat
    result = classifier.classify_section(
        "Coordinateur - Croix-Rouge (volontariat) 2022-2023",
        initial_section="experience"
    )
    
    print(f"Classification: {result.section}")
    print(f"Reclassifié: {result.reclassified}")
    print(f"Règles: {result.triggered_rules}")
