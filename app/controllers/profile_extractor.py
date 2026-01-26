"""
Profile Extractor Controller - Orchestrateur d'extraction de profil
==================================================================

Coordonne l'extraction complète d'un profil utilisateur en combinant
l'analyse CV et l'extraction LinkedIn pour créer un profil ultra-complet.
"""

import json
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from pathlib import Path
# PATCH-PII: Remplacement par logger sécurisé
from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG
logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)

from PySide6.QtCore import QObject, QThread, Signal
from sqlmodel import Session

from ..models.database import get_session
from ..models.user_profile import UserProfile
from ..workers.cv_extractor import CVExtractor, ExtractionParams
from ..workers.linkedin_extractor import LinkedInExtractor, LinkedInExtractionParams
from ..common.sections import ALL_SECTIONS, TOTAL_SECTIONS_COUNT
from ..utils.extraction_logger import get_extraction_logger


class ProfileExtractionController(QObject):
    """Contrôleur principal pour l'extraction de profil complet."""
    
    # Signaux pour l'interface utilisateur
    extraction_started = Signal(str)  # message de démarrage
    progress_updated = Signal(int, str)  # pourcentage, étape
    cv_extraction_completed = Signal(dict)  # données CV
    linkedin_extraction_completed = Signal(dict)  # données LinkedIn
    profile_updated = Signal(UserProfile)  # profil mis à jour
    extraction_completed = Signal(UserProfile)  # extraction complète terminée
    extraction_failed = Signal(str)  # erreur
    
    def __init__(self):
        super().__init__()
        self.current_profile: Optional[UserProfile] = None
        self.cv_extractor: Optional[CVExtractor] = None
        self.linkedin_extractor: Optional[LinkedInExtractor] = None
        self.cv_results: Optional[Dict[str, Any]] = None
        self.linkedin_results: Optional[Dict[str, Any]] = None
        self.extraction_logger = get_extraction_logger()
        self.extraction_start_time: Optional[datetime] = None
    
    def extract_complete_profile(
        self, 
        profile: UserProfile,
        cv_params: Optional[ExtractionParams] = None,
        linkedin_params: Optional[LinkedInExtractionParams] = None
    ):
        """Lance l'extraction complète d'un profil (CV + LinkedIn)."""
        try:
            self.current_profile = profile
            self.extraction_start_time = datetime.now()
            
            # PATCH-PII: Éviter exposition nom utilisateur
            logger.info("Début extraction complète pour profile_id=%s", profile.id)
            
            # Démarrer le log d'extraction spécialisé
            cv_path = profile.master_cv_path or "Aucun CV"
            log_file = self.extraction_logger.start_extraction_session(str(profile.id), cv_path)
            
            # Configurer la redirection des logs détaillés de tous les modules d'extraction
            key_loggers = [
                "app.workers.cv_extractor",
                "app.utils.experience_filters", 
                "app.utils.certification_router",
                "app.utils.academic_internship_handler", 
                "app.utils.extraction_mapper",
                "app.utils.overfitting_monitor",
                "app.utils.boundary_guards",
                "app.utils.org_sieve",
                "app.utils.education_extractor_enhanced",
                "app.utils.unified_reporter"
            ]
            self.extraction_logger.setup_multiple_loggers_redirection(key_loggers)
            
            self.extraction_logger.log_info(f"🚀 DÉBUT EXTRACTION COMPLÈTE")
            self.extraction_logger.log_info(f"Mode: CV + LinkedIn")
            
            # Émission signal UI avec nom anonymisé
            self.extraction_started.emit(f"Extraction complète du profil [ID:{profile.id}]")
            
            # Étape 1 : Extraction du CV
            if profile.master_cv_path and Path(profile.master_cv_path).exists():
                self.extraction_logger.log_info(f"📄 CV trouvé: {Path(profile.master_cv_path).name}")
                self._start_cv_extraction(profile.master_cv_path, cv_params)
            else:
                self.extraction_logger.log_warning("⚠️ Pas de CV maître trouvé, extraction LinkedIn seulement")
                logger.warning("Pas de CV maître trouvé, extraction LinkedIn seulement")
                self._start_linkedin_extraction(linkedin_params)
                
        except Exception as e:
            error_msg = f"Erreur lors du démarrage de l'extraction : {e}"
            logger.error(error_msg)
            if hasattr(self, 'extraction_logger') and self.extraction_logger.extraction_started:
                self.extraction_logger.log_error(error_msg)
                self.extraction_logger.end_extraction_session(success=False)
            self.extraction_failed.emit(str(e))
    
    def _start_cv_extraction(self, cv_path: str, params: Optional[ExtractionParams] = None):
        """Démarre l'extraction du CV."""
        try:
            self.extraction_logger.log_progress(5, "Initialisation de l'extraction CV...")
            self.progress_updated.emit(5, "Initialisation de l'extraction CV...")
            
            # Configuration par défaut optimisée
            if not params:
                params = ExtractionParams(
                    extract_detailed_skills=True,
                    extract_soft_skills=True,
                    extract_achievements=True,
                    extract_linkedin_info=True,
                    extract_references=True,
                    include_confidence_scores=True,
                    language="fr"
                )
            
            self.extraction_logger.log_info(f"📋 Configuration extraction:")
            self.extraction_logger.log_debug(f"   - Compétences détaillées: {params.extract_detailed_skills}")
            self.extraction_logger.log_debug(f"   - Soft skills: {params.extract_soft_skills}")
            self.extraction_logger.log_debug(f"   - Réalisations: {params.extract_achievements}")
            self.extraction_logger.log_debug(f"   - Références: {params.extract_references}")
            self.extraction_logger.log_debug(f"   - Langue: {params.language}")
            
            # Créer et configurer l'extracteur CV
            self.extraction_logger.log_info("🔧 Création de l'extracteur CV...")
            raw_text = ""
            try:
                raw_text = self.current_profile.master_cv_content or ""
                if not raw_text and self.current_profile.master_cv_path:
                    from ..utils.parsers import DocumentParser

                    raw_text = DocumentParser().parse_document(self.current_profile.master_cv_path)
            except Exception as exc:
                logger.warning("Unable to load CV text for LLM extraction: %s", exc)

            self.cv_extractor = CVExtractor(cv_path, params, raw_text=raw_text)
            
            # Connecter les signaux
            self.cv_extractor.progress_updated.connect(self._on_cv_progress)
            self.cv_extractor.section_extracted.connect(self._on_cv_section_extracted)
            self.cv_extractor.extraction_completed.connect(self._on_cv_extraction_completed)
            self.cv_extractor.extraction_failed.connect(self._on_cv_extraction_failed)
            
            # Démarrer l'extraction
            self.extraction_logger.log_info("🚀 Démarrage de l'extraction CV...")
            self.cv_extractor.start()
            
        except Exception as e:
            error_msg = f"Erreur démarrage extraction CV : {e}"
            logger.error(error_msg)
            self.extraction_logger.log_error(error_msg)
            self.extraction_failed.emit(f"Erreur extraction CV : {e}")
    
    def _start_linkedin_extraction(self, params: Optional[LinkedInExtractionParams] = None):
        """Démarre l'extraction LinkedIn."""
        try:
            if not self.current_profile.linkedin_url:
                logger.info("Pas d'URL LinkedIn, finalisation du profil...")
                self._finalize_profile_extraction()
                return
            
            progress_offset = 50 if self.cv_results else 10
            self.progress_updated.emit(progress_offset, "Initialisation de l'extraction LinkedIn...")
            
            # Configuration par défaut
            if not params:
                params = LinkedInExtractionParams(
                    method="scraping",  # méthode principale
                    use_headless_browser=True,
                    extract_recommendations=True,
                    extract_connections=False,  # respecter la vie privée
                    respect_robots_txt=True,
                    delay_between_requests=2.0
                )
            
            # Créer et configurer l'extracteur LinkedIn
            self.linkedin_extractor = LinkedInExtractor(self.current_profile.linkedin_url, params)
            
            # Connecter les signaux
            self.linkedin_extractor.progress_updated.connect(self._on_linkedin_progress)
            self.linkedin_extractor.section_extracted.connect(self._on_linkedin_section_extracted)
            self.linkedin_extractor.extraction_completed.connect(self._on_linkedin_extraction_completed)
            self.linkedin_extractor.extraction_failed.connect(self._on_linkedin_extraction_failed)
            self.linkedin_extractor.requires_login.connect(self._on_linkedin_login_required)
            
            # Démarrer l'extraction
            self.linkedin_extractor.start()
            
        except Exception as e:
            logger.error(f"Erreur démarrage extraction LinkedIn : {e}")
            # Continuer sans LinkedIn
            self._finalize_profile_extraction()
    
    def _on_cv_progress(self, percentage: int, message: str):
        """Gère la progression de l'extraction CV."""
        # Mapper sur la première moitié de la progression totale
        total_percentage = min(percentage // 2, 50)
        self.extraction_logger.log_progress(total_percentage, f"CV: {message}")
        self.progress_updated.emit(total_percentage, f"CV: {message}")
    
    def _on_cv_section_extracted(self, section_name: str, data: dict):
        """Gère l'extraction d'une section CV."""
        logger.info(f"Section CV extraite : {section_name}")
        
        # Log spécialisé avec résumé des données
        if isinstance(data, dict):
            items_count = sum(len(v) if isinstance(v, list) else 1 for v in data.values() if v)
            confidence = data.get('confidence', None)
            self.extraction_logger.log_section_result(section_name, data, confidence)
        else:
            self.extraction_logger.log_section_result(section_name, data)
        # Mise à jour temps réel possible ici
    
    def _on_cv_extraction_completed(self, results: dict):
        """Gère la fin de l'extraction CV."""
        try:
            logger.info("Extraction CV terminée avec succès")
            self.extraction_logger.log_info("✅ EXTRACTION CV TERMINÉE AVEC SUCCÈS")
            
            # Résumé des résultats dans le log spécialisé
            sections_extraites = len([k for k, v in results.items() if v and k != 'metadata'])
            self.extraction_logger.log_info(f"📊 Résumé: {sections_extraites} sections extraites")
            
            self.cv_results = results
            
            # Sauvegarder immédiatement les résultats CV
            self._save_cv_results_to_profile()
            
            self.cv_extraction_completed.emit(results)
            
            # Passer à LinkedIn
            self._start_linkedin_extraction()
            
        except Exception as e:
            logger.error(f"Erreur traitement résultats CV : {e}")
            self.extraction_failed.emit(f"Erreur traitement CV : {e}")
    
    def _on_cv_extraction_failed(self, error_message: str):
        """Gère l'échec de l'extraction CV."""
        logger.error(f"Échec extraction CV : {error_message}")
        self.extraction_logger.log_error(f"❌ ÉCHEC EXTRACTION CV: {error_message}")
        
        # Continuer avec LinkedIn même si le CV échoue
        self.extraction_logger.log_info("🔄 Continuation avec LinkedIn malgré l'échec du CV...")
        self.progress_updated.emit(50, "CV échoué, tentative LinkedIn...")
        self._start_linkedin_extraction()
    
    def _on_linkedin_progress(self, percentage: int, message: str):
        """Gère la progression de l'extraction LinkedIn."""
        # Mapper sur la seconde moitié de la progression totale
        base_progress = 50 if self.cv_results else 0
        total_percentage = base_progress + min(percentage // 2, 50)
        self.progress_updated.emit(total_percentage, f"LinkedIn: {message}")
    
    def _on_linkedin_section_extracted(self, section_name: str, data: dict):
        """Gère l'extraction d'une section LinkedIn."""
        logger.info(f"Section LinkedIn extraite : {section_name}")
    
    def _on_linkedin_extraction_completed(self, results: dict):
        """Gère la fin de l'extraction LinkedIn."""
        try:
            logger.info("Extraction LinkedIn terminée avec succès")
            self.linkedin_results = results
            
            # Sauvegarder les résultats LinkedIn
            self._save_linkedin_results_to_profile()
            
            self.linkedin_extraction_completed.emit(results)
            
            # Finaliser le profil
            self._finalize_profile_extraction()
            
        except Exception as e:
            logger.error(f"Erreur traitement résultats LinkedIn : {e}")
            # Finaliser quand même avec les données CV
            self._finalize_profile_extraction()
    
    def _on_linkedin_extraction_failed(self, error_message: str):
        """Gère l'échec de l'extraction LinkedIn."""
        logger.warning(f"Échec extraction LinkedIn : {error_message}")
        
        # Finaliser avec les données CV seulement
        self._finalize_profile_extraction()
    
    def _on_linkedin_login_required(self):
        """Gère la demande de connexion LinkedIn."""
        logger.info("Connexion LinkedIn requise - extraction en mode public")
        # L'extracteur LinkedIn continuera en mode public
    
    def _save_cv_results_to_profile(self):
        """Sauvegarde les résultats CV dans le profil."""
        if not self.cv_results or not self.current_profile:
            return
        
        try:
            # Application du garde-fou schéma avant finalisation
            from ..utils.schema_guard import sanitize_extracted_payload, log_schema_types
            
            # Logging des types avant sécurisation
            log_schema_types(self.cv_results, "controller-before")
            
            # Sécurisation du schéma
            self.cv_results = sanitize_extracted_payload(self.cv_results)
            
            # Logging des types après sécurisation
            log_schema_types(self.cv_results, "controller-after")

            from ..utils.profile_json import (
                apply_profile_json_to_profile,
                has_profile_json_content,
                map_payload_to_profile_json,
                normalize_profile_json,
                save_profile_json,
                save_profile_json_cache,
            )

            profile_json = self.cv_results.get("profile_json")
            if not (isinstance(profile_json, dict) and has_profile_json_content(profile_json)):
                profile_json = map_payload_to_profile_json(self.cv_results, source="cv")

            if has_profile_json_content(profile_json):
                apply_profile_json_to_profile(self.current_profile, profile_json)
                save_profile_json(profile_json, "cv")
                normalized = normalize_profile_json(profile_json)
                if self.current_profile.id:
                    save_profile_json_cache(self.current_profile.id, normalized)

            if self.cv_results.get("soft_skills"):
                self.current_profile.extracted_soft_skills = self.cv_results["soft_skills"]

            # Mise a jour timestamp
            self.current_profile.updated_at = datetime.now()
            
            # Sauvegarder en base
            with get_session() as session:
                session.add(self.current_profile)
                session.commit()
                session.refresh(self.current_profile)
            
            logger.info("Résultats CV sauvegardés dans le profil")
            
        except Exception as e:
            logger.error(f"Erreur sauvegarde résultats CV : {e}")
    
    def _save_linkedin_results_to_profile(self):
        """Sauvegarde les résultats LinkedIn dans le profil."""
        if not self.linkedin_results or not self.current_profile:
            return
        
        try:
            # Sauvegarder les données LinkedIn
            self.current_profile.linkedin_data = self.linkedin_results
            self.current_profile.linkedin_last_sync = datetime.now()
            
            # Déterminer le statut de sync
            if self.linkedin_results.get('requires_manual_input'):
                self.current_profile.linkedin_sync_status = "manual_required"
            elif self.linkedin_results.get('extraction_metadata', {}).get('data_completeness', 0) > 50:
                self.current_profile.linkedin_sync_status = "success"
            else:
                self.current_profile.linkedin_sync_status = "partial"
            
            # Enrichir les données CV avec LinkedIn si possible
            from ..utils.profile_json import (
                apply_profile_json_to_profile,
                has_profile_json_content,
                map_payload_to_profile_json,
                normalize_profile_json,
                save_profile_json,
                save_profile_json_cache,
            )

            profile_json = self.linkedin_results.get("profile_json")
            if not (isinstance(profile_json, dict) and has_profile_json_content(profile_json)):
                profile_json = map_payload_to_profile_json(self.linkedin_results, source="linkedin")

            if has_profile_json_content(profile_json):
                apply_profile_json_to_profile(self.current_profile, profile_json)
                save_profile_json(profile_json, "linkedin")
                normalized = normalize_profile_json(profile_json)
                if self.current_profile.id:
                    save_profile_json_cache(self.current_profile.id, normalized)
            else:
                # Fallback to legacy merge for non-JSON payloads
                self._merge_linkedin_with_cv_data()

                # Peupler les champs extracted_* vides depuis LinkedIn
                self._populate_extracted_from_linkedin()


            # Mise à jour timestamp
            self.current_profile.updated_at = datetime.now()
            
            # Sauvegarder en base
            with get_session() as session:
                session.add(self.current_profile)
                session.commit()
                session.refresh(self.current_profile)
            
            logger.info("Résultats LinkedIn sauvegardés dans le profil")
            
        except Exception as e:
            logger.error(f"Erreur sauvegarde résultats LinkedIn : {e}")
    
    def _merge_linkedin_with_cv_data(self):
        """Fusionne intelligemment les données LinkedIn avec celles du CV."""
        if not self.linkedin_results or not self.current_profile:
            return
        
        try:
            linkedin_data = self.linkedin_results
            
            # Enrichir les informations personnelles
            if linkedin_data.get('basic_info'):
                linkedin_basic = linkedin_data['basic_info']
                cv_personal = self.current_profile.extracted_personal_info or {}
                
                # Ajouter des infos manquantes
                if linkedin_basic.get('headline') and not cv_personal.get('title'):
                    cv_personal['linkedin_headline'] = linkedin_basic['headline']
                
                if linkedin_basic.get('location') and not cv_personal.get('location'):
                    cv_personal['location'] = linkedin_basic['location']
                
                if linkedin_basic.get('connections_count'):
                    cv_personal['linkedin_connections'] = linkedin_basic['connections_count']
                
                self.current_profile.extracted_personal_info = cv_personal
            
            # Enrichir les expériences avec des détails LinkedIn
            if linkedin_data.get('experience') and self.current_profile.extracted_experiences:
                self._merge_experiences_data(linkedin_data['experience'])
            
            # Enrichir les compétences avec les endorsements LinkedIn
            if linkedin_data.get('skills') and self.current_profile.extracted_skills:
                self._merge_skills_data(linkedin_data['skills'])
            
            # Ajouter les recommandations LinkedIn (avec déduplication)
            if linkedin_data.get('recommendations'):
                if not self.current_profile.extracted_references:
                    self.current_profile.extracted_references = []

                existing_refs = self.current_profile.extracted_references
                for rec in linkedin_data['recommendations']:
                    # Vérifier si cette recommandation existe déjà (par auteur + début de texte)
                    is_duplicate = any(
                        existing.get('author') == rec.get('author') and
                        existing.get('text', '')[:50] == rec.get('text', '')[:50]
                        for existing in existing_refs
                    )
                    if not is_duplicate:
                        linkedin_ref = {
                            'type': 'linkedin_recommendation',
                            'author': rec.get('author'),
                            'relationship': rec.get('relationship'),
                            'text': rec.get('text'),
                            'source': 'LinkedIn'
                        }
                        existing_refs.append(linkedin_ref)
                        logger.debug(f"Ajout recommandation de: {rec.get('author', 'N/A')}")
                    else:
                        logger.debug(f"Recommandation déjà présente de: {rec.get('author', 'N/A')}")
            
            logger.info("Données LinkedIn fusionnées avec succès")
            
        except Exception as e:
            logger.error(f"Erreur fusion données LinkedIn : {e}")
    
    def _merge_experiences_data(self, linkedin_experiences: List[Dict[str, Any]]):
        """Fusionne les expériences LinkedIn avec celles du CV.

        Évite les doublons en vérifiant si l'expérience existe déjà avant d'ajouter.
        """
        try:
            cv_experiences = self.current_profile.extracted_experiences or []

            for linkedin_exp in linkedin_experiences:
                # Chercher une expérience correspondante dans le CV
                matching_cv_exp = None
                for cv_exp in cv_experiences:
                    if self._experiences_match(cv_exp, linkedin_exp):
                        matching_cv_exp = cv_exp
                        break

                if matching_cv_exp:
                    # Enrichir l'expérience CV avec les données LinkedIn
                    if linkedin_exp.get('description') and not matching_cv_exp.get('description'):
                        matching_cv_exp['linkedin_description'] = linkedin_exp['description']

                    matching_cv_exp['linkedin_verified'] = True
                else:
                    # Vérifier si cette expérience LinkedIn existe déjà (éviter doublons)
                    already_exists = any(
                        self._experiences_match(existing, linkedin_exp)
                        for existing in cv_experiences
                    )
                    if not already_exists:
                        linkedin_exp['source'] = 'LinkedIn'
                        cv_experiences.append(linkedin_exp)
                        logger.debug(f"Ajout expérience LinkedIn: {linkedin_exp.get('title', 'N/A')}")
                    else:
                        logger.debug(f"Expérience LinkedIn déjà présente: {linkedin_exp.get('title', 'N/A')}")

            self.current_profile.extracted_experiences = cv_experiences

        except Exception as e:
            logger.error(f"Erreur fusion expériences : {e}")
    
    def _experiences_match(self, cv_exp: Dict[str, Any], linkedin_exp: Dict[str, Any]) -> bool:
        """Détermine si deux expériences correspondent."""
        try:
            # Comparaison par entreprise et titre
            cv_company = cv_exp.get('company', '').lower()
            linkedin_company = linkedin_exp.get('company', '').lower()
            
            cv_title = cv_exp.get('title', '').lower()
            linkedin_title = linkedin_exp.get('title', '').lower()
            
            # Match si entreprise similaire ET titre similaire
            company_match = cv_company in linkedin_company or linkedin_company in cv_company
            title_match = cv_title in linkedin_title or linkedin_title in cv_title
            
            return company_match and title_match
            
        except Exception:
            return False
    
    def _merge_skills_data(self, linkedin_skills: List[Dict[str, Any]]):
        """Fusionne les compétences LinkedIn avec celles du CV."""
        try:
            cv_skills = self.current_profile.extracted_skills or {}
            
            # Ajouter les endorsements LinkedIn
            linkedin_skills_dict = {}
            for skill in linkedin_skills:
                skill_name = skill.get('name', '').lower()
                endorsements = skill.get('endorsements', 0)
                
                linkedin_skills_dict[skill_name] = {
                    'name': skill.get('name'),
                    'endorsements': endorsements,
                    'source': 'LinkedIn'
                }
            
            # Enrichir les compétences existantes
            for category, skills_list in cv_skills.items():
                if isinstance(skills_list, list):
                    enriched_skills = []
                    for skill in skills_list:
                        skill_name = skill.lower() if isinstance(skill, str) else skill.get('name', '').lower()
                        
                        if skill_name in linkedin_skills_dict:
                            # Enrichir avec les données LinkedIn
                            if isinstance(skill, str):
                                enriched_skill = {
                                    'name': skill,
                                    'linkedin_endorsements': linkedin_skills_dict[skill_name]['endorsements']
                                }
                            else:
                                enriched_skill = skill.copy()
                                enriched_skill['linkedin_endorsements'] = linkedin_skills_dict[skill_name]['endorsements']
                            
                            enriched_skills.append(enriched_skill)
                        else:
                            enriched_skills.append(skill)
                    
                    cv_skills[category] = enriched_skills
            
            # Ajouter une catégorie spéciale pour les compétences LinkedIn non trouvées dans le CV
            linkedin_only_skills = []
            for skill_name, skill_data in linkedin_skills_dict.items():
                found_in_cv = False
                for category, skills_list in cv_skills.items():
                    if isinstance(skills_list, list):
                        for skill in skills_list:
                            cv_skill_name = skill.lower() if isinstance(skill, str) else skill.get('name', '').lower()
                            if skill_name == cv_skill_name:
                                found_in_cv = True
                                break
                    if found_in_cv:
                        break
                
                if not found_in_cv and skill_data['endorsements'] > 0:
                    linkedin_only_skills.append(skill_data)
            
            if linkedin_only_skills:
                cv_skills['linkedin_endorsed'] = linkedin_only_skills
            
            self.current_profile.extracted_skills = cv_skills
            
        except Exception as e:
            logger.error(f"Erreur fusion compétences : {e}")

    def _populate_extracted_from_linkedin(self):
        """
        Peuple les champs extracted_* à partir des données LinkedIn.

        Crée des entrées même si aucune donnée CV n'existe.
        Chaque élément est marqué avec source='LinkedIn'.
        """
        if not self.linkedin_results or not self.current_profile:
            return

        try:
            linkedin_data = self.linkedin_results

            # Expériences: créer si vide, sinon fusion déjà faite
            if linkedin_data.get('experience') and not self.current_profile.extracted_experiences:
                self.current_profile.extracted_experiences = [
                    {**exp, 'source': 'LinkedIn'} for exp in linkedin_data['experience']
                ]
                logger.info(f"Créé {len(linkedin_data['experience'])} expériences depuis LinkedIn")

            # Education: créer si vide
            if linkedin_data.get('education') and not self.current_profile.extracted_education:
                self.current_profile.extracted_education = [
                    {**edu, 'source': 'LinkedIn'} for edu in linkedin_data['education']
                ]
                logger.info(f"Créé {len(linkedin_data['education'])} formations depuis LinkedIn")

            # Compétences: créer si vide
            if linkedin_data.get('skills') and not self.current_profile.extracted_skills:
                # Convertir liste de compétences LinkedIn en format dict par catégorie
                linkedin_skills = []
                for skill in linkedin_data['skills']:
                    skill_entry = {
                        'name': skill.get('name', skill) if isinstance(skill, dict) else skill,
                        'source': 'LinkedIn'
                    }
                    if isinstance(skill, dict) and skill.get('endorsements'):
                        skill_entry['linkedin_endorsements'] = skill['endorsements']
                    linkedin_skills.append(skill_entry)

                self.current_profile.extracted_skills = {'linkedin': linkedin_skills}
                logger.info(f"Créé {len(linkedin_skills)} compétences depuis LinkedIn")

            # Langues: créer si vide
            if linkedin_data.get('languages') and not self.current_profile.extracted_languages:
                self.current_profile.extracted_languages = [
                    {**lang, 'source': 'LinkedIn'} if isinstance(lang, dict)
                    else {'name': lang, 'source': 'LinkedIn'}
                    for lang in linkedin_data['languages']
                ]
                logger.info(f"Créé {len(linkedin_data['languages'])} langues depuis LinkedIn")

            # Certifications: créer si vide
            if linkedin_data.get('certifications') and not self.current_profile.extracted_certifications:
                self.current_profile.extracted_certifications = [
                    {**cert, 'source': 'LinkedIn'} for cert in linkedin_data['certifications']
                ]
                logger.info(f"Créé {len(linkedin_data['certifications'])} certifications depuis LinkedIn")

            # Projets: créer si vide
            if linkedin_data.get('projects') and not self.current_profile.extracted_projects:
                self.current_profile.extracted_projects = [
                    {**proj, 'source': 'LinkedIn'} for proj in linkedin_data['projects']
                ]
                logger.info(f"Créé {len(linkedin_data['projects'])} projets depuis LinkedIn")

            # Publications: créer si vide
            if linkedin_data.get('publications') and not self.current_profile.extracted_publications:
                self.current_profile.extracted_publications = [
                    {**pub, 'source': 'LinkedIn'} for pub in linkedin_data['publications']
                ]
                logger.info(f"Créé {len(linkedin_data['publications'])} publications depuis LinkedIn")

            # Bénévolat: créer si vide
            if linkedin_data.get('volunteering') and not self.current_profile.extracted_volunteering:
                self.current_profile.extracted_volunteering = [
                    {**vol, 'source': 'LinkedIn'} for vol in linkedin_data['volunteering']
                ]
                logger.info(f"Créé {len(linkedin_data['volunteering'])} expériences bénévoles depuis LinkedIn")

            # Intérêts: créer si vide
            if linkedin_data.get('interests') and not self.current_profile.extracted_interests:
                self.current_profile.extracted_interests = linkedin_data['interests']
                logger.info(f"Créé {len(linkedin_data['interests'])} centres d'intérêt depuis LinkedIn")

            logger.info("Champs extracted_* peuplés depuis LinkedIn avec succès")

        except Exception as e:
            logger.error(f"Erreur peuplement extracted_* depuis LinkedIn : {e}")

    def _finalize_profile_extraction(self):
        """Finalise l'extraction complète du profil."""
        try:
            self.progress_updated.emit(95, "Finalisation du profil complet...")
            
            if not self.current_profile:
                raise ValueError("Aucun profil courant défini")
            
            # Calculer des métriques finales
            self._calculate_profile_metrics()
            
            # Générer un résumé d'extraction
            extraction_summary = self._generate_extraction_summary()
            
            # Sauvegarder le résumé
            if not self.current_profile.extracted_personal_info:
                self.current_profile.extracted_personal_info = {}
            
            self.current_profile.extracted_personal_info['extraction_summary'] = extraction_summary
            
            # Mise à jour finale
            self.current_profile.updated_at = datetime.now()
            
            with get_session() as session:
                session.add(self.current_profile)
                session.commit()
                session.refresh(self.current_profile)
            
            self.progress_updated.emit(100, "Profil complet extrait avec succès !")
            
            # Calculer la durée totale d'extraction
            total_duration = None
            if self.extraction_start_time:
                total_duration = (datetime.now() - self.extraction_start_time).total_seconds()
            
            # Finaliser le log d'extraction spécialisé
            self.extraction_logger.end_extraction_session(success=True, total_duration=total_duration)
            
            # Émettre les signaux de fin
            self.profile_updated.emit(self.current_profile)
            self.extraction_completed.emit(self.current_profile)
            
            # PATCH-PII: Éviter exposition nom
            logger.info("Extraction complète terminée pour profile_id=%s", self.current_profile.id)
            
        except Exception as e:
            error_msg = f"Erreur finalisation profil : {e}"
            logger.error(error_msg)
            self.extraction_logger.log_error(f"❌ ERREUR FINALISATION: {error_msg}")
            
            # Calculer la durée même en cas d'échec
            total_duration = None
            if self.extraction_start_time:
                total_duration = (datetime.now() - self.extraction_start_time).total_seconds()
            
            # Terminer le log d'extraction en échec
            self.extraction_logger.end_extraction_session(success=False, total_duration=total_duration)
            
            self.extraction_failed.emit(f"Erreur finalisation : {e}")
    
    def _calculate_profile_metrics(self):
        """Calcule des métriques sur le profil extrait avec comptage unifié."""
        try:
            if not self.current_profile:
                return
            
            # Utiliser le comptage unifié des sections (même logique que le pipeline)
            def _is_filled(section_name: str) -> bool:
                """Vérifie si une section est remplie selon les mêmes critères que le pipeline."""
                attr_name = f"extracted_{section_name}"
                if hasattr(self.current_profile, attr_name):
                    value = getattr(self.current_profile, attr_name)
                    if isinstance(value, dict):
                        return len(value) > 0
                    elif isinstance(value, list):
                        return len(value) > 0
                    else:
                        return bool(value)
                return False
            
            # Compter les sections remplies selon ALL_SECTIONS
            filled_sections = sum(1 for section in ALL_SECTIONS if _is_filled(section))
            completion_percentage = int((filled_sections / TOTAL_SECTIONS_COUNT) * 100)
            
            # PATCH-PII: Éviter exposition nom
            logger.info("Profil profile_id=%s complété à %s%%", self.current_profile.id, completion_percentage)
            logger.info(f"Sections extraites : {filled_sections}/{TOTAL_SECTIONS_COUNT}")
            
        except Exception as e:
            logger.error(f"Erreur calcul métriques : {e}")
    
    def _generate_extraction_summary(self) -> Dict[str, Any]:
        """Génère un résumé de l'extraction."""
        try:
            summary = {
                'extraction_date': datetime.now().isoformat(),
                'sources_used': [],
                'sections_extracted': {},
                'data_quality_score': 0.0,
                'recommendations': []
            }
            
            # Sources utilisées
            if self.cv_results:
                summary['sources_used'].append('CV')
            if self.linkedin_results:
                summary['sources_used'].append('LinkedIn')
            
            # Sections extraites
            completeness = self.current_profile.get_extraction_completeness()
            for section, available in completeness.items():
                summary['sections_extracted'][section] = available
            
            # Score de qualité (basé sur la complétude et la présence de multiples sources)
            base_score = self.current_profile.get_completion_percentage() / 100
            
            # Bonus pour données LinkedIn
            if self.current_profile.has_linkedin_data():
                base_score = min(base_score + 0.1, 1.0)
            
            summary['data_quality_score'] = round(base_score, 2)
            
            # Recommandations
            if base_score < 0.8:
                summary['recommendations'].append("Profil incomplet - vérifiez le CV source")
            
            if not self.current_profile.linkedin_data:
                summary['recommendations'].append("Ajoutez votre profil LinkedIn pour plus de détails")
            elif self.current_profile.needs_linkedin_resync():
                summary['recommendations'].append("Mettez à jour votre profil LinkedIn")
            
            return summary
            
        except Exception as e:
            logger.error(f"Erreur génération résumé : {e}")
            return {
                'extraction_date': datetime.now().isoformat(),
                'error': str(e)
            }
    
    def cleanup(self):
        """Nettoie les ressources utilisées."""
        try:
            if self.cv_extractor and self.cv_extractor.isRunning():
                self.cv_extractor.terminate()
                self.cv_extractor.wait(5000)
            
            if self.linkedin_extractor and self.linkedin_extractor.isRunning():
                self.linkedin_extractor.terminate()
                self.linkedin_extractor.wait(5000)
            
            self.cv_extractor = None
            self.linkedin_extractor = None
            self.current_profile = None
            self.cv_results = None
            self.linkedin_results = None
            
        except Exception as e:
            logger.error(f"Erreur nettoyage ressources : {e}")


def extract_profile_complete(
    profile: UserProfile,
    cv_params: Optional[ExtractionParams] = None,
    linkedin_params: Optional[LinkedInExtractionParams] = None
) -> ProfileExtractionController:
    """
    Fonction utilitaire pour lancer une extraction complète de profil.

    Args:
        profile: Le profil utilisateur à enrichir
        cv_params: Paramètres d'extraction CV (optionnel)
        linkedin_params: Paramètres d'extraction LinkedIn (optionnel)

    Returns:
        Le contrôleur d'extraction configuré
    """
    controller = ProfileExtractionController()
    controller.extract_complete_profile(profile, cv_params, linkedin_params)
    return controller


def convert_linkedin_payload_to_extracted(
    linkedin_payload: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Convertit un payload LinkedIn en format extracted_* compatible.

    Retourne un dictionnaire conforme au modele JSON utilise par l'editeur
    de details (personal_info, experiences, education, skills, languages,
    projects, certifications, publications, volunteering, interests, awards,
    references).
    """
    if not linkedin_payload:
        return {}

    try:
        from ..utils.profile_json import (
            has_profile_json_content,
            map_payload_to_profile_json,
            normalize_profile_json,
        )

        profile_json = linkedin_payload.get("profile_json")
        if isinstance(profile_json, dict) and has_profile_json_content(profile_json):
            return normalize_profile_json(profile_json)

        return map_payload_to_profile_json(linkedin_payload, source="linkedin")
    except Exception as e:
        logger.error(f"Erreur conversion payload LinkedIn : {e}")
        return {}
