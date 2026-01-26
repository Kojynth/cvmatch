"""
CV Scorer - Phase 5: SCORING & métriques avec logs structurés
=============================================================

Calcul de scores de confiance granulaires par champ/section + score global
avec logs structurés traçables et métriques de qualité détaillées.
"""

import json
import hashlib
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from loguru import logger

import numpy as np
from .cv_analyzer import LayoutAnalysis, TextBlock
from .cv_mapper import SectionMapping, ContaminationRisk
from .cv_extractor_advanced import ExtractedData


@dataclass
class FieldConfidence:
    """Score de confiance pour un champ spécifique."""
    field_name: str
    value: Any
    confidence_score: float
    reasoning: str
    source_info: Dict[str, Any]
    validation_checks: Dict[str, bool]


@dataclass
class SectionQualityMetrics:
    """Métriques de qualité pour une section."""
    section_name: str
    completeness_score: float  # 0-1, ratio champs remplis
    confidence_score: float    # 0-1, moyenne confiances champs
    field_scores: List[FieldConfidence]
    data_density: float       # Richesse des données
    validation_score: float   # Score validation (formats, cohérence)


@dataclass
class ExtractionQualityMetrics:
    """Métriques qualité extraction spécifiques."""
    date_parsing_accuracy: float
    entity_recognition_accuracy: float
    section_boundary_accuracy: float
    ocr_quality_score: Optional[float]
    layout_detection_accuracy: float
    contamination_prevention_score: float


@dataclass
class ProcessingLogEntry:
    """Entrée de log structuré."""
    timestamp: str
    phase: str
    operation: str
    duration_ms: float
    status: str  # 'success', 'warning', 'error'
    details: Dict[str, Any]
    rule_applied: Optional[str]
    data_source: str  # bbox, page, block_id
    confidence_impact: Optional[float]


@dataclass
class GlobalQualityMetrics:
    """Métriques de qualité globales."""
    global_confidence_score: float
    data_completeness: float
    extraction_quality: ExtractionQualityMetrics
    section_scores: Dict[str, float]
    processing_time_ms: float
    warnings: List[str]
    recommendations: List[str]
    processing_log: List[ProcessingLogEntry]


class PII_Masker:
    """Masquage PII pour logs sécurisés."""
    
    def __init__(self):
        self.email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        self.phone_pattern = r'(\+33|0)[1-9](?:[0-9]{8})'
        self.name_patterns = [
            r'\b[A-Z][a-z]+ [A-Z][a-z]+\b',  # Prénom Nom
            r'\b[A-Z]{2,} [A-Z][a-z]+\b'     # NOM Prénom
        ]
    
    def mask_text(self, text: str, mask_level: str = 'partial') -> str:
        """Masque les PII dans un texte."""
        if not text:
            return text
        
        import re
        masked_text = text
        
        # Email
        if mask_level == 'full':
            masked_text = re.sub(self.email_pattern, '[EMAIL_MASKED]', masked_text)
        else:
            # Partial: garder début + domaine
            def mask_email(match):
                email = match.group(0)
                if '@' in email:
                    local, domain = email.split('@', 1)
                    return f"{local[:2]}***@{domain}"
                return '[EMAIL]'
            
            masked_text = re.sub(self.email_pattern, mask_email, masked_text)
        
        # Téléphone
        if mask_level == 'full':
            masked_text = re.sub(self.phone_pattern, '[PHONE_MASKED]', masked_text)
        else:
            # Partial: garder début
            def mask_phone(match):
                phone = match.group(0)
                return f"{phone[:4]}***{phone[-2:]}"
            
            masked_text = re.sub(self.phone_pattern, mask_phone, masked_text)
        
        # Noms (heuristique basique)
        if mask_level == 'full':
            for pattern in self.name_patterns:
                masked_text = re.sub(pattern, '[NAME_MASKED]', masked_text)
        
        return masked_text
    
    def hash_sensitive_data(self, data: Any) -> str:
        """Hash des données sensibles pour traçabilité anonyme."""
        text = str(data) if data else ""
        return hashlib.sha256(text.encode()).hexdigest()[:12]


class FieldScorer:
    """Calculateur de scores de confiance par champ."""
    
    # Poids par type de champ
    FIELD_WEIGHTS = {
        'personal_info': {
            'full_name': 0.25,
            'email': 0.20,
            'phone': 0.15,
            'location': 0.15,
            'linkedin_url': 0.10,
            'portfolio_url': 0.10,
            'github_url': 0.05
        },
        'experience': {
            'title': 0.25,
            'company': 0.25,
            'dates': 0.20,
            'description': 0.15,
            'location': 0.10,
            'achievements': 0.05
        },
        'education': {
            'degree': 0.30,
            'institution': 0.25,
            'dates': 0.20,
            'grade': 0.15,
            'specialization': 0.10
        }
    }
    
    def __init__(self):
        self.pii_masker = PII_Masker()
    
    def score_field(
        self, 
        field_name: str, 
        value: Any, 
        section_type: str,
        source_metadata: Dict[str, Any] = None
    ) -> FieldConfidence:
        """Score un champ individuel."""
        
        confidence_score = 0.0
        reasoning_parts = []
        validation_checks = {}
        
        # 1. Présence de valeur
        if value is None or (isinstance(value, str) and not value.strip()):
            return FieldConfidence(
                field_name=field_name,
                value=value,
                confidence_score=0.0,
                reasoning="Champ vide",
                source_info=source_metadata or {},
                validation_checks={'has_value': False}
            )
        
        validation_checks['has_value'] = True
        confidence_score += 0.3  # Base pour présence
        
        # 2. Validation format selon type
        format_score, format_checks = self._validate_field_format(field_name, value)
        confidence_score += format_score * 0.4
        validation_checks.update(format_checks)
        reasoning_parts.append(f"Format: {format_score:.2f}")
        
        # 3. Richesse/complétude du contenu
        content_score = self._score_content_richness(field_name, value)
        confidence_score += content_score * 0.3
        reasoning_parts.append(f"Contenu: {content_score:.2f}")
        
        # 4. Bonus source fiable
        if source_metadata:
            source_score = self._score_source_reliability(source_metadata)
            confidence_score += source_score * 0.1
            reasoning_parts.append(f"Source: {source_score:.2f}")
        
        # Score final normalisé
        final_score = min(confidence_score, 1.0)
        
        return FieldConfidence(
            field_name=field_name,
            value=self.pii_masker.mask_text(str(value)) if isinstance(value, str) else value,
            confidence_score=final_score,
            reasoning=" | ".join(reasoning_parts),
            source_info=source_metadata or {},
            validation_checks=validation_checks
        )
    
    def _validate_field_format(self, field_name: str, value: Any) -> Tuple[float, Dict[str, bool]]:
        """Valide le format d'un champ."""
        checks = {}
        
        if field_name == 'email':
            import re
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            is_valid = bool(re.match(email_pattern, str(value)))
            checks['valid_email_format'] = is_valid
            return 1.0 if is_valid else 0.2, checks
        
        elif field_name == 'phone':
            # Validation basique numéro
            phone_str = str(value).replace(' ', '').replace('-', '').replace('.', '')
            is_numeric = phone_str.replace('+', '').isdigit()
            has_country_code = phone_str.startswith('+') or phone_str.startswith('0')
            checks['is_numeric'] = is_numeric
            checks['has_country_code'] = has_country_code
            
            score = 0.0
            if is_numeric:
                score += 0.5
            if has_country_code:
                score += 0.3
            if len(phone_str) >= 10:
                score += 0.2
            
            return score, checks
        
        elif field_name in ['linkedin_url', 'portfolio_url', 'github_url']:
            import re
            url_pattern = r'^https?://'
            is_url = bool(re.match(url_pattern, str(value)))
            checks['is_url'] = is_url
            
            # Validation domaine spécifique
            domain_valid = False
            if 'linkedin' in field_name:
                domain_valid = 'linkedin.com' in str(value).lower()
            elif 'github' in field_name:
                domain_valid = 'github.com' in str(value).lower()
            else:
                domain_valid = True  # Pas de contrainte pour portfolio
            
            checks['valid_domain'] = domain_valid
            
            score = 0.0
            if is_url:
                score += 0.6
            if domain_valid:
                score += 0.4
            
            return score, checks
        
        elif field_name in ['title', 'company', 'degree', 'institution']:
            # Validation longueur raisonnable
            text_len = len(str(value).strip())
            checks['reasonable_length'] = 3 <= text_len <= 100
            checks['not_too_short'] = text_len >= 3
            checks['not_too_long'] = text_len <= 100
            
            score = 0.5  # Base
            if 3 <= text_len <= 100:
                score = 0.9
            elif text_len < 3:
                score = 0.2
            elif text_len > 100:
                score = 0.6
            
            return score, checks
        
        # Default: validation basique
        checks['has_content'] = bool(str(value).strip())
        return 0.7 if checks['has_content'] else 0.0, checks
    
    def _score_content_richness(self, field_name: str, value: Any) -> float:
        """Score la richesse du contenu."""
        if not value:
            return 0.0
        
        text = str(value).strip()
        
        if field_name == 'description':
            # Plus de détails = mieux pour descriptions
            word_count = len(text.split())
            if word_count >= 50:
                return 1.0
            elif word_count >= 20:
                return 0.8
            elif word_count >= 10:
                return 0.6
            else:
                return 0.3
        
        elif field_name in ['responsibilities', 'achievements']:
            # Vérifier si c'est une liste structurée
            if isinstance(value, list):
                return min(len(value) * 0.2, 1.0)
            else:
                # Compter les puces/séparateurs
                bullet_count = text.count('•') + text.count('-') + text.count('\n')
                return min(bullet_count * 0.3, 1.0)
        
        elif field_name == 'technologies':
            if isinstance(value, list):
                return min(len(value) * 0.15, 1.0)
            else:
                tech_count = len([t for t in text.split(',') if t.strip()])
                return min(tech_count * 0.15, 1.0)
        
        # Score basique longueur
        return min(len(text) / 50.0, 1.0)
    
    def _score_source_reliability(self, source_metadata: Dict[str, Any]) -> float:
        """Score la fiabilité de la source."""
        score = 0.5  # Base
        
        # Bonus si extraction géométrique précise
        if source_metadata.get('has_bbox'):
            score += 0.2
        
        # Bonus si multiple sources concordent
        if source_metadata.get('multiple_sources'):
            score += 0.2
        
        # Bonus si règle spécifique appliquée
        if source_metadata.get('rule_applied'):
            score += 0.1
        
        return min(score, 1.0)


class SectionScorer:
    """Calculateur de scores par section."""
    
    def __init__(self):
        self.field_scorer = FieldScorer()
    
    def score_section(
        self, 
        section_name: str, 
        section_data: Any,
        source_metadata: Dict[str, Any] = None
    ) -> SectionQualityMetrics:
        """Score une section complète."""
        
        field_scores = []
        
        if section_name == 'personal_info' and section_data:
            # Informations personnelles
            for field_name, value in section_data.items():
                if field_name not in ['confidence_score']:  # Skip meta
                    field_score = self.field_scorer.score_field(
                        field_name, value, section_name, source_metadata
                    )
                    field_scores.append(field_score)
        
        elif section_name == 'experiences' and isinstance(section_data, list):
            # Expériences (prendre moyenne du top 3)
            for i, exp in enumerate(section_data[:3]):  # Top 3 seulement
                if isinstance(exp, dict):
                    for field_name, value in exp.items():
                        if field_name not in ['confidence_score', 'extraction_source']:
                            field_score = self.field_scorer.score_field(
                                f"exp_{i}_{field_name}", value, section_name, source_metadata
                            )
                            field_scores.append(field_score)
        
        elif section_name == 'skills' and isinstance(section_data, dict):
            # Compétences
            for category, skills_list in section_data.items():
                field_score = self.field_scorer.score_field(
                    f"skills_{category}", skills_list, section_name, source_metadata
                )
                field_scores.append(field_score)
        
        elif section_name == 'languages' and isinstance(section_data, list):
            # Langues
            for lang in section_data:
                if isinstance(lang, dict):
                    lang_score = self.field_scorer.score_field(
                        f"lang_{lang.get('language', 'unknown')}", lang, section_name, source_metadata
                    )
                    field_scores.append(lang_score)
        
        # Calculs métriques section
        if field_scores:
            confidence_scores = [f.confidence_score for f in field_scores]
            avg_confidence = np.mean(confidence_scores)
            
            # Completeness: ratio champs non-vides
            non_empty_fields = sum(1 for f in field_scores if f.validation_checks.get('has_value', False))
            completeness = non_empty_fields / len(field_scores)
            
            # Data density: richesse moyenne
            data_density = np.mean([self._calculate_field_density(f) for f in field_scores])
            
            # Validation score: ratio validations passées
            total_validations = sum(len(f.validation_checks) for f in field_scores)
            passed_validations = sum(sum(f.validation_checks.values()) for f in field_scores)
            validation_score = passed_validations / max(total_validations, 1)
        else:
            avg_confidence = 0.0
            completeness = 0.0
            data_density = 0.0
            validation_score = 0.0
        
        return SectionQualityMetrics(
            section_name=section_name,
            completeness_score=completeness,
            confidence_score=avg_confidence,
            field_scores=field_scores,
            data_density=data_density,
            validation_score=validation_score
        )
    
    def _calculate_field_density(self, field_score: FieldConfidence) -> float:
        """Calcule la densité de données d'un champ."""
        if not field_score.value:
            return 0.0
        
        if isinstance(field_score.value, str):
            return min(len(field_score.value.split()) / 10.0, 1.0)
        elif isinstance(field_score.value, list):
            return min(len(field_score.value) / 5.0, 1.0)
        elif isinstance(field_score.value, dict):
            return min(len([k for k, v in field_score.value.items() if v]) / 5.0, 1.0)
        
        return 0.5  # Default


class ExtractionQualityAnalyzer:
    """Analyseur de qualité d'extraction spécifique."""
    
    def analyze_extraction_quality(
        self,
        extracted_data: ExtractedData,
        layout_analysis: LayoutAnalysis,
        section_mapping: SectionMapping,
        processing_log: List[ProcessingLogEntry]
    ) -> ExtractionQualityMetrics:
        """Analyse la qualité technique de l'extraction."""
        
        # 1. Date parsing accuracy
        date_accuracy = self._calculate_date_parsing_accuracy(extracted_data)
        
        # 2. Entity recognition accuracy (heuristique)
        entity_accuracy = self._calculate_entity_recognition_accuracy(extracted_data)
        
        # 3. Section boundary accuracy
        boundary_accuracy = 1.0 - (len(section_mapping.contamination_risks) * 0.1)
        boundary_accuracy = max(boundary_accuracy, 0.0)
        
        # 4. OCR quality (si applicable)
        ocr_quality = self._assess_ocr_quality(processing_log)
        
        # 5. Layout detection accuracy
        layout_accuracy = layout_analysis.confidence_score
        
        # 6. Contamination prevention score
        contamination_score = section_mapping.mapping_quality_score
        
        return ExtractionQualityMetrics(
            date_parsing_accuracy=date_accuracy,
            entity_recognition_accuracy=entity_accuracy,
            section_boundary_accuracy=boundary_accuracy,
            ocr_quality_score=ocr_quality,
            layout_detection_accuracy=layout_accuracy,
            contamination_prevention_score=contamination_score
        )
    
    def _calculate_date_parsing_accuracy(self, data: ExtractedData) -> float:
        """Calcule la précision de parsing des dates."""
        total_date_fields = 0
        valid_dates = 0
        
        # Compter dans expériences
        for exp in data.experiences:
            if exp.date_range:
                total_date_fields += 1
                if exp.date_range.start_date or exp.date_range.is_current:
                    valid_dates += 1
        
        # Compter dans formation
        for edu in data.education:
            if edu.date_range:
                total_date_fields += 1
                if edu.date_range.start_date:
                    valid_dates += 1
        
        return valid_dates / max(total_date_fields, 1)
    
    def _calculate_entity_recognition_accuracy(self, data: ExtractedData) -> float:
        """Estime la précision de reconnaissance d'entités."""
        accuracy_factors = []
        
        # Noms d'entreprises (heuristique : longueur raisonnable, casse correcte)
        company_scores = []
        for exp in data.experiences:
            if exp.company:
                score = 1.0 if 2 <= len(exp.company.split()) <= 6 else 0.5
                company_scores.append(score)
        
        if company_scores:
            accuracy_factors.append(np.mean(company_scores))
        
        # Emails valides
        if data.personal_info and data.personal_info.email:
            import re
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            email_valid = bool(re.match(email_pattern, data.personal_info.email))
            accuracy_factors.append(1.0 if email_valid else 0.3)
        
        return np.mean(accuracy_factors) if accuracy_factors else 0.7
    
    def _assess_ocr_quality(self, processing_log: List[ProcessingLogEntry]) -> Optional[float]:
        """Évalue la qualité OCR si utilisée."""
        ocr_entries = [entry for entry in processing_log if 'ocr' in entry.operation.lower()]
        
        if not ocr_entries:
            return None  # Pas d'OCR utilisée
        
        # Heuristique basée sur confiance OCR moyenne
        ocr_confidences = []
        for entry in ocr_entries:
            if entry.confidence_impact:
                ocr_confidences.append(entry.confidence_impact)
        
        return np.mean(ocr_confidences) if ocr_confidences else 0.5


class CVScorer:
    """Calculateur principal de scores CV."""
    
    def __init__(self, mask_pii: bool = True):
        self.mask_pii = mask_pii
        self.section_scorer = SectionScorer()
        self.quality_analyzer = ExtractionQualityAnalyzer()
        self.processing_log = []
        self.start_time = datetime.now()
    
    def log_processing_step(
        self,
        phase: str,
        operation: str,
        duration_ms: float,
        status: str = 'success',
        details: Dict[str, Any] = None,
        rule_applied: str = None,
        data_source: str = None,
        confidence_impact: float = None
    ):
        """Enregistre une étape de traitement."""
        entry = ProcessingLogEntry(
            timestamp=datetime.now().isoformat(),
            phase=phase,
            operation=operation,
            duration_ms=duration_ms,
            status=status,
            details=details or {},
            rule_applied=rule_applied,
            data_source=data_source or 'unknown',
            confidence_impact=confidence_impact
        )
        
        self.processing_log.append(entry)
        
        if self.mask_pii and entry.details:
            # Masquer PII dans les logs
            pii_masker = PII_Masker()
            for key, value in entry.details.items():
                if isinstance(value, str):
                    entry.details[key] = pii_masker.mask_text(value)
    
    def calculate_comprehensive_scores(
        self,
        extracted_data: ExtractedData,
        layout_analysis: LayoutAnalysis,
        section_mapping: SectionMapping,
        normalized_data: Dict[str, Any]
    ) -> GlobalQualityMetrics:
        """
        Calcule les scores complets avec métriques granulaires.
        
        Returns:
            GlobalQualityMetrics avec tous les scores et logs
        """
        logger.info("📊 Calcul scores de qualité complets")
        
        # 1. Scores par section
        section_scores = {}
        section_metrics = {}
        
        for section_name, section_data in normalized_data.items():
            if section_name not in ['normalization_metadata']:
                section_metric = self.section_scorer.score_section(section_name, section_data)
                section_metrics[section_name] = section_metric
                section_scores[section_name] = section_metric.confidence_score
        
        # 2. Score global pondéré
        section_weights = {
            'experiences': 0.35,
            'personal_info': 0.25,
            'skills': 0.15,
            'education': 0.15,
            'languages': 0.05,
            'projects': 0.05
        }
        
        global_score = 0.0
        total_weight = 0.0
        
        for section, weight in section_weights.items():
            if section in section_scores:
                global_score += section_scores[section] * weight
                total_weight += weight
        
        global_score = global_score / max(total_weight, 1.0)
        
        # 3. Completeness (sections présentes)
        expected_sections = ['personal_info', 'experiences', 'skills']
        present_sections = [s for s in expected_sections if section_scores.get(s, 0) > 0]
        completeness = len(present_sections) / len(expected_sections)
        
        # 4. Qualité extraction technique
        extraction_quality = self.quality_analyzer.analyze_extraction_quality(
            extracted_data, layout_analysis, section_mapping, self.processing_log
        )
        
        # 5. Génération warnings/recommandations
        warnings, recommendations = self._generate_insights(
            section_metrics, extraction_quality, global_score
        )
        
        # 6. Temps de traitement total
        processing_time = (datetime.now() - self.start_time).total_seconds() * 1000
        
        return GlobalQualityMetrics(
            global_confidence_score=global_score,
            data_completeness=completeness,
            extraction_quality=extraction_quality,
            section_scores=section_scores,
            processing_time_ms=processing_time,
            warnings=warnings,
            recommendations=recommendations,
            processing_log=self.processing_log
        )
    
    def _generate_insights(
        self,
        section_metrics: Dict[str, SectionQualityMetrics],
        extraction_quality: ExtractionQualityMetrics,
        global_score: float
    ) -> Tuple[List[str], List[str]]:
        """Génère warnings et recommandations."""
        warnings = []
        recommendations = []
        
        # Warnings basés sur scores faibles
        if global_score < 0.6:
            warnings.append(f"Score global faible ({global_score:.2f}) - Qualité extraction à vérifier")
        
        if extraction_quality.date_parsing_accuracy < 0.8:
            warnings.append(f"Précision dates faible ({extraction_quality.date_parsing_accuracy:.2f})")
        
        if extraction_quality.section_boundary_accuracy < 0.9:
            warnings.append(f"Risques contamination détectés ({extraction_quality.section_boundary_accuracy:.2f})")
        
        # Sections manquantes/faibles
        for section_name, metrics in section_metrics.items():
            if metrics.confidence_score < 0.5:
                warnings.append(f"Section {section_name} : confiance faible ({metrics.confidence_score:.2f})")
            
            if metrics.completeness_score < 0.3:
                warnings.append(f"Section {section_name} : données incomplètes ({metrics.completeness_score:.2f})")
        
        # Recommandations
        if global_score < 0.8:
            recommendations.append("Vérifier la qualité du document source (scan, résolution)")
        
        if 'experiences' in section_metrics and section_metrics['experiences'].confidence_score < 0.7:
            recommendations.append("Améliorer l'extraction des expériences - vérifier format dates/entreprises")
        
        if extraction_quality.ocr_quality_score and extraction_quality.ocr_quality_score < 0.7:
            recommendations.append("Qualité OCR faible - utiliser document natif si possible")
        
        return warnings, recommendations
