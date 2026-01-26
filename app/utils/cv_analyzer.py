"""
CV Analyzer - Phase 1: ANALYSE layout et structure
=====================================================

Analyse géométrique complète d'un CV : détection colonnes, ordre de lecture,
langue, direction script (LTR/RTL), regroupement par proximité spatiale.
"""

import re
import math
from typing import Dict, List, Any, Optional, Tuple, NamedTuple
from dataclasses import dataclass
from pathlib import Path
from loguru import logger

import numpy as np
from sklearn.cluster import KMeans
from babel import Locale
from babel.core import get_global
import langdetect
import unicodedata
try:
    import pycld2 as cld2
    CLD2_AVAILABLE = True
except ImportError:
    CLD2_AVAILABLE = False


class BoundingBox(NamedTuple):
    """Rectangle englobant avec coordonnées."""
    left: float
    top: float
    right: float
    bottom: float
    
    @property
    def width(self) -> float:
        return self.right - self.left
    
    @property
    def height(self) -> float:
        return self.bottom - self.top
    
    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2
    
    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2
    
    @property
    def area(self) -> float:
        return self.width * self.height


@dataclass
class TextBlock:
    """Bloc de texte avec métadonnées spatiales et stylistiques."""
    id: str
    text: str
    bbox: BoundingBox
    page: int
    font_size: float = 12.0
    is_bold: bool = False
    is_italic: bool = False
    font_name: str = ""
    confidence: float = 1.0
    reading_order: int = -1
    column_id: Optional[str] = None


@dataclass
class Column:
    """Colonne détectée avec métadonnées."""
    id: str
    bbox: BoundingBox
    text_blocks: List[TextBlock]
    reading_order: int = -1


@dataclass 
class LayoutAnalysis:
    """Résultat complet de l'analyse layout."""
    column_count: int
    columns: List[Column]
    reading_order: List[TextBlock]
    is_rtl_layout: bool
    detected_language: str
    detected_script: str
    has_sidebar: bool
    sidebar_position: Optional[str]  # 'left', 'right', None
    header_footer_detected: bool
    structural_elements: Dict[str, List[BoundingBox]]
    confidence_score: float


class CVAnalyzer:
    """Analyseur de layout CV avec support multi-langues et RTL."""
    
    # Langues RTL courantes
    RTL_LANGUAGES = {'ar', 'he', 'fa', 'ur', 'yi'}
    
    # Scripts RTL Unicode
    RTL_SCRIPTS = {
        'Arabic', 'Hebrew', 'Thaana', 'Syriac', 'Samaritan', 
        'Mandaic', 'Imperial_Aramaic', 'Phoenician', 'Lydian',
        'Meroitic_Hieroglyphs', 'Meroitic_Cursive', 'Kharoshthi',
        'Old_South_Arabian', 'Old_North_Arabian', 'Manichaean',
        'Avestan', 'Inscriptional_Parthian', 'Inscriptional_Pahlavi',
        'Psalter_Pahlavi', 'Old_Turkic', 'Old_Hungarian'
    }
    
    def __init__(self):
        self.debug_mode = False
    
    def analyze_layout(self, text_blocks: List[TextBlock]) -> LayoutAnalysis:
        """
        Analyse complète du layout d'un CV.
        
        Args:
            text_blocks: Liste des blocs de texte avec coordonnées
            
        Returns:
            LayoutAnalysis: Analyse complète du layout
        """
        if not text_blocks:
            return self._empty_layout()
        
        logger.info(f"🔍 Analyse layout de {len(text_blocks)} blocs de texte")
        
        # 1. Détection langue et direction script
        full_text = " ".join(block.text for block in text_blocks)
        detected_language = self._detect_language(full_text)
        detected_script = self._detect_script(full_text)
        is_rtl = self._is_rtl_layout(detected_language, detected_script, full_text)
        
        logger.info(f"📝 Langue: {detected_language}, Script: {detected_script}, RTL: {is_rtl}")
        
        # 2. Détection colonnes par clustering spatial
        columns = self._detect_columns(text_blocks)
        
        # 3. Calcul ordre de lecture (RTL aware)
        reading_order = self._compute_reading_order(text_blocks, columns, is_rtl)
        
        # 4. Détection éléments structurels
        structural_elements = self._detect_structural_elements(text_blocks)
        
        # 5. Détection sidebar
        has_sidebar, sidebar_position = self._detect_sidebar(columns, text_blocks)
        
        # 6. Score de confiance global
        confidence_score = self._calculate_layout_confidence(
            text_blocks, columns, reading_order
        )
        
        result = LayoutAnalysis(
            column_count=len(columns),
            columns=columns,
            reading_order=reading_order,
            is_rtl_layout=is_rtl,
            detected_language=detected_language,
            detected_script=detected_script,
            has_sidebar=has_sidebar,
            sidebar_position=sidebar_position,
            header_footer_detected=bool(
                structural_elements.get('headers') or structural_elements.get('footers')
            ),
            structural_elements=structural_elements,
            confidence_score=confidence_score
        )
        
        logger.info(f"✅ Layout analysé: {len(columns)} colonnes, "
                   f"RTL: {is_rtl}, confiance: {confidence_score:.2f}")
        
        return result
    
    def _detect_language(self, text: str) -> str:
        """Détection robuste de langue."""
        if len(text.strip()) < 10:
            return "unknown"
        
        try:
            # Essayer CLD2 d'abord (plus précis)
            if CLD2_AVAILABLE:
                reliable, text_bytes_found, details = cld2.detect(text)
                if reliable and details:
                    return details[0][1]  # Code langue ISO
            
            # Fallback sur langdetect
            detected = langdetect.detect(text)
            return detected
            
        except Exception as e:
            logger.warning(f"Erreur détection langue: {e}")
            
            # Fallback heuristique simple
            if self._has_arabic_chars(text):
                return "ar"
            elif self._has_hebrew_chars(text):
                return "he"
            elif self._has_cyrillic_chars(text):
                return "ru"
            elif self._has_cjk_chars(text):
                return "zh"
            else:
                return "en"  # Default
    
    def _detect_script(self, text: str) -> str:
        """Détection du système d'écriture principal."""
        if not text.strip():
            return "Latin"
        
        # Compter les caractères par script
        script_counts = {}
        for char in text:
            if char.isalnum():  # Ignorer ponctuation/espaces
                script = unicodedata.name(char, '').split()[0] if unicodedata.name(char, '') else 'UNKNOWN'
                
                # Mapping des scripts Unicode
                if script.startswith('ARABIC'):
                    script_counts['Arabic'] = script_counts.get('Arabic', 0) + 1
                elif script.startswith('HEBREW'):
                    script_counts['Hebrew'] = script_counts.get('Hebrew', 0) + 1
                elif script.startswith('CYRILLIC'):
                    script_counts['Cyrillic'] = script_counts.get('Cyrillic', 0) + 1
                elif script.startswith(('CJK', 'HIRAGANA', 'KATAKANA', 'HANGUL')):
                    script_counts['CJK'] = script_counts.get('CJK', 0) + 1
                elif script.startswith('LATIN'):
                    script_counts['Latin'] = script_counts.get('Latin', 0) + 1
        
        if script_counts:
            return max(script_counts.items(), key=lambda x: x[1])[0]
        
        return "Latin"  # Default
    
    def _is_rtl_layout(self, language: str, script: str, text: str) -> bool:
        """Détermine si le layout est RTL."""
        # Check langue
        if language in self.RTL_LANGUAGES:
            return True
        
        # Check script
        if script in self.RTL_SCRIPTS:
            return True
        
        # Heuristique sur le contenu
        rtl_ratio = self._calculate_rtl_char_ratio(text)
        return rtl_ratio > 0.3  # Plus de 30% de caractères RTL
    
    def _calculate_rtl_char_ratio(self, text: str) -> float:
        """Calcule le ratio de caractères RTL dans le texte."""
        if not text:
            return 0.0
        
        rtl_chars = 0
        total_chars = 0
        
        for char in text:
            if char.isalnum():
                total_chars += 1
                if self._is_rtl_char(char):
                    rtl_chars += 1
        
        return rtl_chars / max(total_chars, 1)
    
    def _is_rtl_char(self, char: str) -> bool:
        """Vérifie si un caractère appartient à un script RTL."""
        try:
            script = unicodedata.name(char, '').split()[0]
            return any(rtl_script in script for rtl_script in 
                      ['ARABIC', 'HEBREW', 'SYRIAC', 'THAANA'])
        except:
            return False
    
    def _has_arabic_chars(self, text: str) -> bool:
        """Détecte la présence de caractères arabes."""
        return bool(re.search(r'[\u0600-\u06FF\u0750-\u077F]', text))
    
    def _has_hebrew_chars(self, text: str) -> bool:
        """Détecte la présence de caractères hébreux."""
        return bool(re.search(r'[\u0590-\u05FF]', text))
    
    def _has_cyrillic_chars(self, text: str) -> bool:
        """Détecte la présence de caractères cyrilliques."""
        return bool(re.search(r'[\u0400-\u04FF]', text))
    
    def _has_cjk_chars(self, text: str) -> bool:
        """Détecte la présence de caractères CJK."""
        return bool(re.search(r'[\u4e00-\u9fff\u3400-\u4dbf\uac00-\ud7af\u3040-\u309f\u30a0-\u30ff]', text))
    
    def _detect_columns(self, text_blocks: List[TextBlock]) -> List[Column]:
        """Détection des colonnes par clustering spatial."""
        if len(text_blocks) < 2:
            # Un seul bloc = une colonne
            column = Column(
                id="col_0",
                bbox=text_blocks[0].bbox,
                text_blocks=text_blocks,
                reading_order=0
            )
            return [column]
        
        # Extraire les coordonnées X centrales
        x_centers = np.array([[block.bbox.center_x] for block in text_blocks])
        
        # Clustering automatique (méthode du coude)
        best_k = self._find_optimal_clusters(x_centers, max_k=min(5, len(text_blocks)))
        
        if best_k == 1:
            # Une seule colonne détectée
            all_bbox = self._compute_bounding_box([b.bbox for b in text_blocks])
            column = Column(
                id="col_0",
                bbox=all_bbox,
                text_blocks=text_blocks,
                reading_order=0
            )
            return [column]
        
        # Clustering K-means
        kmeans = KMeans(n_clusters=best_k, random_state=42)
        cluster_labels = kmeans.fit_predict(x_centers)
        
        # Créer les colonnes
        columns = []
        for i in range(best_k):
            cluster_blocks = [block for j, block in enumerate(text_blocks) 
                            if cluster_labels[j] == i]
            
            if cluster_blocks:
                cluster_bbox = self._compute_bounding_box([b.bbox for b in cluster_blocks])
                column = Column(
                    id=f"col_{i}",
                    bbox=cluster_bbox,
                    text_blocks=cluster_blocks,
                    reading_order=i
                )
                columns.append(column)
        
        # Trier colonnes par position X
        columns.sort(key=lambda c: c.bbox.center_x)
        
        # Réassigner les IDs d'ordre
        for i, column in enumerate(columns):
            column.reading_order = i
            column.id = f"col_{i}"
            # Assigner column_id aux blocs
            for block in column.text_blocks:
                block.column_id = column.id
        
        logger.info(f"📊 {len(columns)} colonnes détectées")
        return columns
    
    def _find_optimal_clusters(self, data: np.ndarray, max_k: int = 5) -> int:
        """Trouve le nombre optimal de clusters (méthode du coude)."""
        if len(data) <= 1:
            return 1
        
        max_k = min(max_k, len(data))
        if max_k <= 1:
            return 1
        
        try:
            inertias = []
            k_range = range(1, max_k + 1)
            
            for k in k_range:
                kmeans = KMeans(n_clusters=k, random_state=42)
                kmeans.fit(data)
                inertias.append(kmeans.inertia_)
            
            # Méthode du coude - chercher le point de "cassure"
            if len(inertias) < 3:
                return 1
            
            # Calculer les différences secondes
            diffs = np.diff(inertias)
            second_diffs = np.diff(diffs)
            
            # Le coude est là où la différence seconde est maximum (en valeur absolue)
            if len(second_diffs) > 0:
                elbow_idx = np.argmax(np.abs(second_diffs)) + 2  # +2 car deux diff()
                return min(elbow_idx, max_k)
            
            return min(2, max_k)  # Default à 2 colonnes max
            
        except Exception as e:
            logger.warning(f"Erreur clustering: {e}")
            return 1
    
    def _compute_bounding_box(self, bboxes: List[BoundingBox]) -> BoundingBox:
        """Calcule le rectangle englobant d'une liste de bbox."""
        if not bboxes:
            return BoundingBox(0, 0, 0, 0)
        
        min_left = min(bbox.left for bbox in bboxes)
        min_top = min(bbox.top for bbox in bboxes)
        max_right = max(bbox.right for bbox in bboxes)
        max_bottom = max(bbox.bottom for bbox in bboxes)
        
        return BoundingBox(min_left, min_top, max_right, max_bottom)
    
    def _compute_reading_order(
        self, 
        text_blocks: List[TextBlock], 
        columns: List[Column], 
        is_rtl: bool
    ) -> List[TextBlock]:
        """Calcule l'ordre de lecture optimal (RTL aware)."""
        
        # Trier colonnes selon direction de lecture
        sorted_columns = sorted(columns, 
                               key=lambda c: c.bbox.center_x, 
                               reverse=is_rtl)
        
        ordered_blocks = []
        reading_order_counter = 0
        
        for column in sorted_columns:
            # Dans chaque colonne, trier top-down
            column_blocks = sorted(column.text_blocks, key=lambda b: b.bbox.top)
            
            for block in column_blocks:
                block.reading_order = reading_order_counter
                reading_order_counter += 1
                ordered_blocks.append(block)
        
        logger.info(f"📖 Ordre de lecture calculé pour {len(ordered_blocks)} blocs "
                   f"(RTL: {is_rtl})")
        
        return ordered_blocks
    
    def _detect_structural_elements(
        self, 
        text_blocks: List[TextBlock]
    ) -> Dict[str, List[BoundingBox]]:
        """Détecte les éléments structurels (en-têtes, pieds, sidebars)."""
        
        if not text_blocks:
            return {'headers': [], 'footers': [], 'sidebars': []}
        
        # Grouper par page
        pages_blocks = {}
        for block in text_blocks:
            if block.page not in pages_blocks:
                pages_blocks[block.page] = []
            pages_blocks[block.page].append(block)
        
        headers = []
        footers = []
        sidebars = []
        
        for page, blocks in pages_blocks.items():
            if not blocks:
                continue
            
            # Trier par position Y
            blocks_by_y = sorted(blocks, key=lambda b: b.bbox.top)
            
            # Seuils pour en-têtes/pieds (% de la hauteur page)
            min_y = min(b.bbox.top for b in blocks)
            max_y = max(b.bbox.bottom for b in blocks)
            page_height = max_y - min_y
            
            header_threshold = min_y + 0.1 * page_height
            footer_threshold = max_y - 0.1 * page_height
            
            # Détecter en-têtes (10% du haut)
            for block in blocks_by_y:
                if block.bbox.top <= header_threshold:
                    if self._looks_like_header(block):
                        headers.append(block.bbox)
                else:
                    break
            
            # Détecter pieds (10% du bas)  
            for block in reversed(blocks_by_y):
                if block.bbox.bottom >= footer_threshold:
                    if self._looks_like_footer(block):
                        footers.append(block.bbox)
                else:
                    break
        
        return {
            'headers': headers,
            'footers': footers, 
            'sidebars': sidebars
        }
    
    def _looks_like_header(self, block: TextBlock) -> bool:
        """Heuristique pour identifier un en-tête."""
        text = block.text.lower().strip()
        
        # Mots-clés typiques d'en-têtes
        header_keywords = [
            'cv', 'curriculum vitae', 'resume', 'profil', 'profile',
            'nom', 'name', 'titre', 'title', 'poste', 'position'
        ]
        
        return any(keyword in text for keyword in header_keywords) or \
               len(text.split()) <= 5  # En-têtes souvent courts
    
    def _looks_like_footer(self, block: TextBlock) -> bool:
        """Heuristique pour identifier un pied de page."""
        text = block.text.lower().strip()
        
        # Mots-clés typiques de pieds
        footer_keywords = [
            'page', 'confidentiel', 'confidential', 'copyright', '©',
            'références', 'references', 'disponible', 'available'
        ]
        
        return any(keyword in text for keyword in footer_keywords) or \
               re.match(r'^\d+$', text.strip())  # Numéros de page
    
    def _detect_sidebar(
        self, 
        columns: List[Column], 
        text_blocks: List[TextBlock]
    ) -> Tuple[bool, Optional[str]]:
        """Détecte la présence d'une sidebar et sa position."""
        
        if len(columns) < 2:
            return False, None
        
        # Calculer largeurs colonnes
        column_widths = [(col, col.bbox.width) for col in columns]
        column_widths.sort(key=lambda x: x[1])  # Trier par largeur
        
        # Si la plus petite colonne fait < 40% de la plus grande
        smallest_width = column_widths[0][1]
        largest_width = column_widths[-1][1]
        
        if smallest_width / largest_width < 0.4:
            # C'est probablement une sidebar
            sidebar_column = column_widths[0][0]
            
            # Déterminer position (gauche vs droite)
            all_columns_x = [col.bbox.center_x for col in columns]
            sidebar_x = sidebar_column.bbox.center_x
            
            if sidebar_x == min(all_columns_x):
                return True, "left"
            elif sidebar_x == max(all_columns_x):
                return True, "right" 
            else:
                return True, "center"  # Rare mais possible
        
        return False, None
    
    def _calculate_layout_confidence(
        self, 
        text_blocks: List[TextBlock], 
        columns: List[Column], 
        reading_order: List[TextBlock]
    ) -> float:
        """Calcule un score de confiance pour l'analyse layout."""
        
        if not text_blocks:
            return 0.0
        
        confidence_factors = []
        
        # 1. Facteur nombre de blocs (plus il y en a, plus c'est fiable)
        block_count_factor = min(len(text_blocks) / 20.0, 1.0)
        confidence_factors.append(block_count_factor)
        
        # 2. Facteur cohérence colonnes (alignement)
        if columns:
            alignment_scores = []
            for column in columns:
                if len(column.text_blocks) > 1:
                    # Mesurer alignement vertical des blocs dans la colonne
                    left_coords = [b.bbox.left for b in column.text_blocks]
                    alignment_variance = np.var(left_coords)
                    # Normaliser (variance faible = bon alignement)
                    alignment_score = 1.0 / (1.0 + alignment_variance / 1000.0)
                    alignment_scores.append(alignment_score)
            
            if alignment_scores:
                avg_alignment = np.mean(alignment_scores)
                confidence_factors.append(avg_alignment)
        
        # 3. Facteur taille de texte (éviter blocs trop petits)
        text_lengths = [len(block.text.strip()) for block in text_blocks]
        avg_text_length = np.mean(text_lengths)
        text_factor = min(avg_text_length / 50.0, 1.0)  # 50 chars = facteur 1.0
        confidence_factors.append(text_factor)
        
        # Score final = moyenne pondérée
        if confidence_factors:
            return np.mean(confidence_factors)
        
        return 0.5  # Score neutre par défaut
    
    def _empty_layout(self) -> LayoutAnalysis:
        """Layout vide pour cas d'erreur."""
        return LayoutAnalysis(
            column_count=0,
            columns=[],
            reading_order=[],
            is_rtl_layout=False,
            detected_language="unknown",
            detected_script="Latin",
            has_sidebar=False,
            sidebar_position=None,
            header_footer_detected=False,
            structural_elements={'headers': [], 'footers': [], 'sidebars': []},
            confidence_score=0.0
        )
