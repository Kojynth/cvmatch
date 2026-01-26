"""
Soft Skills Fallback Lexical Extractor
======================================

Fallback lexical pour extraire soft skills quand IA < 0.40
avec header `Compétences/Soft skills` + bullet list détectés.
"""

import re
from typing import List, Dict, Set, Optional, Tuple, Any
from dataclasses import dataclass
from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)

@dataclass
class SoftSkillsExtractionResult:
    """Résultat d'extraction de soft skills"""
    skills: List[str]
    confidence: float
    extraction_method: str
    header_detected: Optional[str] = None
    bullet_patterns_found: List[str] = None
    raw_text: str = ""
    normalized_count: int = 0
    
    def __post_init__(self):
        if self.bullet_patterns_found is None:
            self.bullet_patterns_found = []
        self.normalized_count = len(self.skills)

# Soft skills lexicon multilingue
SOFT_SKILLS_LEXICON = {
    # Leadership & Management
    "leadership", "management", "gestion d'équipe", "team management", "encadrement",
    "delegation", "coordination", "direction", "supervision", "mentoring",
    
    # Communication
    "communication", "présentation", "négociation", "persuasion", "écoute",
    "communication écrite", "communication orale", "presentation skills",
    "public speaking", "storytelling", "empathie", "empathy",
    
    # Analytical & Problem Solving  
    "analyse", "analytical", "résolution de problèmes", "problem solving",
    "esprit critique", "critical thinking", "logique", "logical thinking",
    "créativité", "creativity", "innovation", "brainstorming",
    
    # Interpersonal
    "travail en équipe", "teamwork", "collaboration", "coopération", 
    "relations interpersonnelles", "networking", "diplomatie", "tact",
    "intelligence émotionnelle", "emotional intelligence", "bienveillance",
    
    # Adaptability
    "adaptabilité", "adaptability", "flexibilité", "flexibility", 
    "agilité", "agility", "résilience", "resilience", "polyvalence",
    "apprentissage rapide", "quick learning", "curiosité", "curiosity",
    
    # Organization
    "organisation", "organization", "planification", "planning", 
    "gestion du temps", "time management", "priorisation", "prioritization",
    "rigueur", "méthodologie", "methodology", "attention aux détails",
    
    # Initiative & Drive
    "initiative", "proactivité", "proactivity", "autonomie", "independence",
    "motivation", "détermination", "determination", "persévérance", "persistence",
    "ambition", "dynamisme", "energy", "passion",
    
    # Stress & Pressure
    "gestion du stress", "stress management", "résistance à la pression",
    "pressure resistance", "sang-froid", "calme", "sérénité"
}

# Header patterns pour soft skills  
SOFT_SKILLS_HEADER_PATTERNS = [
    # French
    r'\b(?:COMPÉTENCES?\s+(?:COMPORTEMENTALES?|TRANSVERSALES?|HUMAINES?))\b',
    r'\b(?:QUALITÉS?\s+(?:PERSONNELLES?|HUMAINES?))\b', 
    r'\b(?:SOFT\s+SKILLS?)\b',
    r'\b(?:SAVOIR[- ]ÊTRE)\b',
    r'\b(?:COMPÉTENCES?\s+RELATIONNELLES?)\b',
    
    # English  
    r'\b(?:SOFT\s+SKILLS?)\b',
    r'\b(?:INTERPERSONAL\s+SKILLS?)\b',
    r'\b(?:PERSONAL\s+(?:QUALITIES?|SKILLS?))\b',
    r'\b(?:BEHAVIORAL\s+SKILLS?)\b',
    r'\b(?:PEOPLE\s+SKILLS?)\b',
    
    # Generic
    r'\b(?:QUALITÉS?)\b(?=\s*[:;\-])',
    r'\b(?:ATOUTS?)\b(?=\s*[:;\-])',
    r'\b(?:TRAITS?)\b(?=\s*[:;\-])'
]

# Bullet patterns
BULLET_PATTERNS = [
    r'^\s*[•\-\+\*]\s+',           # • - + * bullets
    r'^\s*[\u2022\u2023\u2043]\s+', # Unicode bullets  
    r'^\s*\d+[\.\)]\s+',           # 1. 1) numbered
    r'^\s*[a-zA-Z][\.\)]\s+',      # a. b) lettered
    r'(?:^|\n)\s*[;,]\s*',         # ; , separators (beginning of line)
    r'[•\-\+\*]\s*\w+'             # Inline bullets
]

# Patterns à exclure (pas des soft skills)
EXCLUSION_PATTERNS = [
    # Technical skills
    r'\b(?:java|python|javascript|react|angular|sql|html|css)\b',
    r'\b(?:photoshop|excel|word|powerpoint|office)\b',
    r'\b(?:linux|windows|mac|ios|android)\b',
    
    # Hard skills
    r'\b(?:développement|programming|coding|database|serveur)\b',
    r'\b(?:comptabilité|accounting|finance|budget)\b',
    r'\b(?:vente|sales|marketing|commerce)\b',
    
    # Languages  
    r'\b(?:français|anglais|espagnol|allemand|italien)\b',
    r'\b(?:french|english|spanish|german|italian)\b',
    
    # Certifications
    r'\b(?:toefl|toeic|ielts|delf|dalf|cambridge)\b',
    
    # Too generic/short
    r'^\w{1,2}$',  # 1-2 letter words
    r'^\d+$'       # Pure numbers
]

# Enhanced patterns pour projet/technique (guardrails routing)
PROJECT_TECHNICAL_EXCLUSION_PATTERNS = [
    # Programming languages & frameworks
    r'\b(?:node\.?js|react\.?js|angular\.?js|vue\.?js|typescript|php|ruby|go|rust|swift|kotlin|scala)\b',
    r'\b(?:spring|django|flask|laravel|express|rails|asp\.?net|dotnet|\.net)\b',
    r'\b(?:jquery|bootstrap|tailwind|sass|scss|webpack|babel|npm|yarn|composer)\b',
    
    # Databases & tools
    r'\b(?:mysql|postgresql|mongodb|redis|elasticsearch|oracle|sqlite|firebase)\b',
    r'\b(?:docker|kubernetes|jenkins|git|github|gitlab|ansible|terraform|vagrant)\b',
    r'\b(?:aws|azure|gcp|heroku|digitalocean|cloudflare|cdn)\b',
    
    # Technical concepts
    r'\b(?:api|rest|graphql|microservices|devops|ci/cd|automation|testing|deployment)\b',
    r'\b(?:architecture|infrastructure|scalability|performance|optimization|refactoring)\b',
    r'\b(?:agile|scrum|kanban|sprint|backlog|jira|trello|confluence)\b',
    r'\b(?:server|serveur|client|frontend|backend|fullstack|stack technique)\b',
    
    # Project-specific terms
    r'\b(?:mise en place|implémentation|développement de|création de|réalisation de)\b',
    r'\b(?:projet|mission|livrable|livrables|milestone|deadline|planning)\b',
    r'\b(?:version|release|déploiement|production|staging|environnement)\b',
    r'\b(?:bug|debug|testing|unit test|integration|validation)\b',
    
    # Business/domain specific
    r'\b(?:erp|crm|cms|e-commerce|marketplace|b2b|b2c|saas|paas|iaas)\b',
    r'\b(?:fintech|healthtech|edtech|startup|scale-up|pme|tpe)\b',
    r'\b(?:roi|kpi|metrics|analytics|dashboard|reporting|bi)\b',
    
    # Technical skills disguised as soft skills
    r'\b(?:maîtrise de|expertise en|connaissance de|expérience avec)\s+[A-Z][\w\s]+\b',
    r'\b(?:technologies|outils|environnement|stack|plateforme|framework)\b',
    
    # File extensions and technical terms
    r'\b\w+\.\w{2,4}\b',  # file.ext patterns
    r'\b(?:https?://|www\.|\.com|\.fr|\.org)\b',  # URLs
    r'\b[A-Z]{2,}(?:[_-][A-Z0-9]+)*\b',  # Constants like API_KEY
    
    # Dates and versions
    r'\bv?\d+\.\d+(?:\.\d+)?\b',  # version numbers
    r'\b\d{4}[-/]\d{1,2}[-/]\d{1,2}\b',  # dates
    r'\b(?:version|v|release)\s*\d+\b'
]

# Patterns de lignes techniques complètes à exclure
TECHNICAL_LINE_PATTERNS = [
    # Lignes commençant par des éléments techniques
    r'^(?:développement|création|mise en place|implémentation|réalisation)\s+d[eu]',
    r'^(?:utilisation|usage|emploi|maîtrise)\s+d[eu]?\s+(?:technologies|outils|framework)',
    r'^(?:architecture|conception|design)\s+d[eu]',
    r'^(?:gestion|management)\s+d[eu]?\s+(?:projet|équipe|version|configuration)',
    
    # Lignes avec syntaxes techniques
    r'[{}()\[\]<>/\\]',  # Code syntax characters
    r'\w+\(\)',  # function calls
    r'\$\w+|@\w+|#\w+',  # Variables, mentions, hashtags
    
    # Lignes avec des listes de technologies
    r'(?:[A-Z][\w\s]*,\s*){2,}',  # Comma-separated tech lists
    r'(?:\w+\s*[&+]\s*\w+)',  # Tech combinations with & or +
]

class SoftSkillsFallbackExtractor:
    """Extracteur fallback lexical pour soft skills avec guardrails routing"""
    
    def __init__(self, ai_threshold: float = 0.40, max_skills: int = 20, 
                 enable_routing_guardrails: bool = True):
        self.ai_threshold = ai_threshold
        self.max_skills = max_skills
        self.enable_routing_guardrails = enable_routing_guardrails
        self.lexicon = SOFT_SKILLS_LEXICON
        self.header_patterns = SOFT_SKILLS_HEADER_PATTERNS
        self.bullet_patterns = BULLET_PATTERNS
        self.exclusions = EXCLUSION_PATTERNS
        self.project_technical_exclusions = PROJECT_TECHNICAL_EXCLUSION_PATTERNS
        self.technical_line_patterns = TECHNICAL_LINE_PATTERNS
        
        # Statistiques de routing
        self.routing_stats = {
            'lines_processed': 0,
            'lines_routed_away': 0,
            'technical_exclusions': 0,
            'project_line_exclusions': 0
        }
    
    def should_use_fallback(self, ai_score: float, text: str, title: str = "") -> bool:
        """
        Détermine si le fallback lexical doit être utilisé
        
        Conditions: IA < 0.40 ET header soft skills détecté ET bullet list présente
        """
        if ai_score >= self.ai_threshold:
            return False
        
        full_text = text + " " + title
        
        # Check for soft skills header
        has_header = self._detect_soft_skills_header(full_text)
        
        if not has_header:
            return False
        
        # Check for bullet list structure
        has_bullets = self._detect_bullet_structure(text)
        
        should_fallback = has_header and has_bullets
        
        if should_fallback:
            logger.info(f"SOFT_SKILLS_FALLBACK: triggered with ai_score={ai_score:.3f} < {self.ai_threshold}, header_detected={has_header}, bullets_detected={has_bullets}")
        
        return should_fallback
    
    def apply_routing_guardrails(self, text: str, title: str = "") -> Dict[str, Any]:
        """
        Applique les guardrails de routing pour éviter les fausses extractions.
        
        Args:
            text: Texte de la section
            title: Titre de la section
            
        Returns:
            Dict avec should_route_away, reasons, filtered_text
        """
        if not self.enable_routing_guardrails:
            return {
                'should_route_away': False,
                'reasons': [],
                'filtered_text': text,
                'routing_decision': 'guardrails_disabled'
            }
        
        full_text = text + " " + title
        routing_reasons = []
        
        # 1. Vérifier si le contenu est principalement technique
        tech_density = self._calculate_technical_density(full_text)
        if tech_density > 0.6:  # Plus de 60% de contenu technique
            routing_reasons.append(f'high_technical_density_{tech_density:.2f}')
        
        # 2. Vérifier la présence de lignes techniques complètes
        technical_lines = self._detect_technical_lines(text)
        if len(technical_lines) > len(text.split('\n')) * 0.5:  # Plus de 50% des lignes
            routing_reasons.append(f'excessive_technical_lines_{len(technical_lines)}')
        
        # 3. Vérifier les patterns de projet/mission
        project_indicators = self._detect_project_patterns(full_text)
        if len(project_indicators) > 3:  # Plus de 3 indicateurs de projet
            routing_reasons.append(f'project_content_detected_{len(project_indicators)}')
        
        # 4. Filtrer le texte des éléments techniques
        filtered_text = self._filter_technical_content(text)
        content_reduction = 1 - (len(filtered_text) / max(len(text), 1))
        
        if content_reduction > 0.7:  # Plus de 70% du contenu filtré
            routing_reasons.append(f'excessive_technical_filtering_{content_reduction:.2f}')
        
        should_route_away = len(routing_reasons) > 0
        
        # Log des décisions de routing
        if should_route_away:
            logger.info(f"SOFT_SKILLS_ROUTING: routing_away | reasons={routing_reasons}")
            self.routing_stats['lines_routed_away'] += 1
        
        self.routing_stats['lines_processed'] += 1
        
        return {
            'should_route_away': should_route_away,
            'reasons': routing_reasons,
            'filtered_text': filtered_text,
            'technical_density': tech_density,
            'project_indicators': project_indicators,
            'routing_decision': 'routed_away' if should_route_away else 'allowed'
        }
    
    def _calculate_technical_density(self, text: str) -> float:
        """Calcule la densité de contenu technique dans le texte."""
        if not text:
            return 0.0
        
        words = text.lower().split()
        technical_matches = 0
        
        for word in words:
            for pattern in self.project_technical_exclusions:
                if re.search(pattern, word, re.IGNORECASE):
                    technical_matches += 1
                    break  # Éviter le double comptage
        
        return technical_matches / len(words) if words else 0.0
    
    def _detect_technical_lines(self, text: str) -> List[str]:
        """Détecte les lignes à contenu principalement technique."""
        lines = text.split('\n')
        technical_lines = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Vérifier contre les patterns de lignes techniques
            for pattern in self.technical_line_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    technical_lines.append(line)
                    break
        
        return technical_lines
    
    def _detect_project_patterns(self, text: str) -> List[str]:
        """Détecte les patterns indiquant un contenu de projet/mission."""
        project_indicators = []
        text_lower = text.lower()
        
        # Patterns spécifiques aux projets/missions
        project_keywords = [
            'projet', 'mission', 'livrable', 'milestone', 'planning',
            'développement de', 'mise en place', 'réalisation de',
            'implémentation', 'création de', 'architecture',
            'stack technique', 'environnement', 'technologies'
        ]
        
        for keyword in project_keywords:
            if keyword in text_lower:
                project_indicators.append(keyword)
        
        return project_indicators
    
    def _filter_technical_content(self, text: str) -> str:
        """Filtre le contenu technique d'un texte."""
        filtered_lines = []
        
        for line in text.split('\n'):
            line = line.strip()
            if not line:
                continue
            
            # Vérifier si la ligne doit être exclue
            should_exclude = False
            
            # Vérifier contre les patterns de lignes techniques
            for pattern in self.technical_line_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    should_exclude = True
                    break
            
            if not should_exclude:
                # Filtrer les mots techniques dans la ligne
                words = line.split()
                filtered_words = []
                
                for word in words:
                    word_technical = False
                    for pattern in self.project_technical_exclusions:
                        if re.search(pattern, word, re.IGNORECASE):
                            word_technical = True
                            break
                    
                    if not word_technical:
                        filtered_words.append(word)
                
                if filtered_words:  # Garder seulement les lignes non vides
                    filtered_lines.append(' '.join(filtered_words))
        
        return '\n'.join(filtered_lines)
    
    def get_routing_stats(self) -> Dict[str, Any]:
        """Retourne les statistiques de routing."""
        total_processed = self.routing_stats['lines_processed']
        routing_rate = (
            self.routing_stats['lines_routed_away'] / total_processed 
            if total_processed > 0 else 0.0
        )
        
        return {
            **self.routing_stats,
            'routing_rate': routing_rate,
            'guardrails_enabled': self.enable_routing_guardrails
        }
    
    def extract_soft_skills(self, text: str, title: str = "", 
                           ai_score: float = 0.0) -> SoftSkillsExtractionResult:
        """
        Extrait les soft skills avec fallback lexical
        
        Args:
            text: Texte de la section
            title: Titre de la section  
            ai_score: Score IA (pour validation threshold)
            
        Returns:
            SoftSkillsExtractionResult avec skills extraites
        """
        full_text = text + " " + title
        
        # Apply routing guardrails before processing
        routing_result = self.apply_routing_guardrails(text, title)
        if routing_result['should_route_away']:
            logger.info(f"SOFT_SKILLS_EXTRACT: routing_guardrails_blocked | reasons={routing_result['reasons']}")
            return SoftSkillsExtractionResult(
                skills=[],
                confidence=0.0,
                extraction_method="blocked_by_routing_guardrails",
                header_detected=None,
                bullet_patterns_found=[],
                raw_text=text[:100] + "..." if len(text) > 100 else text,
                normalized_count=0
            )
        
        # Use filtered text for extraction if guardrails are enabled
        extraction_text = routing_result['filtered_text'] if self.enable_routing_guardrails else text
        
        # Detect header
        detected_header = self._extract_header_text(full_text)
        
        # Extract bullet patterns
        bullet_patterns_found = self._find_bullet_patterns(extraction_text)
        
        # Extract and normalize skills  
        raw_skills = self._extract_skills_from_bullets(extraction_text)
        normalized_skills = self._normalize_and_deduplicate(raw_skills)
        
        # Filter against lexicon and exclusions
        filtered_skills = self._filter_against_lexicon(normalized_skills)
        
        # Limit to max skills
        final_skills = filtered_skills[:self.max_skills]
        
        # Calculate confidence
        confidence = self._calculate_extraction_confidence(
            final_skills, bullet_patterns_found, detected_header, ai_score
        )
        
        extraction_method = "fallback_lexical" if ai_score < self.ai_threshold else "hybrid"
        
        return SoftSkillsExtractionResult(
            skills=final_skills,
            confidence=confidence,
            extraction_method=extraction_method,
            header_detected=detected_header,
            bullet_patterns_found=bullet_patterns_found,
            raw_text=text[:200] + "..." if len(text) > 200 else text,
            normalized_count=len(final_skills)
        )
    
    def _detect_soft_skills_header(self, text: str) -> bool:
        """Détecte la présence d'un header soft skills"""
        text_upper = text.upper()
        
        for pattern in self.header_patterns:
            if re.search(pattern, text_upper, re.IGNORECASE | re.MULTILINE):
                return True
        
        return False
    
    def _extract_header_text(self, text: str) -> Optional[str]:
        """Extrait le texte du header soft skills détecté"""
        text_upper = text.upper()
        
        for pattern in self.header_patterns:
            match = re.search(pattern, text_upper, re.IGNORECASE | re.MULTILINE)
            if match:
                return match.group(0)
        
        return None
    
    def _detect_bullet_structure(self, text: str) -> bool:
        """Détecte la présence d'une structure en bullet list"""
        bullet_count = 0
        
        for pattern in self.bullet_patterns:
            matches = re.findall(pattern, text, re.MULTILINE)
            bullet_count += len(matches)
        
        # Need at least 2 bullet items to consider it a list
        return bullet_count >= 2
    
    def _find_bullet_patterns(self, text: str) -> List[str]:
        """Trouve les patterns de bullets utilisés"""
        found_patterns = []
        
        for pattern in self.bullet_patterns:
            if re.search(pattern, text, re.MULTILINE):
                found_patterns.append(pattern)
        
        return found_patterns
    
    def _extract_skills_from_bullets(self, text: str) -> List[str]:
        """Extrait les skills des bullet points"""
        skills = []
        
        # Split by lines and process each
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Remove bullet markers
            cleaned_line = self._remove_bullet_markers(line)
            
            if not cleaned_line:
                continue
            
            # Split by common separators within lines  
            line_skills = self._split_line_skills(cleaned_line)
            skills.extend(line_skills)
        
        return skills
    
    def _remove_bullet_markers(self, line: str) -> str:
        """Supprime les marqueurs de bullets d'une ligne"""
        # Remove leading bullet patterns
        for pattern in self.bullet_patterns:
            line = re.sub(pattern, '', line).strip()
        
        # Remove trailing punctuation
        line = re.sub(r'[,;.]+$', '', line).strip()
        
        return line
    
    def _split_line_skills(self, line: str) -> List[str]:
        """Split une ligne en skills individuelles"""
        # Split by separators
        separators = [',', ';', '·', '•', '-', '|']
        
        skills = [line]  # Start with full line
        
        for sep in separators:
            new_skills = []
            for skill in skills:
                new_skills.extend([s.strip() for s in skill.split(sep)])
            skills = new_skills
        
        # Filter out empty and very short skills
        return [skill for skill in skills if skill and len(skill.strip()) > 2]
    
    def _normalize_and_deduplicate(self, skills: List[str]) -> List[str]:
        """Normalise et déduplique les skills"""
        normalized = set()
        
        for skill in skills:
            # Normalize: lowercase + trim + remove extra spaces
            norm_skill = re.sub(r'\s+', ' ', skill.lower().strip())
            
            # Skip if too short or empty
            if len(norm_skill) < 3:
                continue
            
            # Skip if matches exclusion patterns  
            if self._matches_exclusions(norm_skill):
                continue
            
            normalized.add(norm_skill)
        
        return sorted(list(normalized))
    
    def _matches_exclusions(self, skill: str) -> bool:
        """Vérifie si une skill matche les patterns d'exclusion (basique + enhanced)"""
        # Vérifier contre les exclusions basiques
        for pattern in self.exclusions:
            if re.search(pattern, skill, re.IGNORECASE):
                self.routing_stats['technical_exclusions'] += 1
                return True
        
        # Vérifier contre les patterns techniques/projets renforcés si activés
        if self.enable_routing_guardrails:
            for pattern in self.project_technical_exclusions:
                if re.search(pattern, skill, re.IGNORECASE):
                    self.routing_stats['technical_exclusions'] += 1
                    logger.debug(f"SOFT_SKILLS_EXCLUSION: technical_pattern_matched | skill='{skill}' pattern='{pattern}'")
                    return True
        
        return False
    
    def _filter_against_lexicon(self, skills: List[str]) -> List[str]:
        """Filtre les skills contre le lexicon de soft skills"""
        filtered = []
        
        for skill in skills:
            # Check exact match in lexicon
            if skill.lower() in [lex_skill.lower() for lex_skill in self.lexicon]:
                filtered.append(skill)
                continue
            
            # Check partial match (skill contains lexicon term or vice versa)
            for lex_skill in self.lexicon:
                lex_lower = lex_skill.lower()
                skill_lower = skill.lower()
                
                # Partial match (either direction, min 4 chars)
                if len(lex_lower) >= 4 and (
                    lex_lower in skill_lower or 
                    skill_lower in lex_lower
                ):
                    filtered.append(skill)
                    break
            else:
                # If no lexicon match, check if it "looks like" a soft skill
                if self._looks_like_soft_skill(skill):
                    filtered.append(skill)
        
        return filtered
    
    def _looks_like_soft_skill(self, skill: str) -> bool:
        """Heuristique pour déterminer si ça ressemble à une soft skill"""
        skill_lower = skill.lower()
        
        # Positive indicators
        positive_indicators = [
            "capacité", "ability", "aptitude", "compétence", 
            "sens", "esprit", "gestion", "management",
            "travail", "work", "communication", "relation"
        ]
        
        # Check if contains positive indicators
        has_positive = any(indicator in skill_lower for indicator in positive_indicators)
        
        # Length check (reasonable soft skill length)
        reasonable_length = 4 <= len(skill_lower) <= 50
        
        # Not purely technical (basic heuristic)
        not_technical = not re.search(r'\b(?:\.js|\.py|\.exe|http|www|@|#)\b', skill_lower)
        
        return has_positive and reasonable_length and not_technical
    
    def _calculate_extraction_confidence(self, skills: List[str], 
                                       bullet_patterns: List[str],
                                       header: Optional[str],
                                       ai_score: float) -> float:
        """Calcule la confiance de l'extraction"""
        base_confidence = 0.6  # Base for lexical extraction
        
        # Bonus pour header spécialisé
        if header:
            base_confidence += 0.1
        
        # Bonus pour structure bullets riche
        if len(bullet_patterns) > 1:
            base_confidence += 0.1
        
        # Bonus pour nombre de skills raisonnable
        skills_count = len(skills)
        if 3 <= skills_count <= 10:  # Sweet spot
            base_confidence += 0.1
        elif skills_count > 10:  # Many skills found
            base_confidence += 0.05
        
        # Pénalité si très peu de skills
        if skills_count < 2:
            base_confidence -= 0.2
        
        # Léger bonus si score AI pas complètement nul
        if ai_score > 0.1:
            base_confidence += 0.05
        
        return max(0.3, min(1.0, base_confidence))


# Factory functions
def extract_soft_skills_with_fallback(text: str, title: str = "", 
                                     ai_score: float = 0.0,
                                     ai_threshold: float = 0.40) -> Optional[SoftSkillsExtractionResult]:
    """
    Factory function pour extraction soft skills avec fallback
    
    Returns:
        SoftSkillsExtractionResult si fallback applicable, None sinon
    """
    extractor = SoftSkillsFallbackExtractor(ai_threshold=ai_threshold)
    
    if not extractor.should_use_fallback(ai_score, text, title):
        return None
    
    return extractor.extract_soft_skills(text, title, ai_score)


def detect_soft_skills_section(text: str, title: str = "") -> bool:
    """
    Détecte si une section semble contenir des soft skills
    
    Returns:
        True si détection positive
    """
    extractor = SoftSkillsFallbackExtractor()
    full_text = text + " " + title
    
    has_header = extractor._detect_soft_skills_header(full_text)
    has_bullets = extractor._detect_bullet_structure(text)
    
    return has_header or has_bullets


def normalize_soft_skills_list(skills: List[str]) -> List[str]:
    """
    Normalise une liste de soft skills (lowercase, dedupe, filter)
    
    Returns:
        Liste normalisée et filtrée
    """
    extractor = SoftSkillsFallbackExtractor()
    normalized = extractor._normalize_and_deduplicate(skills)
    return extractor._filter_against_lexicon(normalized)
