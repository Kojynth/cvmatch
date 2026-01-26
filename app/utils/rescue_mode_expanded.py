"""
RESCUE Mode Expansion
====================

RESCUE mode étendu avec nouveaux déclencheurs:
- experiences.count == 0 APRÈS PHASE1  
- header-guard suppressed > 2 windows
- Sliding window (±6 lignes) avec seuils relâchés + overrides
"""

import re
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG
from .routing_decision import HeuristicOverrideEngine, RoutingDecision

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)

class RescueTrigger(Enum):
    """Types de déclencheurs RESCUE"""
    ZERO_EXPERIENCES = "zero_experiences_after_phase1"
    HEADER_GUARD_SUPPRESSED = "header_guard_suppressed_windows"
    LOW_EXTRACTION_YIELD = "low_extraction_yield"
    MANUAL_TRIGGER = "manual_trigger"

@dataclass  
class RescueContext:
    """Contexte pour une session RESCUE"""
    trigger: RescueTrigger
    document_lines: List[str]
    phase1_results: Dict[str, Any] = field(default_factory=dict)
    suppressed_windows: List[Tuple[int, int, str]] = field(default_factory=list)
    employment_patterns_found: List[Tuple[int, str]] = field(default_factory=list)
    rescue_extractions: List[Dict[str, Any]] = field(default_factory=list)
    success_rate: float = 0.0

@dataclass
class RescueWindow:
    """Fenêtre de recherche RESCUE"""
    start_line: int
    end_line: int
    center_line: int
    employment_pattern: str
    confidence: float
    extracted_data: Optional[Dict[str, Any]] = None

class RescueModeEngine:
    """Engine pour RESCUE mode avec déclencheurs étendus"""
    
    def __init__(self, window_size: int = 6, relaxed_threshold: float = 0.25):
        self.window_size = window_size  # ±6 lignes
        self.relaxed_threshold = relaxed_threshold
        self.override_engine = HeuristicOverrideEngine(ml_gate_soft=0.25, ml_gate_min=0.30)
        
        # Employment patterns étendus pour RESCUE
        self.employment_patterns = [
            # Core employment terms
            r'\b(?:développeur|developer|ingénieur|engineer|consultant|analyste)\b',
            r'\b(?:manager|chef|lead|senior|junior|assistant|coordinator)\b', 
            r'\b(?:stagiaire|intern|stage|alternance|apprentissage)\b',
            
            # Contract types
            r'\b(?:CDI|CDD|freelance|contractuel|intérim|consultant)\b',
            
            # Company indicators  
            r'\b(?:chez|at|@)\s+[A-Z][a-zA-Z]+',
            r'\b[A-Z][a-zA-Z]*\s+(?:SA|SAS|SARL|Inc|Ltd|Corp)\b',
            r'\b(?:société|entreprise|company|startup|cabinet)\b',
            
            # Activity indicators
            r'\b(?:responsable|en charge|missions?|tâches|projets?)\b',
            r'\b(?:développement|gestion|coordination|encadrement)\b',
            
            # Date + activity patterns
            r'\d{4}\s*[-–—]\s*(?:\d{4}|présent).*(?:développement|projet|gestion)',
            r'(?:depuis|from|pendant)\s+\d+.*(?:mois|ans|years)'
        ]
    
    def should_trigger_rescue(self, phase1_results: Dict[str, Any],
                             suppressed_windows: List[Tuple[int, int, str]] = None) -> Tuple[bool, RescueTrigger]:
        """
        Détermine si RESCUE mode doit être déclenché
        
        Returns:
            Tuple (should_trigger, trigger_reason)
        """
        if suppressed_windows is None:
            suppressed_windows = []
            
        # Trigger 1: Zero experiences après PHASE1
        experiences = phase1_results.get('experiences', [])
        if len(experiences) == 0:
            logger.warning(f"RESCUE_TRIGGER: zero_experiences_after_phase1, experiences_count={len(experiences)}")
            return True, RescueTrigger.ZERO_EXPERIENCES
        
        # Trigger 2: Header-guard suppressed > 2 windows
        if len(suppressed_windows) > 2:
            logger.warning(f"RESCUE_TRIGGER: header_guard_suppressed > 2 windows, suppressed_count={len(suppressed_windows)}")
            return True, RescueTrigger.HEADER_GUARD_SUPPRESSED
        
        # Trigger 3: Low extraction yield (few total sections)
        total_sections = sum(len(phase1_results.get(section, [])) for section in ['experiences', 'education', 'projects', 'skills'])
        if total_sections < 3:
            logger.warning(f"RESCUE_TRIGGER: low_extraction_yield, total_sections={total_sections} < 3")
            return True, RescueTrigger.LOW_EXTRACTION_YIELD
        
        return False, None
    
    def run_rescue_extraction(self, context: RescueContext) -> Dict[str, Any]:
        """
        Lance l'extraction RESCUE avec sliding windows
        
        Args:
            context: Contexte RESCUE avec trigger et données
            
        Returns:
            Dict avec extractions RESCUE
        """
        logger.info(f"RESCUE_MODE: starting with trigger={context.trigger.value}")
        
        # Step 1: Find all employment patterns in document
        employment_locations = self._find_employment_patterns(context.document_lines)
        context.employment_patterns_found = employment_locations
        
        logger.info(f"RESCUE_PATTERNS: found {len(employment_locations)} employment patterns")
        
        # Step 2: Create sliding windows around patterns
        rescue_windows = self._create_rescue_windows(employment_locations, context.document_lines)
        
        logger.info(f"RESCUE_WINDOWS: created {len(rescue_windows)} sliding windows")
        
        # Step 3: Extract from each window with relaxed thresholds  
        rescue_extractions = []
        for window in rescue_windows:
            extraction = self._extract_from_rescue_window(window, context.document_lines)
            if extraction:
                rescue_extractions.append(extraction)
                context.rescue_extractions.append(extraction)
        
        # Step 4: Apply override logic to rescued data
        enriched_extractions = self._apply_rescue_overrides(rescue_extractions)
        
        # Step 5: Calculate success rate
        context.success_rate = len(enriched_extractions) / max(1, len(rescue_windows))
        
        logger.info(f"RESCUE_COMPLETE: extracted {len(enriched_extractions)}/{len(rescue_windows)} windows, success_rate={context.success_rate:.2f}")
        
        return {
            'trigger': context.trigger.value,
            'rescue_experiences': enriched_extractions,
            'patterns_found': len(employment_locations),
            'windows_processed': len(rescue_windows),
            'success_rate': context.success_rate,
            'extraction_method': 'rescue_mode'
        }
    
    def _find_employment_patterns(self, lines: List[str]) -> List[Tuple[int, str]]:
        """Trouve tous les patterns d'emploi dans le document"""
        employment_locations = []
        
        for line_idx, line in enumerate(lines):
            line_lower = line.lower().strip()
            if not line_lower:
                continue
            
            for pattern in self.employment_patterns:
                matches = re.finditer(pattern, line, re.IGNORECASE)
                for match in matches:
                    employment_locations.append((line_idx, match.group(0)))
                    logger.debug(f"RESCUE_PATTERN: line {line_idx}: '{match.group(0)}' in '{line[:50]}'")
        
        # Deduplicate by line index
        seen_lines = set()
        deduplicated = []
        for line_idx, pattern in employment_locations:
            if line_idx not in seen_lines:
                deduplicated.append((line_idx, pattern))
                seen_lines.add(line_idx)
        
        return deduplicated
    
    def _create_rescue_windows(self, employment_locations: List[Tuple[int, str]], 
                              lines: List[str]) -> List[RescueWindow]:
        """Crée les fenêtres sliding autour des patterns d'emploi"""
        windows = []
        
        for line_idx, pattern in employment_locations:
            # Create ±window_size window
            start = max(0, line_idx - self.window_size)
            end = min(len(lines), line_idx + self.window_size + 1)
            
            # Calculate confidence based on pattern strength and context
            confidence = self._calculate_pattern_confidence(pattern, line_idx, lines)
            
            window = RescueWindow(
                start_line=start,
                end_line=end, 
                center_line=line_idx,
                employment_pattern=pattern,
                confidence=confidence
            )
            
            windows.append(window)
        
        # Sort by confidence descending
        windows.sort(key=lambda w: w.confidence, reverse=True)
        
        return windows
    
    def _calculate_pattern_confidence(self, pattern: str, line_idx: int, 
                                    lines: List[str]) -> float:
        """Calcule la confiance d'un pattern d'emploi"""
        base_confidence = 0.5
        
        line = lines[line_idx].lower()
        
        # Bonus pour patterns spécifiques
        if any(term in pattern.lower() for term in ['développeur', 'ingénieur', 'manager']):
            base_confidence += 0.2
        
        # Bonus pour contexte de dates
        date_patterns = [r'\d{4}', r'(?:mois|ans|years)', r'(?:depuis|from|pendant)']
        if any(re.search(dp, line) for dp in date_patterns):
            base_confidence += 0.15
        
        # Bonus pour contexte d'organisation
        org_patterns = [r'chez|at|@', r'SA|SARL|Inc|Ltd', r'société|company']
        if any(re.search(op, line) for op in org_patterns):
            base_confidence += 0.1
        
        # Bonus pour contexte d'activité  
        activity_patterns = [r'missions?|tâches|projets?', r'responsable|en charge', r'équipe|team']
        if any(re.search(ap, line) for ap in activity_patterns):
            base_confidence += 0.1
        
        # Malus si ligne très courte ou peu d'informations
        if len(line.strip()) < 20:
            base_confidence -= 0.1
        
        return max(0.2, min(1.0, base_confidence))
    
    def _extract_from_rescue_window(self, window: RescueWindow, 
                                   lines: List[str]) -> Optional[Dict[str, Any]]:
        """Extrait les données d'une fenêtre RESCUE"""
        window_lines = lines[window.start_line:window.end_line]
        window_text = '\n'.join(window_lines)
        
        if not window_text.strip():
            return None
        
        # Basic extraction avec seuils relâchés
        extraction = {
            'text': window_text,
            'title': self._extract_title(window_lines),
            'organization': self._extract_organization(window_lines),
            'dates': self._extract_dates(window_lines),
            'description': self._extract_description(window_lines),
            'window_info': {
                'start_line': window.start_line,
                'end_line': window.end_line,
                'center_line': window.center_line,
                'pattern': window.employment_pattern,
                'confidence': window.confidence
            },
            'extraction_method': 'rescue_sliding_window'
        }
        
        # Filter out empty extractions
        if not any([extraction['title'], extraction['organization'], extraction['dates']]):
            logger.debug(f"RESCUE_SKIP: window {window.start_line}-{window.end_line} has no structured data")
            return None
        
        return extraction
    
    def _extract_title(self, window_lines: List[str]) -> Optional[str]:
        """Extrait le titre/rôle d'une fenêtre"""
        title_patterns = [
            r'\b(?:développeur|developer|ingénieur|engineer|consultant|analyste)\s+\w+',
            r'\b(?:manager|chef|lead|senior|junior)\s+\w+',
            r'\b(?:stagiaire|intern)\s+\w+',
            r'\b[A-Z][a-zA-Z]+\s+(?:développeur|developer|ingénieur|engineer)'
        ]
        
        for line in window_lines:
            line_stripped = line.strip()
            if len(line_stripped) < 5:
                continue
                
            for pattern in title_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    return match.group(0).strip()
        
        return None
    
    def _extract_organization(self, window_lines: List[str]) -> Optional[str]:
        """Extrait l'organisation d'une fenêtre"""
        org_patterns = [
            r'(?:chez|at|@)\s+([A-Z][a-zA-Z\s]+)',
            r'\b([A-Z][a-zA-Z\s]*(?:SA|SAS|SARL|Inc|Ltd|Corp))\b',
            r'(?:société|entreprise|company)\s+([A-Z][a-zA-Z\s]+)'
        ]
        
        for line in window_lines:
            for pattern in org_patterns:
                match = re.search(pattern, line)
                if match:
                    return match.group(1).strip()
        
        return None
    
    def _extract_dates(self, window_lines: List[str]) -> Optional[str]:
        """Extrait les dates d'une fenêtre"""
        date_patterns = [
            r'\d{4}\s*[-–—]\s*(?:\d{4}|présent|present|actuel)',
            r'(?:depuis|from|pendant)\s+\d+\s*(?:mois|ans|years)',
            r'(?:janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+\d{4}',
            r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{4}'
        ]
        
        for line in window_lines:
            for pattern in date_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    return match.group(0).strip()
        
        return None
    
    def _extract_description(self, window_lines: List[str]) -> Optional[str]:
        """Extrait la description d'une fenêtre"""
        # Take all lines except very short ones
        desc_lines = []
        
        for line in window_lines:
            line_stripped = line.strip()
            if len(line_stripped) > 10:  # Substantial content
                desc_lines.append(line_stripped)
        
        if desc_lines:
            return '\n'.join(desc_lines[:3])  # Max 3 lines
        
        return None
    
    def _apply_rescue_overrides(self, extractions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Applique les overrides heuristiques aux données RESCUE"""
        enriched = []
        
        for extraction in extractions:
            text = extraction.get('text', '')
            title = extraction.get('title', '')
            
            # Apply routing decision with relaxed thresholds
            routing_decision = self.override_engine.should_override(
                'experience', text, title, ai_score=self.relaxed_threshold
            )
            
            if routing_decision:
                extraction['routing_decision'] = {
                    'section': routing_decision.final_section,
                    'override_reason': routing_decision.override_reason,
                    'confidence': routing_decision.confidence,
                    'signals': dict(routing_decision.source_signals)
                }
                enriched.append(extraction)
                logger.debug(f"RESCUE_OVERRIDE: applied {routing_decision.override_reason}")
            else:
                # Keep extraction même sans override si confiance de fenêtre suffisante
                window_confidence = extraction.get('window_info', {}).get('confidence', 0)
                if window_confidence >= 0.6:
                    extraction['routing_decision'] = {
                        'section': 'experience',
                        'override_reason': 'rescue_window_confidence',
                        'confidence': window_confidence,
                        'signals': {}
                    }
                    enriched.append(extraction)
        
        return enriched


# Factory functions
def check_rescue_trigger(phase1_results: Dict[str, Any],
                        suppressed_windows: List[Tuple[int, int, str]] = None) -> Tuple[bool, Optional[RescueTrigger]]:
    """
    Factory function pour vérifier si RESCUE doit être déclenché
    
    Returns:
        Tuple (should_trigger, trigger_type)
    """
    engine = RescueModeEngine()
    return engine.should_trigger_rescue(phase1_results, suppressed_windows)


def run_rescue_extraction_on_document(document_lines: List[str], 
                                     phase1_results: Dict[str, Any],
                                     trigger: RescueTrigger,
                                     suppressed_windows: List[Tuple[int, int, str]] = None) -> Dict[str, Any]:
    """
    Factory function pour lancer extraction RESCUE complète
    
    Returns:
        Dict avec résultats RESCUE
    """
    if suppressed_windows is None:
        suppressed_windows = []
    
    context = RescueContext(
        trigger=trigger,
        document_lines=document_lines,
        phase1_results=phase1_results,
        suppressed_windows=suppressed_windows
    )
    
    engine = RescueModeEngine()
    return engine.run_rescue_extraction(context)


def merge_rescue_with_phase1(phase1_results: Dict[str, Any], 
                            rescue_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merge les résultats RESCUE avec ceux de PHASE1
    
    Returns:
        Dict merged avec priorité aux résultats RESCUE
    """
    merged = phase1_results.copy()
    
    # Add rescue experiences to existing ones
    existing_experiences = merged.get('experiences', [])
    rescue_experiences = rescue_results.get('rescue_experiences', [])
    
    # Merge experiences with deduplication by text similarity
    all_experiences = existing_experiences.copy()
    
    for rescue_exp in rescue_experiences:
        rescue_text = rescue_exp.get('text', '').lower()
        
        # Check if similar experience already exists
        is_duplicate = False
        for existing_exp in existing_experiences:
            existing_text = existing_exp.get('text', '').lower()
            
            # Simple similarity check (common words > 50%)
            rescue_words = set(rescue_text.split())
            existing_words = set(existing_text.split())
            
            if len(rescue_words) > 0 and len(existing_words) > 0:
                common_words = rescue_words.intersection(existing_words)
                similarity = len(common_words) / max(len(rescue_words), len(existing_words))
                
                if similarity > 0.5:
                    is_duplicate = True
                    break
        
        if not is_duplicate:
            all_experiences.append(rescue_exp)
            logger.info(f"RESCUE_MERGED: added rescue experience with {len(rescue_exp.get('text', '').split())} words")
    
    merged['experiences'] = all_experiences
    
    # Add rescue metadata
    merged['rescue_info'] = {
        'triggered': True,
        'trigger': rescue_results.get('trigger'),
        'patterns_found': rescue_results.get('patterns_found', 0),
        'windows_processed': rescue_results.get('windows_processed', 0),
        'success_rate': rescue_results.get('success_rate', 0.0),
        'added_experiences': len(all_experiences) - len(existing_experiences)
    }
    
    return merged
