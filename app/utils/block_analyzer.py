"""
Block Analyzer - Système de détection et d'analyse de blocs cohérents dans les CVs.

Découpe intelligemment le CV en blocs d'information cohérents pour une extraction
contextuelle précise, évitant les faux positifs du traitement ligne par ligne.
"""

import re
import unicodedata
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum

from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG
from ..utils.pii import validate_no_pii_leakage

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class BlockType(Enum):
    """Types de blocs détectés."""
    EXPERIENCE = "experience"
    EDUCATION = "education" 
    CERTIFICATION = "certification"
    SKILLS = "skills"
    PROJECTS = "projects"
    HEADER = "header"
    UNKNOWN = "unknown"


@dataclass
class InformationBlock:
    """Représente un bloc d'information cohérent dans le CV."""
    
    lines: List[str]
    start_idx: int
    end_idx: int
    detected_elements: Dict[str, str] = field(default_factory=dict)
    confidence_scores: Dict[str, float] = field(default_factory=dict)
    block_type: BlockType = BlockType.UNKNOWN
    raw_text: str = ""
    
    def __post_init__(self):
        """Initialise le texte brut du bloc."""
        self.raw_text = "\n".join(self.lines)
        
        # Initialise les éléments détectés avec des valeurs par défaut
        if not self.detected_elements:
            self.detected_elements = {
                "title": "",
                "organization": "",
                "dates": "", 
                "description": "",
                "location": ""
            }
    
    def get_line_count(self) -> int:
        """Retourne le nombre de lignes du bloc."""
        return len(self.lines)
    
    def contains_pattern(self, pattern: str, flags: int = re.IGNORECASE) -> bool:
        """Vérifie si le bloc contient un motif regex."""
        try:
            return bool(re.search(pattern, self.raw_text, flags))
        except re.error:
            return False
    
    def get_safe_preview(self, max_chars: int = 100) -> str:
        """Retourne un aperçu sécurisé du bloc pour les logs."""
        preview = self.raw_text.replace('\n', ' ')[:max_chars]
        return validate_no_pii_leakage(preview, DEFAULT_PII_CONFIG.HASH_SALT)


class BlockAnalyzer:
    """Analyseur de blocs pour segmentation intelligente des CVs."""
    
    def __init__(self):
        self.logger = get_safe_logger(f"{__name__}.BlockAnalyzer", cfg=DEFAULT_PII_CONFIG)
        
        # Patterns pour la détection de frontières de blocs
        self._compile_boundary_patterns()
        
        # Patterns pour la détection d'éléments
        self._compile_element_patterns()
        
        # Compteurs pour les métriques
        self.stats = {
            "total_blocks_detected": 0,
            "blocks_by_type": {},
            "avg_block_size": 0.0,
            "boundary_types_used": {}
        }
    
    def _compile_boundary_patterns(self):
        """Compile les patterns de détection de frontières de blocs."""
        
        # Headers de sections (forts délimiteurs)
        self.section_headers = [
            re.compile(r'^\s*(?:EXPÉRIENCES?|EXPERIENCES?|EXPERIENCE)\s*(?:PROFESSIONNELLE?S?)?\s*$', re.IGNORECASE),
            re.compile(r'^\s*(?:FORMATIONS?|ÉDUCATIONS?|EDUCATIONS?)\s*$', re.IGNORECASE),
            re.compile(r'^\s*(?:CERTIFICATIONS?|DIPLÔMES?|DIPLOMES?)\s*$', re.IGNORECASE),
            re.compile(r'^\s*(?:COMPÉTENCES|COMPETENCES|SKILLS)\s*$', re.IGNORECASE),
            re.compile(r'^\s*(?:PROJETS?|PROJECTS?)\s*$', re.IGNORECASE)
        ]
        
        # Patterns de dates (délimiteurs moyens)
        self.date_patterns = [
            re.compile(r'\b(?:\d{1,2}[\/\-\.]\d{1,2}[\/\-\.]\d{2,4}|\d{4}(?:\s*[-–—]\s*\d{4})?|\d{1,2}[\/\-\.]\d{4})\b'),
            re.compile(r'\b(?:janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+\d{4}\b', re.IGNORECASE),
            re.compile(r'\b(?:jan|fév|mar|avr|mai|jun|jul|aoû|sep|oct|nov|déc)\.?\s+\d{4}\b', re.IGNORECASE),
            re.compile(r'\b(?:depuis|until|jusqu\'à|à\s+ce\s+jour)\b', re.IGNORECASE)
        ]
        
        # Patterns de puces et listes (délimiteurs faibles)
        self.bullet_patterns = [
            re.compile(r'^\s*[•\-–*▪▫‣⁃]\s+', re.UNICODE),
            re.compile(r'^\s*\d+[\.\)]\s+'),
            re.compile(r'^\s*[a-zA-Z]\)\s+')
        ]
        
        # Patterns d'indentation
        self.indentation_pattern = re.compile(r'^(\s*)')
    
    def _compile_element_patterns(self):
        """Compile les patterns pour la détection d'éléments dans les blocs."""
        
        # Titres/rôles professionnels
        self.professional_titles = [
            re.compile(r'\b(?:professeur|enseignant|directeur|manager|chef|responsable)\b', re.IGNORECASE),
            re.compile(r'\b(?:développeur|developer|ingénieur|engineer|analyst|analyste)\b', re.IGNORECASE),
            re.compile(r'\b(?:consultant|technicien|assistant|stagiaire|alternant)\b', re.IGNORECASE),
            re.compile(r'\b(?:lead|senior|junior|intern|stage)\b', re.IGNORECASE)
        ]
        
        # Noms d'organisations
        self.organization_indicators = [
            re.compile(r'\b(?:société|company|entreprise|corp|corporation|inc|ltd|sas|sarl)\b', re.IGNORECASE),
            re.compile(r'\b(?:université|university|école|ecole|lycée|institut|college)\b', re.IGNORECASE),
            re.compile(r'\b(?:consulting|conseil|services|solutions|technologies|tech)\b', re.IGNORECASE),
            re.compile(r'\b(?:group|groupe|holding|agency|agence|bureau|cabinet)\b', re.IGNORECASE)
        ]
        
        # Noms de diplômes/formations
        self.degree_patterns = [
            re.compile(r'\b(?:bachelor|licence|license|master|mba|phd|doctorat|thèse)\b', re.IGNORECASE),
            re.compile(r'\b(?:bac|bts|dut|but|cap|bep)\b', re.IGNORECASE),
            re.compile(r'\b(?:diplôme|degree|certification)\b', re.IGNORECASE)
        ]
    
    def detect_blocks(self, lines: List[str]) -> List[InformationBlock]:
        """
        Détecte les blocs d'information dans une liste de lignes.
        
        Args:
            lines: Liste des lignes du CV
            
        Returns:
            Liste des blocs détectés
        """
        if not lines:
            return []
        
        self.logger.info(f"BLOCK_DETECTION: starting | total_lines={len(lines)}")
        
        # Nettoyer les lignes
        clean_lines = [line.rstrip() for line in lines]
        
        # Détecter les frontières de blocs
        boundaries = self._detect_block_boundaries(clean_lines)
        
        # Créer les blocs à partir des frontières
        blocks = self._create_blocks_from_boundaries(clean_lines, boundaries)
        
        # Filtrer les blocs trop petits ou vides
        filtered_blocks = self._filter_blocks(blocks)
        
        # Mettre à jour les statistiques
        self._update_stats(filtered_blocks)
        
        self.logger.info(f"BLOCK_DETECTION: completed | blocks_detected={len(filtered_blocks)} | avg_size={self.stats['avg_block_size']:.1f}")
        
        return filtered_blocks
    
    def _detect_block_boundaries(self, lines: List[str]) -> List[int]:
        """Détecte les indices des frontières de blocs."""
        boundaries = [0]  # Toujours commencer au début
        
        for i, line in enumerate(lines):
            if not line.strip():  # Ligne vide
                continue
                
            # Frontière forte : headers de sections
            if self._is_section_header(line):
                boundaries.append(i)
                self.stats["boundary_types_used"]["section_header"] = self.stats["boundary_types_used"].get("section_header", 0) + 1
                self.logger.debug(f"BOUNDARY: section_header at line {i}")
                continue
            
            # Frontière moyenne : changement d'indentation significatif
            if i > 0 and self._is_indentation_change(lines[i-1], line):
                # Vérifier si c'est vraiment une nouvelle information
                if self._looks_like_new_item_start(line):
                    boundaries.append(i)
                    self.stats["boundary_types_used"]["indentation_change"] = self.stats["boundary_types_used"].get("indentation_change", 0) + 1
                    self.logger.debug(f"BOUNDARY: indentation_change at line {i}")
            
            # Frontière faible : pattern de date (nouveau item temporel)
            elif self._contains_date_pattern(line) and i > 0:
                # Ne pas créer de frontière si la ligne précédente a aussi des dates (même bloc)
                if not self._contains_date_pattern(lines[i-1]):
                    boundaries.append(i)
                    self.stats["boundary_types_used"]["date_pattern"] = self.stats["boundary_types_used"].get("date_pattern", 0) + 1
                    self.logger.debug(f"BOUNDARY: date_pattern at line {i}")
        
        # Ajouter la fin du document
        if len(lines) not in boundaries:
            boundaries.append(len(lines))
        
        # Trier et dédupliquer
        boundaries = sorted(set(boundaries))
        
        self.logger.debug(f"BOUNDARIES: detected {len(boundaries)-1} blocks | boundaries={boundaries}")
        return boundaries
    
    def _is_section_header(self, line: str) -> bool:
        """Vérifie si une ligne est un header de section."""
        line_stripped = line.strip()
        
        # Ligne trop courte ou trop longue pour être un header
        if len(line_stripped) < 3 or len(line_stripped) > 50:
            return False
        
        # Vérifier les patterns de headers connus
        for pattern in self.section_headers:
            if pattern.match(line_stripped):
                return True
        
        # Headers avec formatage spécial
        if line_stripped.isupper() and len(line_stripped.split()) <= 3:
            return True
            
        # Headers avec des caractères de décoration
        if re.match(r'^[\-=*]{3,}', line_stripped) or re.match(r'^.*[\-=*]{3,}$', line_stripped):
            return True
        
        return False
    
    def _is_indentation_change(self, prev_line: str, curr_line: str) -> bool:
        """Détecte un changement d'indentation significatif."""
        prev_indent = len(self.indentation_pattern.match(prev_line).group(1))
        curr_indent = len(self.indentation_pattern.match(curr_line).group(1))
        
        # Changement significatif d'indentation (>=2 espaces)
        return abs(prev_indent - curr_indent) >= 2
    
    def _looks_like_new_item_start(self, line: str) -> bool:
        """Vérifie si une ligne ressemble au début d'un nouvel item."""
        line_stripped = line.strip()
        
        # Lignes avec puces
        for pattern in self.bullet_patterns:
            if pattern.match(line):
                return True
        
        # Lignes avec des titres professionnels
        for pattern in self.professional_titles:
            if pattern.search(line_stripped):
                return True
        
        # Lignes avec des noms de diplômes
        for pattern in self.degree_patterns:
            if pattern.search(line_stripped):
                return True
        
        # Lignes avec des patterns temporels
        if self._contains_date_pattern(line_stripped):
            return True
        
        return False
    
    def _contains_date_pattern(self, line: str) -> bool:
        """Vérifie si une ligne contient un pattern de date."""
        for pattern in self.date_patterns:
            if pattern.search(line):
                return True
        return False
    
    def _create_blocks_from_boundaries(self, lines: List[str], boundaries: List[int]) -> List[InformationBlock]:
        """Crée les blocs d'information à partir des frontières détectées."""
        blocks = []
        
        for i in range(len(boundaries) - 1):
            start_idx = boundaries[i]
            end_idx = boundaries[i + 1]
            
            # Extraire les lignes du bloc
            block_lines = lines[start_idx:end_idx]
            
            # Nettoyer les lignes vides en début et fin
            while block_lines and not block_lines[0].strip():
                block_lines.pop(0)
                start_idx += 1
            
            while block_lines and not block_lines[-1].strip():
                block_lines.pop()
                end_idx -= 1
            
            # Créer le bloc si non vide
            if block_lines:
                block = InformationBlock(
                    lines=block_lines,
                    start_idx=start_idx,
                    end_idx=end_idx - 1
                )
                blocks.append(block)
                
                self.logger.debug(f"BLOCK_CREATED: lines {start_idx}-{end_idx-1} | size={len(block_lines)} | preview='{block.get_safe_preview(50)}'")
        
        return blocks
    
    def _filter_blocks(self, blocks: List[InformationBlock]) -> List[InformationBlock]:
        """Filtre les blocs selon des critères de qualité."""
        filtered = []
        
        for block in blocks:
            # Filtrer les blocs trop petits
            if len(block.lines) < 1:
                continue
            
            # Filtrer les blocs qui ne contiennent que des espaces ou des caractères spéciaux
            meaningful_content = any(re.search(r'[a-zA-Z0-9]', line) for line in block.lines)
            if not meaningful_content:
                continue
            
            # Filtrer les blocs qui sont juste des headers isolés
            if len(block.lines) == 1 and self._is_section_header(block.lines[0]):
                # Marquer comme header mais ne pas inclure dans les blocs de contenu
                block.block_type = BlockType.HEADER
                # On peut choisir de les garder ou non selon les besoins
                # continue
            
            filtered.append(block)
        
        self.logger.debug(f"BLOCK_FILTERING: {len(blocks)} → {len(filtered)} blocks after filtering")
        return filtered
    
    def _update_stats(self, blocks: List[InformationBlock]):
        """Met à jour les statistiques d'analyse."""
        self.stats["total_blocks_detected"] = len(blocks)
        
        if blocks:
            total_size = sum(block.get_line_count() for block in blocks)
            self.stats["avg_block_size"] = total_size / len(blocks)
            
            # Compter par type de bloc
            type_counts = {}
            for block in blocks:
                block_type = block.block_type.value
                type_counts[block_type] = type_counts.get(block_type, 0) + 1
            
            self.stats["blocks_by_type"] = type_counts
    
    def get_analysis_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques d'analyse."""
        return dict(self.stats)
    
    def analyze_block_coherence(self, block: InformationBlock) -> Dict[str, float]:
        """
        Analyse la cohérence interne d'un bloc.
        
        Returns:
            Dict avec scores de cohérence (0.0 à 1.0)
        """
        coherence_scores = {
            "temporal_coherence": 0.0,
            "semantic_coherence": 0.0,
            "structural_coherence": 0.0,
            "overall_coherence": 0.0
        }
        
        # Cohérence temporelle : présence et cohérence des dates
        date_lines = [line for line in block.lines if self._contains_date_pattern(line)]
        if date_lines:
            coherence_scores["temporal_coherence"] = min(1.0, len(date_lines) / max(len(block.lines), 1))
        
        # Cohérence sémantique : présence de termes liés
        professional_lines = sum(1 for line in block.lines 
                               if any(pattern.search(line) for pattern in self.professional_titles))
        org_lines = sum(1 for line in block.lines 
                       if any(pattern.search(line) for pattern in self.organization_indicators))
        
        semantic_score = (professional_lines + org_lines) / max(len(block.lines), 1)
        coherence_scores["semantic_coherence"] = min(1.0, semantic_score)
        
        # Cohérence structurelle : indentation et formatage consistant
        indentations = [len(self.indentation_pattern.match(line).group(1)) for line in block.lines]
        if indentations:
            indent_variance = max(indentations) - min(indentations)
            coherence_scores["structural_coherence"] = max(0.0, 1.0 - (indent_variance / 10.0))
        
        # Score global
        coherence_scores["overall_coherence"] = (
            coherence_scores["temporal_coherence"] * 0.4 +
            coherence_scores["semantic_coherence"] * 0.4 +
            coherence_scores["structural_coherence"] * 0.2
        )
        
        return coherence_scores


# Instance globale pour singleton
_block_analyzer = None

def get_block_analyzer() -> BlockAnalyzer:
    """Retourne l'instance singleton du BlockAnalyzer."""
    global _block_analyzer
    if _block_analyzer is None:
        _block_analyzer = BlockAnalyzer()
    return _block_analyzer


# Fonctions utilitaires
def analyze_cv_blocks(cv_lines: List[str]) -> List[InformationBlock]:
    """Analyse un CV en blocs cohérents."""
    analyzer = get_block_analyzer()
    return analyzer.detect_blocks(cv_lines)


def get_block_analysis_stats() -> Dict[str, Any]:
    """Retourne les statistiques de l'analyse de blocs."""
    analyzer = get_block_analyzer()
    return analyzer.get_analysis_stats()