"""
CV Mapper - Phase 2: MAPPING sémantique avec garde-fous anti-contamination
=========================================================================

Cartographie intelligente des sections CV avec dictionnaires multi-langues
et garde-fous stricts pour éviter la contamination croisée entre sections.
"""

import re
import json
import math
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass
from pathlib import Path
from loguru import logger

import numpy as np
from rapidfuzz import fuzz, process
from sklearn.metrics.pairwise import euclidean_distances

from .cv_analyzer import TextBlock, BoundingBox, LayoutAnalysis


@dataclass
class SectionCandidate:
    """Candidat pour une section avec score de confiance."""
    section_type: str
    block_id: str
    confidence_score: float
    keywords_matched: List[str]
    reasoning: str


@dataclass
class ContaminationRisk:
    """Risque de contamination détecté."""
    block_id: str
    risk_type: str  # 'geometric_proximity', 'semantic_confusion', 'boundary_conflict'
    risk_level: float  # 0.0 - 1.0
    details: Dict[str, Any]
    recommendation: str


@dataclass
class SectionMapping:
    """Résultat complet du mapping sémantique."""
    sections: Dict[str, List[TextBlock]]  # section_type -> blocks
    confidence_scores: Dict[str, float]   # section_type -> confidence
    contamination_risks: List[ContaminationRisk]
    unmapped_blocks: List[TextBlock]
    mapping_quality_score: float
    processing_metadata: Dict[str, Any]


class MultiLanguageDictionaries:
    """Dictionnaires multi-langues pour mapping sémantique."""
    
    def __init__(self):
        self.dictionaries = self._load_builtin_dictionaries()
    
    def _load_builtin_dictionaries(self) -> Dict[str, Dict[str, List[str]]]:
        """Charge les dictionnaires intégrés multi-langues."""
        return {
            # FRANÇAIS
            "fr": {
                "contact": [
                    "informations personnelles", "coordonnées", "contact", "adresse",
                    "téléphone", "email", "mail", "portable", "mobile", "linkedin",
                    "profil", "identité", "nom", "prénom", "né le", "né en",
                    "nationalité", "situation familiale", "permis", "véhicule"
                ],
                "summary": [
                    "profil", "résumé", "objectif", "synthèse", "présentation",
                    "à propos", "qui suis-je", "profil professionnel", "introduction",
                    "résumé professionnel", "objectifs", "motivations", "projet"
                ],
                "experience": [
                    "expérience professionnelle", "expériences", "parcours professionnel",
                    "carrière", "emplois", "postes occupés", "fonctions", "missions",
                    "depuis", "jusqu'à", "actuellement", "en cours", "présent",
                    "stage", "alternance", "cdd", "cdi", "freelance", "consultant"
                ],
                "education": [
                    "formation", "études", "diplômes", "scolarité", "cursus",
                    "université", "école", "institut", "lycée", "baccalauréat",
                    "licence", "master", "doctorat", "bts", "dut", "cap",
                    "certification", "titre", "niveau", "mention"
                ],
                "skills": [
                    "compétences", "savoir-faire", "aptitudes", "capacités",
                    "maîtrise", "expertise", "technologies", "outils", "langages",
                    "logiciels", "systèmes", "méthodes", "techniques", "niveau"
                ],
                "projects": [
                    "projets", "réalisations", "portfolio", "travaux", "créations",
                    "développement", "conception", "mise en œuvre", "implémentation",
                    "projet personnel", "projet professionnel", "hackathon", "concours"
                ],
                "languages": [
                    "langues", "langages", "linguistique", "idiomes", "parlé",
                    "écrit", "lu", "bilingue", "trilingue", "natif", "maternel",
                    "courant", "intermédiaire", "notions", "débutant", "avancé",
                    "toeic", "toefl", "delf", "dalf", "cecr", "a1", "a2", "b1", "b2", "c1", "c2"
                ],
                "certifications": [
                    "certifications", "certificats", "qualifications", "agréments",
                    "habilitations", "accréditations", "labels", "attestations",
                    "cisco", "microsoft", "google", "aws", "azure", "oracle",
                    "pmp", "scrum", "agile", "itil", "prince2"
                ],
                "awards": [
                    "prix", "récompenses", "distinctions", "reconnaissance",
                    "médailles", "trophées", "concours", "classement", "lauréat",
                    "finaliste", "gagnant", "vainqueur", "champion", "mention"
                ],
                "volunteering": [
                    "bénévolat", "volontariat", "associatif", "solidarité",
                    "engagement", "humanitaire", "social", "caritatif", "ong",
                    "association", "fondation", "entraide", "service civique"
                ],
                "interests": [
                    "centres d'intérêt", "loisirs", "hobbies", "passions",
                    "activités", "passe-temps", "sport", "culture", "lecture",
                    "voyage", "musique", "cinéma", "art", "cuisine", "jardinage"
                ],
                "references": [
                    "références", "recommandations", "contacts", "témoignages",
                    "parrains", "référents", "superviseur", "manager", "collègue",
                    "disponible sur demande", "fourni si nécessaire"
                ]
            },
            
            # ENGLISH
            "en": {
                "contact": [
                    "personal information", "contact", "address", "phone", "email",
                    "mobile", "cell", "linkedin", "profile", "name", "born",
                    "nationality", "marital status", "driving license", "vehicle"
                ],
                "summary": [
                    "profile", "summary", "objective", "overview", "about",
                    "introduction", "professional summary", "career objective",
                    "personal statement", "goals", "motivation", "vision"
                ],
                "experience": [
                    "professional experience", "work experience", "employment",
                    "career", "jobs", "positions", "roles", "responsibilities",
                    "since", "until", "currently", "present", "ongoing",
                    "internship", "apprenticeship", "contract", "permanent", "freelance"
                ],
                "education": [
                    "education", "academic background", "qualifications", "degrees",
                    "university", "college", "school", "institute", "bachelor",
                    "master", "phd", "doctorate", "diploma", "certificate",
                    "gpa", "honors", "magna cum laude", "summa cum laude"
                ],
                "skills": [
                    "skills", "competencies", "abilities", "expertise", "proficiency",
                    "technologies", "tools", "languages", "software", "systems",
                    "methodologies", "frameworks", "platforms", "level", "advanced"
                ],
                "projects": [
                    "projects", "portfolio", "work", "developments", "implementations",
                    "creations", "personal projects", "professional projects",
                    "hackathon", "competition", "open source", "github"
                ],
                "languages": [
                    "languages", "linguistic", "spoken", "written", "read",
                    "bilingual", "trilingual", "native", "mother tongue", "fluent",
                    "intermediate", "basic", "beginner", "advanced", "conversational",
                    "toeic", "toefl", "ielts", "cambridge", "cefr", "a1", "a2", "b1", "b2", "c1", "c2"
                ],
                "certifications": [
                    "certifications", "certificates", "qualifications", "credentials",
                    "licenses", "accreditations", "attestations", "cisco", "microsoft",
                    "google", "aws", "azure", "oracle", "pmp", "scrum", "agile", "itil"
                ],
                "awards": [
                    "awards", "honors", "achievements", "recognition", "prizes",
                    "medals", "trophies", "competitions", "winner", "finalist",
                    "champion", "distinction", "excellence", "outstanding"
                ],
                "volunteering": [
                    "volunteering", "volunteer work", "community service", "charity",
                    "non-profit", "ngo", "foundation", "social work", "humanitarian",
                    "civic engagement", "community involvement"
                ],
                "interests": [
                    "interests", "hobbies", "activities", "pastimes", "leisure",
                    "sports", "culture", "reading", "travel", "music", "movies",
                    "art", "cooking", "gardening", "photography"
                ],
                "references": [
                    "references", "recommendations", "contacts", "testimonials",
                    "referees", "supervisors", "managers", "colleagues",
                    "available upon request", "provided if needed"
                ]
            },
            
            # ESPAÑOL
            "es": {
                "contact": [
                    "información personal", "contacto", "dirección", "teléfono",
                    "email", "correo", "móvil", "celular", "linkedin", "perfil",
                    "nombre", "nacido", "nacionalidad", "estado civil", "carnet"
                ],
                "experience": [
                    "experiencia profesional", "experiencia laboral", "trayectoria",
                    "carrera", "empleos", "puestos", "funciones", "responsabilidades",
                    "desde", "hasta", "actualmente", "presente", "en curso",
                    "prácticas", "becario", "contrato", "indefinido", "freelance"
                ],
                "education": [
                    "formación", "educación", "estudios", "titulación", "diplomas",
                    "universidad", "colegio", "instituto", "licenciatura", "máster",
                    "doctorado", "grado", "bachillerato", "certificado", "título"
                ],
                "skills": [
                    "competencias", "habilidades", "destrezas", "capacidades",
                    "conocimientos", "tecnologías", "herramientas", "idiomas",
                    "software", "sistemas", "metodologías", "nivel", "avanzado"
                ]
            },
            
            # DEUTSCH
            "de": {
                "contact": [
                    "persönliche daten", "kontakt", "adresse", "telefon", "email",
                    "handy", "mobilfunk", "linkedin", "profil", "name", "geboren",
                    "nationalität", "familienstand", "führerschein"
                ],
                "experience": [
                    "berufserfahrung", "berufliche laufbahn", "tätigkeiten",
                    "karriere", "stellen", "positionen", "aufgaben", "verantwortlichkeiten",
                    "seit", "bis", "derzeit", "aktuell", "gegenwärtig",
                    "praktikum", "ausbildung", "vertrag", "festanstellung", "freiberuflich"
                ],
                "education": [
                    "ausbildung", "bildung", "studium", "qualifikationen", "abschlüsse",
                    "universität", "hochschule", "schule", "bachelor", "master",
                    "promotion", "doktor", "diplom", "zertifikat", "zeugnis"
                ],
                "skills": [
                    "fähigkeiten", "kompetenzen", "kenntnisse", "fertigkeiten",
                    "expertise", "technologien", "werkzeuge", "sprachen",
                    "software", "systeme", "methoden", "niveau", "fortgeschritten"
                ]
            }
        }
    
    def get_keywords(self, section_type: str, language: str) -> List[str]:
        """Récupère les mots-clés pour une section dans une langue."""
        if language not in self.dictionaries:
            language = "en"  # Fallback anglais
        
        lang_dict = self.dictionaries[language]
        return lang_dict.get(section_type, [])
    
    def get_all_section_types(self) -> List[str]:
        """Retourne tous les types de sections disponibles."""
        return list(self.dictionaries["fr"].keys())


class CVMapper:
    """Mappeur sémantique de CV avec garde-fous anti-contamination."""
    
    def __init__(self):
        self.dictionaries = MultiLanguageDictionaries()
        self.contamination_threshold = 100.0  # pixels
        self.semantic_threshold = 0.6  # score minimum pour validation
        self.debug_mode = False
    
    def map_sections_semantic(
        self, 
        text_blocks: List[TextBlock], 
        layout: LayoutAnalysis
    ) -> SectionMapping:
        """
        Mapping sémantique complet avec garde-fous anti-contamination.
        
        Args:
            text_blocks: Blocs de texte avec coordonnées
            layout: Analyse layout du document
            
        Returns:
            SectionMapping: Mapping validé avec score de qualité
        """
        if not text_blocks:
            return self._empty_mapping()
        
        logger.info(f"🗺️ Mapping sémantique de {len(text_blocks)} blocs")
        
        # 1. Génération candidats par bloc
        candidates = self._generate_section_candidates(text_blocks, layout)
        
        # 2. Construction graphe d'adjacence spatiale
        adjacency_graph = self._build_adjacency_graph(text_blocks)
        
        # 3. Application garde-fous contamination
        validated_mapping, contamination_risks = self._apply_contamination_guards(
            candidates, adjacency_graph, text_blocks
        )
        
        # 4. Groupement des blocs par section
        section_groups = self._group_blocks_by_section(validated_mapping, text_blocks)
        
        # 5. Calcul scores de confiance par section
        confidence_scores = self._calculate_section_confidence_scores(
            section_groups, candidates
        )
        
        # 6. Score de qualité global
        quality_score = self._calculate_mapping_quality_score(
            section_groups, contamination_risks, text_blocks
        )
        
        # 7. Identification blocs non mappés
        mapped_block_ids = set(validated_mapping.keys())
        unmapped_blocks = [block for block in text_blocks 
                          if block.id not in mapped_block_ids]
        
        result = SectionMapping(
            sections=section_groups,
            confidence_scores=confidence_scores,
            contamination_risks=contamination_risks,
            unmapped_blocks=unmapped_blocks,
            mapping_quality_score=quality_score,
            processing_metadata={
                'total_blocks': len(text_blocks),
                'mapped_blocks': len(mapped_block_ids),
                'contamination_risks_found': len(contamination_risks),
                'language': layout.detected_language,
                'confidence_threshold': self.semantic_threshold
            }
        )
        
        logger.info(f"✅ Mapping terminé: {len(section_groups)} sections, "
                   f"qualité: {quality_score:.2f}")
        
        return result
    
    def _generate_section_candidates(
        self, 
        text_blocks: List[TextBlock], 
        layout: LayoutAnalysis
    ) -> Dict[str, List[SectionCandidate]]:
        """Génère les candidats de section pour chaque bloc."""
        candidates = {}
        language = layout.detected_language
        section_types = self.dictionaries.get_all_section_types()
        
        for block in text_blocks:
            block_candidates = []
            
            for section_type in section_types:
                score, matched_keywords, reasoning = self._calculate_semantic_score(
                    block, section_type, language
                )
                
                if score > 0.1:  # Seuil minimal pour être considéré
                    candidate = SectionCandidate(
                        section_type=section_type,
                        block_id=block.id,
                        confidence_score=score,
                        keywords_matched=matched_keywords,
                        reasoning=reasoning
                    )
                    block_candidates.append(candidate)
            
            # Trier par score décroissant
            block_candidates.sort(key=lambda c: c.confidence_score, reverse=True)
            candidates[block.id] = block_candidates
        
        return candidates
    
    def _calculate_semantic_score(
        self, 
        block: TextBlock, 
        section_type: str, 
        language: str
    ) -> Tuple[float, List[str], str]:
        """Calcule le score sémantique d'un bloc pour une section."""
        
        text = block.text.lower().strip()
        if not text:
            return 0.0, [], "Bloc vide"
        
        keywords = self.dictionaries.get_keywords(section_type, language)
        if not keywords:
            return 0.0, [], f"Pas de mots-clés pour {section_type} en {language}"
        
        matched_keywords = []
        total_score = 0.0
        
        # 1. Matching exact des mots-clés
        for keyword in keywords:
            # Fuzzy matching pour robustesse
            best_match = process.extractOne(
                keyword, 
                text.split(), 
                scorer=fuzz.ratio,
                score_cutoff=80  # 80% similarité minimum
            )
            
            if best_match:
                match_word, match_score = best_match
                matched_keywords.append(f"{keyword}->{match_word}({match_score})")
                # Score pondéré par longueur du mot-clé (plus long = plus spécifique)
                weight = len(keyword.split()) * match_score / 100.0
                total_score += weight
        
        # 2. Bonus pour présence de mots-clés multiples
        if len(matched_keywords) > 1:
            total_score *= 1.2  # Bonus 20%
        
        # 3. Bonus position (titres/en-têtes ont plus d'importance)
        if self._looks_like_section_header(block):
            total_score *= 1.5  # Bonus 50% pour en-têtes
        
        # 4. Normalisation du score (0-1)
        normalized_score = min(total_score / 10.0, 1.0)
        
        reasoning = f"{len(matched_keywords)} mots-clés trouvés, score: {normalized_score:.2f}"
        
        return normalized_score, matched_keywords, reasoning
    
    def _looks_like_section_header(self, block: TextBlock) -> bool:
        """Détermine si un bloc ressemble à un titre de section."""
        text = block.text.strip()
        
        # Heuristiques pour identifier un titre
        criteria = []
        
        # 1. Court (< 5 mots généralement)
        word_count = len(text.split())
        criteria.append(word_count <= 5)
        
        # 2. Formatage spécial (gras, taille police plus grande)
        criteria.append(block.is_bold)
        criteria.append(block.font_size > 12.0)  # Supposé plus grand que le texte normal
        
        # 3. Pas de ponctuation finale complexe
        criteria.append(not text.endswith('.') or not text.endswith(','))
        
        # 4. Mayuscules ou première lettre majuscule
        criteria.append(text.isupper() or text.istitle())
        
        # Au moins 2 critères sur 4 pour être considéré comme titre
        return sum(criteria) >= 2
    
    def _build_adjacency_graph(self, text_blocks: List[TextBlock]) -> Dict[str, List[str]]:
        """Construit un graphe d'adjacence spatiale entre blocs."""
        adjacency = {block.id: [] for block in text_blocks}
        
        # Calculer distances entre tous les blocs
        for i, block1 in enumerate(text_blocks):
            for j, block2 in enumerate(text_blocks):
                if i != j:
                    distance = self._calculate_spatial_distance(block1.bbox, block2.bbox)
                    
                    # Si distance < seuil, ils sont "adjacents"
                    if distance < self.contamination_threshold:
                        adjacency[block1.id].append(block2.id)
        
        return adjacency
    
    def _calculate_spatial_distance(self, bbox1: BoundingBox, bbox2: BoundingBox) -> float:
        """Calcule la distance spatiale entre deux bounding boxes."""
        # Distance entre centres
        center1 = np.array([bbox1.center_x, bbox1.center_y])
        center2 = np.array([bbox2.center_x, bbox2.center_y])
        
        return np.linalg.norm(center1 - center2)
    
    def _apply_contamination_guards(
        self, 
        candidates: Dict[str, List[SectionCandidate]], 
        adjacency_graph: Dict[str, List[str]], 
        text_blocks: List[TextBlock]
    ) -> Tuple[Dict[str, str], List[ContaminationRisk]]:
        """Applique les garde-fous anti-contamination."""
        
        validated_mapping = {}
        contamination_risks = []
        
        # Créer un mapping bloc_id -> TextBlock pour lookup rapide
        blocks_lookup = {block.id: block for block in text_blocks}
        
        for block_id, block_candidates in candidates.items():
            if not block_candidates:
                continue
            
            # Meilleur candidat pour ce bloc
            best_candidate = block_candidates[0]
            
            # Garde-fou 1: Score sémantique minimum
            if best_candidate.confidence_score < self.semantic_threshold:
                contamination_risks.append(ContaminationRisk(
                    block_id=block_id,
                    risk_type="low_semantic_confidence",
                    risk_level=1.0 - best_candidate.confidence_score,
                    details={
                        'score': best_candidate.confidence_score,
                        'threshold': self.semantic_threshold,
                        'section_candidate': best_candidate.section_type
                    },
                    recommendation=f"Score trop bas ({best_candidate.confidence_score:.2f}), "
                                  f"augmenter seuil ou enrichir dictionnaire"
                ))
                continue
            
            # Garde-fou 2: Cohérence avec voisins adjacents
            neighbors = adjacency_graph.get(block_id, [])
            conflicting_neighbors = []
            
            for neighbor_id in neighbors:
                if neighbor_id in validated_mapping:
                    neighbor_section = validated_mapping[neighbor_id]
                    if neighbor_section != best_candidate.section_type:
                        # Voisin proche avec section différente = risque contamination
                        neighbor_block = blocks_lookup[neighbor_id]
                        current_block = blocks_lookup[block_id]
                        distance = self._calculate_spatial_distance(
                            current_block.bbox, neighbor_block.bbox
                        )
                        
                        conflicting_neighbors.append({
                            'neighbor_id': neighbor_id,
                            'neighbor_section': neighbor_section,
                            'distance': distance
                        })
            
            if conflicting_neighbors:
                # Calculer niveau de risque basé sur proximité et nombre de conflits
                min_distance = min(cn['distance'] for cn in conflicting_neighbors)
                risk_level = len(conflicting_neighbors) * (self.contamination_threshold - min_distance) / self.contamination_threshold
                risk_level = min(risk_level, 1.0)
                
                contamination_risks.append(ContaminationRisk(
                    block_id=block_id,
                    risk_type="geometric_proximity_conflict",
                    risk_level=risk_level,
                    details={
                        'conflicting_neighbors': conflicting_neighbors,
                        'proposed_section': best_candidate.section_type,
                        'min_distance': min_distance
                    },
                    recommendation="Vérifier manuellement ou ajuster seuils de proximité"
                ))
                
                # Si risque élevé, rejeter ce mapping
                if risk_level > 0.7:
                    continue
            
            # Garde-fou 3: Cohérence interne de section
            section_blocks_so_far = [bid for bid, section in validated_mapping.items() 
                                   if section == best_candidate.section_type]
            
            if section_blocks_so_far:
                # Vérifier dispersion géographique
                section_positions = [blocks_lookup[bid].bbox.center_x for bid in section_blocks_so_far]
                current_position = blocks_lookup[block_id].bbox.center_x
                
                # Si trop éloigné des autres blocs de même section = suspect
                avg_position = np.mean(section_positions)
                distance_to_avg = abs(current_position - avg_position)
                
                if distance_to_avg > 300:  # Seuil arbitraire
                    contamination_risks.append(ContaminationRisk(
                        block_id=block_id,
                        risk_type="section_dispersion",
                        risk_level=min(distance_to_avg / 500.0, 1.0),
                        details={
                            'distance_to_section_center': distance_to_avg,
                            'section_type': best_candidate.section_type,
                            'existing_blocks': len(section_blocks_so_far)
                        },
                        recommendation="Vérifier si bloc appartient vraiment à cette section"
                    ))
            
            # Si on arrive ici, le bloc est validé
            validated_mapping[block_id] = best_candidate.section_type
        
        logger.info(f"⚠️ Validation: {len(validated_mapping)}/{len(candidates)} blocs validés, "
                   f"{len(contamination_risks)} risques détectés")
        
        return validated_mapping, contamination_risks
    
    def _group_blocks_by_section(
        self, 
        validated_mapping: Dict[str, str], 
        text_blocks: List[TextBlock]
    ) -> Dict[str, List[TextBlock]]:
        """Groupe les blocs validés par section."""
        
        sections = {}
        blocks_lookup = {block.id: block for block in text_blocks}
        
        for block_id, section_type in validated_mapping.items():
            if section_type not in sections:
                sections[section_type] = []
            
            block = blocks_lookup[block_id]
            sections[section_type].append(block)
        
        # Trier les blocs dans chaque section par ordre de lecture
        for section_type, blocks in sections.items():
            blocks.sort(key=lambda b: b.reading_order)
        
        return sections
    
    def _calculate_section_confidence_scores(
        self, 
        section_groups: Dict[str, List[TextBlock]], 
        candidates: Dict[str, List[SectionCandidate]]
    ) -> Dict[str, float]:
        """Calcule les scores de confiance par section."""
        
        confidence_scores = {}
        
        for section_type, blocks in section_groups.items():
            section_scores = []
            
            for block in blocks:
                # Récupérer le score du candidat validé pour ce bloc
                block_candidates = candidates.get(block.id, [])
                for candidate in block_candidates:
                    if candidate.section_type == section_type:
                        section_scores.append(candidate.confidence_score)
                        break
            
            if section_scores:
                # Moyenne pondérée (premier bloc = plus important)
                weights = [1.0 / (i + 1) for i in range(len(section_scores))]
                weighted_avg = np.average(section_scores, weights=weights)
                confidence_scores[section_type] = weighted_avg
            else:
                confidence_scores[section_type] = 0.5  # Score neutre par défaut
        
        return confidence_scores
    
    def _calculate_mapping_quality_score(
        self, 
        section_groups: Dict[str, List[TextBlock]], 
        contamination_risks: List[ContaminationRisk], 
        text_blocks: List[TextBlock]
    ) -> float:
        """Calcule un score de qualité global pour le mapping."""
        
        factors = []
        
        # 1. Taux de mapping (blocs mappés / total)
        mapped_blocks = sum(len(blocks) for blocks in section_groups.values())
        mapping_rate = mapped_blocks / len(text_blocks) if text_blocks else 0
        factors.append(mapping_rate)
        
        # 2. Diversité des sections (plus de sections = meilleur)
        section_diversity = min(len(section_groups) / 8.0, 1.0)  # 8 sections = score max
        factors.append(section_diversity)
        
        # 3. Pénalité contamination
        high_risk_contaminations = sum(1 for risk in contamination_risks if risk.risk_level > 0.5)
        contamination_penalty = max(0, 1.0 - high_risk_contaminations * 0.1)
        factors.append(contamination_penalty)
        
        # 4. Équilibrage des sections (éviter 1 section avec tous les blocs)
        if section_groups:
            block_counts = [len(blocks) for blocks in section_groups.values()]
            max_blocks = max(block_counts)
            balance_factor = 1.0 - (max_blocks - np.mean(block_counts)) / mapped_blocks
            factors.append(max(balance_factor, 0))
        
        return np.mean(factors) if factors else 0.0
    
    def _empty_mapping(self) -> SectionMapping:
        """Mapping vide pour cas d'erreur."""
        return SectionMapping(
            sections={},
            confidence_scores={},
            contamination_risks=[],
            unmapped_blocks=[],
            mapping_quality_score=0.0,
            processing_metadata={'error': 'No text blocks provided'}
        )
