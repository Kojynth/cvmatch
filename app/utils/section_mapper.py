"""
Mappeur intelligent pour les fenêtres de sections avec détection header-aware.
Spécialement optimisé pour l'extraction des expériences avec bornage dynamique.
"""

import re
import unicodedata
from typing import List, Tuple, Optional, Dict
from loguru import logger

# Configuration des seuils pour les guards anti-contamination
DENSITY_MIN_EXPERIENCE = 0.18
DATE_ROLE_MAX_GAP = 3
DATE_COMPANY_MAX_GAP = 4

# Headers à exclure des fenêtres d'expériences (multi-langues, normalisés NFC + casefold)
DISALLOW_HEADERS_EXPERIENCE = {
    # FR
    'compétences', 'formation', 'formations', 'éducation', 'certifications', 'langues',
    'centres d\'intérêt', 'projets', 'références', 'hobbies', 'loisirs',
    # EN
    'skills', 'education', 'languages', 'interests', 'projects', 'references',
    'certifications', 'qualifications', 'awards', 'achievements',
    # ES
    'habilidades', 'educación', 'idiomas', 'intereses', 'proyectos', 'referencias',
    # DE
    'fähigkeiten', 'bildung', 'sprachen', 'interessen', 'projekte', 'referenzen',
    # ZH/JP/AR
    '技能', '技術', '学歴', '教育', '语言', '興趣', '项目', '資格', 'المهارات', 'التعليم', 'اللغات'
}


def normalize_text(text: str) -> str:
    """Normalise un texte en NFC + casefold pour comparaisons robustes."""
    if not text:
        return ""
    return unicodedata.normalize('NFC', text.strip()).casefold()


def calculate_window_density(lines: List[str], start: int, end: int) -> float:
    """Calcule la densité de contenu d'une fenêtre (ratio de lignes non-vides)."""
    if start >= end or start >= len(lines):
        return 0.0
    
    actual_end = min(end, len(lines))
    window_lines = lines[start:actual_end]
    
    non_empty_lines = sum(1 for line in window_lines if line.strip())
    total_lines = len(window_lines)
    
    return non_empty_lines / total_lines if total_lines > 0 else 0.0


def has_conflicting_header(lines: List[str], start: int, end: int, section_type: str) -> bool:
    """Vérifie si une fenêtre contient des headers conflictuels pour le type de section."""
    if section_type != 'experiences':
        return False
    
    actual_end = min(end, len(lines))
    
    for i in range(max(0, start - 2), min(len(lines), actual_end + 2)):
        if i < len(lines):
            line_normalized = normalize_text(lines[i])
            # Vérifier si c'est un format header
            line_stripped = lines[i].strip()
            is_header_format = (
                line_stripped.endswith(':') or
                line_stripped.isupper() or
                re.match(r'^[A-ZÀÂÄÉÈÊËÏÎÔÖÙÛÜŸÇ\s]+[:\-=]{1,3}$', line_stripped.upper())
            )
            
            if is_header_format:
                # Extraire le contenu du header (sans ponctuation)
                header_content = re.sub(r'[:\-=\s]+$', '', line_normalized)
                if header_content in DISALLOW_HEADERS_EXPERIENCE:
                    logger.debug(f"HEADER_CONFLICT: found disallowed header '{header_content}' at line {i}")
                    return True
    
    return False


def detect_section_headers(lines: List[str]) -> Dict[int, str]:
    """Détecte les headers de sections avec support multi-langues."""
    headers = {}
    
    # Patterns headers multi-langues
    header_patterns = {
        'experiences': [
            r'\b(?:EXPÉRIENCES?|EXPERIENCE[S]?|WORK\s+EXPERIENCE|PROFESSIONAL\s+EXPERIENCE)\b',
            r'\b(?:EMPLOIS?|CARRIÈRE|CAREER|PARCOURS\s+PROFESSIONNEL)\b',
            r'\b(?:職務経歴|工作经验|خبرة العمل)\b'  # JP/ZH/AR
        ],
        'education': [
            r'\b(?:FORMATIONS?|ÉDUCATIONS?|EDUCATION|STUDIES|ACADEMIC)\b',
            r'\b(?:DIPLÔMES?|SCOLARITÉ|PARCOURS\s+ACADÉMIQUE)\b',
            r'\b(?:学歴|教育背景|التعليم)\b'  # JP/ZH/AR
        ],
        'projects': [
            r'\b(?:PROJETS?|PROJECTS?|RÉALISATIONS?)\b',
            r'\b(?:项目|プロジェクト|المشاريع)\b'  # ZH/JP/AR
        ],
        'certifications': [
            r'\b(?:CERTIFICATIONS?|CERTIF\.?|QUALIFICATIONS?)\b',
            r'\b(?:资格|資格|المؤهلات)\b'  # ZH/JP/AR
        ]
    }
    
    for i, line in enumerate(lines):
        line_upper = line.upper().strip()
        
        # Skip lignes trop courtes ou vides
        if len(line_upper) < 3:
            continue
        
        # Détecter format header (majuscules, séparateurs, etc.)
        is_header_format = (
            line_upper.isupper() or
            re.match(r'^[=\-_*]{2,}', line) or
            re.match(r'^[A-ZÀÂÄÉÈÊËÏÎÔÖÙÛÜŸÇ\s]+[:\-=]{1,3}$', line_upper) or
            (len(line.split()) <= 4 and any(char in line for char in ['-', '=', ':', '•']))
        )
        
        if is_header_format:
            # Matcher contre les patterns
            for section_type, patterns in header_patterns.items():
                for pattern in patterns:
                    if re.search(pattern, line_upper, re.IGNORECASE):
                        headers[i] = section_type
                        logger.debug(f"HEADER_DETECT: line={i} section={section_type} text='{line.strip()[:50]}'")
                        break
                if i in headers:
                    break
    
    return headers


def next_header_after(start_idx: int, headers: Dict[int, str], max_lines: int) -> int:
    """Trouve l'index du prochain header après start_idx."""
    next_headers = [idx for idx in headers.keys() if idx > start_idx]
    if next_headers:
        return min(next_headers)
    return max_lines - 1


def is_strong_header(line: str) -> bool:
    """Détecte si une ligne est un header fort (Skills/Languages/COMPÉTENCES/etc.)."""
    line_upper = line.upper().strip()
    
    # Headers non-expérience forts à ne pas traverser
    non_exp_headers = [
        r'\b(?:COMP[ÉE]TENCES?|SKILLS?|APTITUDES?)\b',
        r'\b(?:LANGUES?|LANGUAGES?|IDIOMAS?)\b', 
        r'\b(?:FORMATIONS?|[ÉE]DUCATIONS?|STUDIES)\b',
        r'\b(?:PROJETS?|PROJECTS?|R[ÉE]ALISATIONS?)\b',
        r'\b(?:CERTIFICATIONS?|QUALIFICATIONS?)\b',
        r'\b(?:CENTRES?\s+D.INT[ÉE]R[ÊE]T|INTERESTS?|HOBBIES?)\b',
        r'\b(?:R[ÉE]F[ÉE]RENCES?|REFERENCES?)\b'
    ]
    
    # Format header (majuscules + ponctuation)
    is_header_format = (
        line_upper.isupper() or
        line.endswith(':') or
        re.match(r'^[A-ZÀÂÄÉÈÊËÏÎÔÖÙÛÜŸÇ\s]+[:\-=]{1,3}$', line_upper)
    )
    
    if is_header_format:
        return any(re.search(pattern, line_upper, re.IGNORECASE) for pattern in non_exp_headers)
    
    return False


def header_label(line: str) -> Optional[str]:
    """Retourne le type de header détecté dans la ligne."""
    line_upper = line.upper().strip()
    
    header_patterns = {
        'experiences': [r'\b(?:EXP[ÉE]RIENCES?|WORK\s+EXPERIENCE|EMPLOIS?)\b'],
        'education': [r'\b(?:FORMATIONS?|[ÉE]DUCATIONS?|STUDIES)\b'],
        'skills': [r'\b(?:COMP[ÉE]TENCES?|SKILLS?|APTITUDES?)\b'],
        'languages': [r'\b(?:LANGUES?|LANGUAGES?|IDIOMAS?)\b'],
        'projects': [r'\b(?:PROJETS?|PROJECTS?|R[ÉE]ALISATIONS?)\b'],
        'certifications': [r'\b(?:CERTIFICATIONS?|QUALIFICATIONS?)\b']
    }
    
    for label, patterns in header_patterns.items():
        if any(re.search(pattern, line_upper, re.IGNORECASE) for pattern in patterns):
            return label
    
    return None


def exp_signal_density(window_lines: List[str]) -> float:
    """Calcule la densité de signaux d'expérience dans une fenêtre."""
    if not window_lines:
        return 0.0
    
    exp_indicators = [
        r'\b(?:développeur|developer|ingénieur|engineer|consultant|manager|chef|lead|senior|junior)\b',
        r'\b(?:stage|stagiaire|alternance|apprenti|cdi|cdd|freelance)\b',
        r'\b(?:société|entreprise|company|corp|startup|cabinet|groupe)\b',
        r'\b(?:chez|at|@)\s+[A-Z]',  # "chez TechCorp"
        r'\d{4}\s*[-–—]\s*(?:\d{4}|present|actuel|ongoing)'  # dates
    ]
    
    signal_count = 0
    for line in window_lines:
        line_lower = line.lower()
        for pattern in exp_indicators:
            if re.search(pattern, line_lower, re.IGNORECASE):
                signal_count += 1
                break  # Une seule détection par ligne
    
    return signal_count / len(window_lines)


def calculate_foreign_header_density(lines: List[str], start: int, end: int) -> float:
    """
    Calcule la densité de headers étrangers (non-expérience) dans une fenêtre.
    
    Returns:
        float: Ratio de lignes avec headers étrangers / total lignes non-vides
    """
    if start >= end or start >= len(lines):
        return 0.0
    
    actual_end = min(end, len(lines))
    window_lines = lines[start:actual_end]
    
    foreign_header_count = 0
    non_empty_lines = 0
    
    for line in window_lines:
        if line.strip():
            non_empty_lines += 1
            line_normalized = normalize_text(line)
            
            # Détecter format header
            line_stripped = line.strip()
            is_header_format = (
                line_stripped.endswith(':') or
                line_stripped.isupper() or
                re.match(r'^[A-ZÀÂÄÉÈÊËÏÎÔÖÙÛÜŸÇ\s]+[:\-=]{1,3}$', line_stripped.upper())
            )
            
            if is_header_format:
                # Vérifier si c'est un header étranger (non-expérience)
                header_content = re.sub(r'[:\-=\s]+$', '', line_normalized)
                foreign_headers = {
                    'compétences', 'skills', 'formation', 'education', 'langues', 'languages',
                    'centres d\'intérêt', 'interests', 'projets', 'projects', 'certifications',
                    'références', 'references', 'hobbies', 'loisirs'
                }
                
                if any(fh in header_content for fh in foreign_headers):
                    foreign_header_count += 1
    
    return foreign_header_count / non_empty_lines if non_empty_lines > 0 else 0.0


def find_split_point_for_foreign_headers(lines: List[str], start: int, end: int) -> Optional[int]:
    """
    Trouve le point de split optimal quand foreign_header_density ≥ 0.08.
    
    Returns:
        Optional[int]: Index de la dernière ligne de header étranger avant densité max, ou None
    """
    if start >= end:
        return None
    
    # Calculer la densité par segments glissants de 5 lignes
    segment_size = 5
    max_density = 0.0
    last_foreign_header_line = None
    
    for i in range(start, end - segment_size + 1):
        segment_density = calculate_foreign_header_density(lines, i, i + segment_size)
        if segment_density > max_density:
            max_density = segment_density
        
        # Chercher les headers étrangers dans ce segment
        for j in range(i, min(i + segment_size, end)):
            if j < len(lines):
                line = lines[j]
                line_normalized = normalize_text(line)
                
                # Détecter header étranger
                line_stripped = line.strip()
                is_header_format = (
                    line_stripped.endswith(':') or
                    line_stripped.isupper() or
                    re.match(r'^[A-ZÀÂÄÉÈÊËÏÎÔÖÙÛÜŸÇ\s]+[:\-=]{1,3}$', line_stripped.upper())
                )
                
                if is_header_format:
                    header_content = re.sub(r'[:\-=\s]+$', '', line_normalized)
                    foreign_headers = {
                        'compétences', 'skills', 'formation', 'education', 'langues', 'languages',
                        'centres d\'intérêt', 'interests', 'projets', 'projects', 'certifications'
                    }
                    
                    if any(fh in header_content for fh in foreign_headers):
                        last_foreign_header_line = j
    
    # Si densité ≥ 0.08 et on a trouvé des headers étrangers
    overall_density = calculate_foreign_header_density(lines, start, end)
    if overall_density >= 0.08 and last_foreign_header_line is not None:
        logger.info(f"SPLIT_FOREIGN_HEADERS: density={overall_density:.3f} ≥ 0.08, split at line {last_foreign_header_line}")
        return last_foreign_header_line
    
    return None


def window_for_section(lines: List[str], start: int, end: int, *, 
                      section_label: Optional[str] = None, 
                      headers: Optional[Dict[int, str]] = None,
                      cv_structure: Optional[Dict] = None) -> Tuple[int, int]:
    """
    Calcule la fenêtre optimale pour une section avec bornage header-aware.
    
    Args:
        lines: Lignes du document
        start: Index de début de base
        end: Index de fin de base
        section_label: Type de section (experiences, education, etc.)
        headers: Dict mapping index -> section_type pour les headers détectés
        cv_structure: Structure CV détectée (pour date_position, etc.)
    
    Returns:
        Tuple (new_start, new_end) avec bornage optimisé
    """
    if not headers:
        headers = {}
    
    if not cv_structure:
        cv_structure = {}
    
    # Bornage header-aware pour expériences avec guards anti-contamination
    if section_label in {"experiences", "experience"}:
        # Guard 1: Vérifier la densité minimale
        initial_density = calculate_window_density(lines, start, end)
        if initial_density < DENSITY_MIN_EXPERIENCE:
            logger.debug(f"DENSITY_GUARD: window density {initial_density:.3f} < {DENSITY_MIN_EXPERIENCE}, rejecting experience window")
            return start, start  # Fenêtre vide pour rejeter
        
        # Guard 2: Vérifier les headers conflictuels
        if has_conflicting_header(lines, start, end, section_label):
            logger.debug(f"HEADER_GUARD: conflicting header detected in experience window [{start}:{end}], reducing score")
            return start, start  # Fenêtre vide pour rejeter
        
        # CORRECTIF: Guard 3: Split si foreign_header_density ≥ 0.08
        split_point = find_split_point_for_foreign_headers(lines, start, end)
        if split_point is not None:
            logger.info(f"FOREIGN_HEADER_SPLIT: splitting experience window at line {split_point}")
            return start, split_point
        
        # Trouver le prochain header après la fin
        next_header_idx = next_header_after(end, headers, len(lines))
        
        # Extension de base jusqu'au prochain header (max 40 lignes)
        extended_end = min(next_header_idx, start + 40)
        
        # stop expansion when encountering strong non-exp header
        for i in range(end, extended_end):
            if i < len(lines):
                line = lines[i]
                if is_strong_header(line) and header_label(line) not in ("experiences", "experience", "work"):
                    extended_end = i
                    break
                
                # Guard 4: Vérifier les headers conflictuels pendant l'extension
                if has_conflicting_header(lines, start, i+1, section_label):
                    extended_end = i
                    logger.debug(f"HEADER_GUARD: stopped extension at line {i} due to conflicting header")
                    break
                
                # Guard 5: Vérifier foreign header density pendant l'extension
                extension_split = find_split_point_for_foreign_headers(lines, start, i+1)
                if extension_split is not None:
                    extended_end = extension_split
                    logger.debug(f"FOREIGN_HEADER_GUARD: stopped extension at line {extension_split} due to foreign header density")
                    break
        
        # ensure minimal window size when exp density is high
        curr_window = lines[start:extended_end]
        window_size = extended_end - start
        if window_size < 12 and exp_signal_density(curr_window) >= 0.35:
            # expand_until(12) mais pas au-delà des headers forts
            target_end = start + 12
            for i in range(extended_end, min(target_end, len(lines))):
                if is_strong_header(lines[i]) and header_label(lines[i]) not in ("experiences", "experience", "work"):
                    break
                extended_end = i + 1
        
        # Lookahead additionnel pour date-first
        if cv_structure.get('date_position') == 'before_content':
            lookahead = cv_structure.get('exp_lookahead', 25)
            extended_end = min(extended_end + lookahead, len(lines) - 1)
        
        # Log du bornage avec métriques
        window_size_final = extended_end - start
        density = exp_signal_density(lines[start:extended_end])
        foreign_density = calculate_foreign_header_density(lines, start, extended_end)
        logger.info(f"BOUND.exp.header_idx={start} next_header_idx={next_header_idx} "
                   f"size={window_size_final} density={density:.2f} foreign_density={foreign_density:.3f}")
        
        return (start, max(end, extended_end))
    
    # Bornage standard pour autres sections
    return (start, end)


def enhance_section_boundaries(boundaries: List[Tuple[int, int, str]], 
                              lines: List[str],
                              cv_structure: Optional[Dict] = None) -> List[Tuple[int, int, str]]:
    """
    Améliore les boundaries de sections avec détection header-aware.
    
    Args:
        boundaries: Liste des (start, end, section_type) originales
        lines: Lignes du document
        cv_structure: Structure CV détectée
    
    Returns:
        Liste des boundaries améliorées
    """
    if not boundaries:
        return boundaries
    
    # Détecter tous les headers
    headers = detect_section_headers(lines)
    
    enhanced_boundaries = []
    for start, end, section_type in boundaries:
        # Appliquer le bornage header-aware
        new_start, new_end = window_for_section(
            lines, start, end,
            section_label=section_type,
            headers=headers,
            cv_structure=cv_structure
        )
        enhanced_boundaries.append((new_start, new_end, section_type))
    
    return enhanced_boundaries
