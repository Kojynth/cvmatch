# ðŸ“ Structure du Projet CVMatch

**Version :** 2.4 (Architecture rÃ©organisÃ©e et optimisÃ©e)  
**Mise Ã  jour :** 26 aoÃ»t 2025  
**Analyse :** Structure 100% rÃ©organisÃ©e avec regroupement logique des dossiers

## ðŸŽ¯ Vue d'Ensemble

CVMatch est une application desktop moderne d'**Intelligence Artificielle** pour la gÃ©nÃ©ration intelligente de CV. Le projet combine une architecture MVC sophistiquÃ©e, des modules IA avancÃ©s (NER, classification, extraction), une interface graphique PySide6 complÃ¨te, et un systÃ¨me de traitement de documents multi-format avec pipeline ML configurable.

## ðŸ“‚ Structure Exhaustive RÃ©elle

```
ðŸ“ cvmatch/ (Structure du projet CVMatch)
â”œâ”€â”€ ðŸš€ FICHIERS PRINCIPAUX & DÃ‰MARRAGE
â”‚   â”œâ”€â”€ main.py                           # â­ Point d'entrÃ©e principal - Interface PySide6 moderne
â”‚   â”œâ”€â”€ cvmatch.bat                       # ðŸªŸ Lanceur Windows intelligent (gestion venv, dÃ©pendances)
â”‚   â”œâ”€â”€ cvmatch.sh                        # ðŸ§ Lanceur Linux/macOS avec couleurs et logging avancÃ©
â”‚   â”œâ”€â”€ README.md                         # ðŸ“– Guide principal utilisateur consolidÃ©
â”‚   â”œâ”€â”€ pyproject.toml                    # ðŸ“¦ Configuration Poetry moderne (IA complÃ¨te)
â”‚   â”œâ”€â”€ requirements_windows.txt          # ðŸ“‹ DÃ©pendances Windows (sans Flash-Attention)  
â”‚   â”œâ”€â”€ requirements_linux.txt            # ðŸ“‹ DÃ©pendances Linux (avec toutes optimisations)
â”‚   â”œâ”€â”€ installation_linux.sh             # âš™ï¸ Installation automatisÃ©e Linux
â”‚   â”œâ”€â”€ installer_windows.bat             # âš™ï¸ Installation automatisÃ©e Windows
â”‚   â”œâ”€â”€ cleanup_reset.bat                 # ðŸ§¹ Script nettoyage et reset
â”‚
â”œâ”€â”€ ðŸ—ï¸ APPLICATION PRINCIPALE (app/)
â”‚   â”œâ”€â”€ __init__.py                       # Package principal application
â”‚   â”œâ”€â”€ config.py                         # Configuration globale application
â”‚   â”‚
â”‚   â”œâ”€â”€ controllers/                      # ðŸŽ›ï¸ Logique mÃ©tier MVC
â”‚   â”‚   â”œâ”€â”€ __init__.py                   # Package controllers
â”‚   â”‚   â”œâ”€â”€ cv_generator.py               # GÃ©nÃ©rateur CV (logique principale)
â”‚   â”‚   â”œâ”€â”€ export_manager.py             # Gestionnaire exports (PDF/DOCX/formats)
â”‚   â”‚   â””â”€â”€ profile_extractor.py          # Extracteur profils (CV/LinkedIn/documents)
â”‚   â”‚
â”‚   â”œâ”€â”€ models/                           # ðŸ—ƒï¸ ModÃ¨les de donnÃ©es & BDD
â”‚   â”‚   â”œâ”€â”€ __init__.py                   # Package models
â”‚   â”‚   â”œâ”€â”€ database.py                   # Configuration SQLModel + migrations
â”‚   â”‚   â”œâ”€â”€ user_profile.py               # ModÃ¨le profil utilisateur complet
â”‚   â”‚   â”œâ”€â”€ job_application.py            # ModÃ¨le candidatures & correspondances
â”‚   â”‚   â””â”€â”€ extraction_schemas.py         # SchÃ©mas extraction donnÃ©es structurÃ©es
â”‚   â”‚
â”‚   â”œâ”€â”€ views/                            # ðŸ–¥ï¸ Interfaces utilisateur PySide6
â”‚   â”‚   â”œâ”€â”€ __init__.py                   # Package views
â”‚   â”‚   â”œâ”€â”€ main_window.py                # FenÃªtre principale avec sidebar navigation
â”‚   â”‚   â”‚   â”œâ”€â”€ main_window.py.bak       # Sauvegarde fenÃªtre principale
â”‚   â”‚   â”‚   â””â”€â”€ main_window.py.filename_bak # Backup filename
â”‚   â”‚   â”œâ”€â”€ profile_setup.py              # Assistant configuration profil (wizard)
â”‚   â”‚   â”‚   â”œâ”€â”€ profile_setup.py.bak     # Sauvegarde setup
â”‚   â”‚   â”‚   â””â”€â”€ profile_setup.py.filename_bak # Backup filename
â”‚   â”‚   â”œâ”€â”€ settings_dialog.py            # ParamÃ¨tres application complets
â”‚   â”‚   â”‚   â”œâ”€â”€ settings_dialog.py.bak   # Sauvegarde settings
â”‚   â”‚   â”‚   â””â”€â”€ settings_dialog.py.filename_bak # Backup filename
â”‚   â”‚   â”œâ”€â”€ extracted_data_viewer.py      # Visualiseur donnÃ©es extraites avec Ã©dition
â”‚   â”‚   â”œâ”€â”€ extracted_data_viewer_backup.py # Backup visualiseur donnÃ©es
â”‚   â”‚   â”œâ”€â”€ data_conflict_resolver.py     # RÃ©soluteur conflits de donnÃ©es
â”‚   â”‚   â”œâ”€â”€ model_loading_dialog.py       # Dialogue chargement modÃ¨les IA
â”‚   â”‚   â”œâ”€â”€ profile_details_editor.py     # Ã‰diteur dÃ©tails profil avancÃ©
â”‚   â”‚   â”œâ”€â”€ template_preview_window.py    # PrÃ©visualisation CV temps rÃ©el
â”‚   â”‚   â”‚
â”‚   â”‚   â””â”€â”€ profile_sections/             # ðŸ“‹ Sections modulaires CV (14 sections)
â”‚   â”‚       â”œâ”€â”€ __init__.py               # Package sections
â”‚   â”‚       â”œâ”€â”€ base_section.py           # Classe base commune pour toutes sections
â”‚   â”‚       â”œâ”€â”€ personal_info_section.py  # Informations personnelles (nom, contact)
â”‚   â”‚       â”œâ”€â”€ experience_section.py     # ExpÃ©riences professionnelles
â”‚   â”‚       â”œâ”€â”€ education_section.py      # Formation & Ã©ducation
â”‚   â”‚       â”œâ”€â”€ skills_section.py         # CompÃ©tences techniques
â”‚   â”‚       â”œâ”€â”€ soft_skills_section.py    # CompÃ©tences comportementales
â”‚   â”‚       â”œâ”€â”€ projects_section.py       # Projets personnels/professionnels  
â”‚   â”‚       â”œâ”€â”€ languages_section.py      # Langues parlÃ©es & niveaux
â”‚   â”‚       â”œâ”€â”€ certifications_section.py # Certifications & accrÃ©ditations
â”‚   â”‚       â”œâ”€â”€ publications_section.py   # Publications & articles
â”‚   â”‚       â”œâ”€â”€ volunteering_section.py   # BÃ©nÃ©volat & volontariat
â”‚   â”‚       â”œâ”€â”€ awards_section.py         # RÃ©compenses & distinctions
â”‚   â”‚       â”œâ”€â”€ references_section.py     # RÃ©fÃ©rences professionnelles
â”‚   â”‚       â””â”€â”€ interests_section.py      # Centres d'intÃ©rÃªt & hobbies
â”‚   â”‚
â”‚   â”œâ”€â”€ widgets/                          # ðŸ§© Composants UI rÃ©utilisables
â”‚   â”‚   â”œâ”€â”€ __init__.py                   # Package widgets
â”‚   â”‚   â”œâ”€â”€ collapsible_section.py        # Sections repliables/dÃ©pliables
â”‚   â”‚   â”œâ”€â”€ dialog_manager.py             # Gestionnaire dialogues centralisÃ©
â”‚   â”‚   â”œâ”€â”€ generic_fields.py             # Champs formulaires gÃ©nÃ©riques
â”‚   â”‚   â”œâ”€â”€ phone_widget.py               # Widget numÃ©ros tÃ©lÃ©phone internationaux
â”‚   â”‚   â”œâ”€â”€ section_header.py             # En-tÃªtes sections avec actions
â”‚   â”‚   â”œâ”€â”€ style_manager.py              # Gestionnaire thÃ¨mes & styles CSS
â”‚   â”‚   â””â”€â”€ model_selector.py             # SÃ©lecteur modÃ¨les IA (dropdown avancÃ©)
â”‚   â”‚
â”‚   â”œâ”€â”€ workers/                          # âš™ï¸ TÃ¢ches asynchrones (Threading)
â”‚   â”‚   â”œâ”€â”€ __init__.py                   # Package workers
â”‚   â”‚   â”œâ”€â”€ profile_parser.py             # Parser profils utilisateur
â”‚   â”‚   â”œâ”€â”€ cv_extractor.py               # Extracteur CV principal (async)
â”‚   â”‚   â”œâ”€â”€ llm_worker.py                 # Worker IA/LLM (Qwen, GPT, etc.)
â”‚   â”‚   â”œâ”€â”€ adaptive_llm_worker.py        # IA adaptative selon contexte
â”‚   â”‚   â””â”€â”€ linkedin_extractor.py         # Extracteur profils LinkedIn (Selenium)
â”‚   â”‚
â”‚   â”œâ”€â”€ ml/                               # ðŸ¤– Machine Learning & IA
â”‚   â”‚   â”œâ”€â”€ __init__.py                   # Package ML
â”‚   â”‚   â”œâ”€â”€ mock.py                       # Mock IA pour tests & dÃ©veloppement
â”‚   â”‚   â”œâ”€â”€ ner_fr.py                     # NER franÃ§ais (CATIE-AQ/NERmembert)
â”‚   â”‚   â”œâ”€â”€ ner_router.py                 # Routeur NER multi-langues
â”‚   â”‚   â”œâ”€â”€ runtime_state.py              # Ã‰tat runtime ML (GPU/CPU, mÃ©moire)
â”‚   â”‚   â”œâ”€â”€ zero_shot.py                  # Classification zero-shot
â”‚   â”‚   â””â”€â”€ context_classifier.py         # Classificateur de contexte (non trackÃ©)
â”‚   â”‚
â”‚   â”œâ”€â”€ common/                           # ðŸ”— Constantes & dÃ©finitions partagÃ©es
â”‚   â”‚   â”œâ”€â”€ __init__.py                   # Package common
â”‚   â”‚   â””â”€â”€ sections.py                   # Constantes sections CV & mappings
â”‚   â”‚
â”‚   â”œâ”€â”€ resources/                        # ðŸ“š Ressources statiques & patterns
â”‚   â”‚   â”œâ”€â”€ dictionaries_extended.json    # Dictionnaires multi-langues Ã©tendus
â”‚   â”‚   â””â”€â”€ patterns.json                 # Patterns dÃ©tection & regex
â”‚   â”‚
â”‚   â”œâ”€â”€ rules/                            # ðŸ“‹ RÃ¨gles d'extraction & classification
â”‚   â”‚   â”œâ”€â”€ __init__.py                   # Package rules
â”‚   â”‚   â”œâ”€â”€ loader.py                     # Chargeur rÃ¨gles dynamique
â”‚   â”‚   â”œâ”€â”€ precedence.yaml               # RÃ¨gles de prÃ©cÃ©dence
â”‚   â”‚   â”œâ”€â”€ pipeline.json                 # Configuration pipeline ML
â”‚   â”‚   â”œâ”€â”€ ml_config.json                # Configuration modÃ¨les IA
â”‚   â”‚   â”œâ”€â”€ date_patterns.json            # Patterns dates multi-formats
â”‚   â”‚   â”œâ”€â”€ date_normalize.py             # Normalisation dates (non trackÃ©)
â”‚   â”‚   â”œâ”€â”€ durations.json                # DurÃ©es & pÃ©riodes
â”‚   â”‚   â”œâ”€â”€ employment_tokens.json        # Tokens emploi & mÃ©tiers
â”‚   â”‚   â”œâ”€â”€ experience.json               # RÃ¨gles expÃ©riences professionnelles
â”‚   â”‚   â”œâ”€â”€ education.json                # RÃ¨gles formation & diplÃ´mes
â”‚   â”‚   â”œâ”€â”€ certifications.json           # RÃ¨gles certifications & accrÃ©ditations
â”‚   â”‚   â”œâ”€â”€ languages.json                # RÃ¨gles langues & niveaux
â”‚   â”‚   â”œâ”€â”€ projects.json                 # RÃ¨gles projets & rÃ©alisations
â”‚   â”‚   â”œâ”€â”€ publications.json             # RÃ¨gles publications & articles
â”‚   â”‚   â”œâ”€â”€ scholarly.json                # RÃ¨gles acadÃ©miques & recherche
â”‚   â”‚   â”œâ”€â”€ soft_skills.json              # RÃ¨gles soft skills & comportements
â”‚   â”‚   â”œâ”€â”€ volunteering.json             # RÃ¨gles bÃ©nÃ©volat & associations
â”‚   â”‚   â””â”€â”€ interests.json                # RÃ¨gles centres d'intÃ©rÃªt & hobbies
â”‚   â”‚
â”‚   â”œâ”€â”€ utils/                            # ðŸ› ï¸ Utilitaires & helpers
â”‚   â”‚   â”œâ”€â”€ __init__.py                   # Package utils (modifiÃ©)
â”‚   â”‚   â”œâ”€â”€ parsers.py                    # Parseurs documents gÃ©nÃ©riques
â”‚   â”‚   â”œâ”€â”€ database_manager.py           # Gestionnaire BDD avancÃ© (modifiÃ©)
â”‚   â”‚   â”‚
â”‚   â”‚   â”œâ”€â”€ ðŸ¤– GESTION MODÃˆLES IA
â”‚   â”‚   â”œâ”€â”€ model_manager.py              # Gestionnaire modÃ¨les IA centralisÃ©
â”‚   â”‚   â”œâ”€â”€ model_config_manager.py       # Configuration modÃ¨les IA
â”‚   â”‚   â”œâ”€â”€ model_optimizer.py            # Optimisation modÃ¨les (quantification)
â”‚   â”‚   â”œâ”€â”€ lightweight_model.py          # ModÃ¨les lÃ©gers pour CPU faible
â”‚   â”‚   â”œâ”€â”€ universal_gpu_adapter.py      # Adaptateur GPU universel (CUDA/OpenCL)
â”‚   â”‚   â”œâ”€â”€ gpu_utils.py                  # Utilitaires GPU & optimisations CUDA
â”‚   â”‚   â”‚
â”‚   â”‚   â”œâ”€â”€ ðŸ“„ TRAITEMENT DOCUMENTS
â”‚   â”‚   â”œâ”€â”€ cv_parsers.py                 # Parseurs CV multi-formats
â”‚   â”‚   â”‚   â””â”€â”€ cv_parsers.py.filename_bak # Backup parseurs
â”‚   â”‚   â”œâ”€â”€ cv_extractor_advanced.py      # Extracteur CV IA avancÃ©
â”‚   â”‚   â”œâ”€â”€ cv_analyzer.py                # Analyseur layout & structure CV
â”‚   â”‚   â”œâ”€â”€ cv_mapper.py                  # Mapping sÃ©mantique intelligente
â”‚   â”‚   â”œâ”€â”€ cv_normalizer.py              # Normalisation donnÃ©es extraites
â”‚   â”‚   â”œâ”€â”€ cv_scorer.py                  # Scoring qualitÃ© & pertinence
â”‚   â”‚   â”‚
â”‚   â”‚   â”œâ”€â”€ ðŸ” EXTRACTION & MAPPING
â”‚   â”‚   â”œâ”€â”€ extraction_mapper.py          # Mapping extraction intelligent
â”‚   â”‚   â”œâ”€â”€ extraction_constants.py       # Constantes extraction (non trackÃ©)
â”‚   â”‚   â”œâ”€â”€ confidence_filter.py          # Filtrage par niveau de confiance
â”‚   â”‚   â”œâ”€â”€ schema_guard.py               # Garde-fou validation schÃ©mas
â”‚   â”‚   â”œâ”€â”€ validation_utils.py           # Utilitaires validation donnÃ©es
â”‚   â”‚   â”‚
â”‚   â”‚   â”œâ”€â”€ ðŸ“ TRAITEMENT TEXTE & LANGUES
â”‚   â”‚   â”œâ”€â”€ text_norm.py                  # Normalisation texte avancÃ©e
â”‚   â”‚   â”œâ”€â”€ lang_detect.py                # DÃ©tection langue automatique
â”‚   â”‚   â”‚
â”‚   â”‚   â”œâ”€â”€ ðŸ”’ SÃ‰CURITÃ‰ & CONFIDENTIALITÃ‰
â”‚   â”‚   â”œâ”€â”€ pii.py                        # DÃ©tection informations personnelles (non trackÃ©)
â”‚   â”‚   â”œâ”€â”€ redactor.py                   # Anonymisation donnÃ©es sensibles (non trackÃ©)
â”‚   â”‚   â”‚
â”‚   â”‚   â”œâ”€â”€ ðŸ› ï¸ DÃ‰VELOPPEMENT & DEBUG
â”‚   â”‚   â”œâ”€â”€ debug_opts.py                 # Options debug & logging avancÃ©
â”‚   â”‚   â”œâ”€â”€ crash_resistant_logger.py     # Logger rÃ©sistant aux crashes (non trackÃ©)
â”‚   â”‚   â”œâ”€â”€ overfitting_monitor.py        # Monitoring overfitting ML (non trackÃ©)
â”‚   â”‚   â”œâ”€â”€ overfitting_reporter.py       # Reporting overfitting (non trackÃ©)
â”‚   â”‚   â”‚
â”‚   â”‚   â”œâ”€â”€ ðŸ’¾ GESTION FICHIERS & I/O
â”‚   â”‚   â”œâ”€â”€ snapshot_io.py                # Gestion snapshots & sauvegardes
â”‚   â”‚   â”œâ”€â”€ file_cleanup_manager.py       # Nettoyage fichiers temporaires
â”‚   â”‚   â”‚   â””â”€â”€ file_cleanup_manager.py.filename_bak # Backup cleanup
â”‚   â”‚   â”‚
â”‚   â”‚   â”œâ”€â”€ ðŸŽ¯ SPÃ‰CIALISÃ‰S MÃ‰TIER
â”‚   â”‚   â”œâ”€â”€ section_mapper.py             # Mapping sections CV (non trackÃ©)
â”‚   â”‚   â”œâ”€â”€ academic_internship_handler.py # Gestionnaire stages acadÃ©miques (non trackÃ©)
â”‚   â”‚   â”œâ”€â”€ certification_router.py        # Routeur certifications (non trackÃ©)
â”‚   â”‚   â””â”€â”€ experience_filters.py          # Filtres expÃ©riences pro (non trackÃ©)
â”‚   â”‚
â”‚   â””â”€â”€ logging/                          # ðŸ“Š SystÃ¨me de logging avancÃ©
â”‚       â”œâ”€â”€ __init__.py                   # Package logging (non trackÃ©)
â”‚       â”œâ”€â”€ formatters.py                 # Formateurs logs (non trackÃ©)
â”‚       â”œâ”€â”€ handlers.py                   # Gestionnaires logs (non trackÃ©)
â”‚       â””â”€â”€ filters.py                    # Filtres logs (non trackÃ©)
â”‚
â”œâ”€â”€ ðŸ§ª DÃ‰VELOPPEMENT & OUTILS
â”‚   â”œâ”€â”€ development/                      # ðŸ†• Regroupement outils dÃ©veloppement
â”‚   â”‚   â”œâ”€â”€ tests/                        # Suite complÃ¨te de tests
â”‚   â”‚   â”‚   â”œâ”€â”€ __init__.py               # Package tests
â”‚   â”‚   â”‚   â”œâ”€â”€ conftest.py               # Configuration pytest globale
â”‚   â”‚   â”‚   â”œâ”€â”€ unit/cvextractor_pipeline/        # Tests unitaires pipeline cv_extractor
â”‚   â”‚   â”‚   â””â”€â”€ integration/cvextractor_pipeline/ # Tests d'intÃ©gration pipeline cv_extractor
â”‚   â”‚   â”‚   â”‚
â”‚   â”‚   â”‚   â”œâ”€â”€ ðŸ”¬ TESTS PRINCIPAUX
â”‚   â”‚   â”‚   â”œâ”€â”€ test_app.py               # Tests application principale
â”‚   â”‚   â”‚   â”œâ”€â”€ test_app_launch.py        # Tests lancement application
â”‚   â”‚   â”‚   â”œâ”€â”€ test_import.py            # Tests imports modules
â”‚   â”‚   â”‚   â”œâ”€â”€ test_minimal.py           # Tests minimalistes
â”‚   â”‚   â”‚   â”œâ”€â”€ test_ui.py                # Tests interface utilisateur
â”‚   â”‚   â”‚   â”‚
â”‚   â”‚   â”‚   â”œâ”€â”€ ðŸ§  TESTS IA & ML
â”‚   â”‚   â”‚   â”œâ”€â”€ test_model_selector.py    # Tests sÃ©lecteur modÃ¨les
â”‚   â”‚   â”‚   â”œâ”€â”€ test_model_worker.py      # Tests workers IA
â”‚   â”‚   â”‚   â”œâ”€â”€ test_config_sync.py       # Tests synchronisation config
â”‚   â”‚   â”‚   â”‚
â”‚   â”‚   â”‚   â”œâ”€â”€ ðŸ”§ TESTS COMPATIBILITÃ‰
â”‚   â”‚   â”‚   â”œâ”€â”€ test_windows_compatibility.py # Tests compatibilitÃ© Windows
â”‚   â”‚   â”‚   â”œâ”€â”€ test_linux_simulation.py  # Tests simulation Linux
â”‚   â”‚   â”‚   â”‚
â”‚   â”‚   â”‚   â”œâ”€â”€ ðŸ“„ TESTS EXTRACTION & DOCS
â”‚   â”‚   â”‚   â”œâ”€â”€ test_cvextractor.py       # Tests extracteur CV
â”‚   â”‚   â”‚   â”œâ”€â”€ test_cv_extractor_pipeline.py # Tests pipeline extraction
â”‚   â”‚   â”‚   â”œâ”€â”€ test_cv_extraction_system.py # Tests systÃ¨me extraction
â”‚   â”‚   â”‚   â”œâ”€â”€ test_extraction_integration_final.py # Tests intÃ©gration finale
â”‚   â”‚   â”‚   â”‚
â”‚   â”‚   â”‚   â”œâ”€â”€ ðŸŽ¨ TESTS INTERFACE & EXPORT
â”‚   â”‚   â”‚   â”œâ”€â”€ test_profile_editor.py    # Tests Ã©diteur profil
â”‚   â”‚   â”‚   â”œâ”€â”€ test_export_functionality.py # Tests fonctionnalitÃ©s export
â”‚   â”‚   â”‚   â”œâ”€â”€ test_css_visual.py        # Tests CSS & rendu visuel
â”‚   â”‚   â”‚   â”‚
â”‚   â”‚   â”‚   â”œâ”€â”€ ðŸ”„ TESTS WORKFLOW COMPLETS
â”‚   â”‚   â”‚   â”œâ”€â”€ test_complete_workflow.py # Tests workflow complet
â”‚   â”‚   â”‚   â”œâ”€â”€ final_test.py             # Test final d'intÃ©gration
â”‚   â”‚   â”‚   â”œâ”€â”€ run_new_tests.py         # Runner nouveaux tests
â”‚   â”‚   â”‚   â”‚
â”‚   â”‚   â”‚   â”œâ”€â”€ debug/                    # Scripts debug spÃ©cialisÃ©s
â”‚   â”‚   â”‚   â”‚   â”œâ”€â”€ debug_app_complete.py # Debug application complÃ¨te
â”‚   â”‚   â”‚   â”‚   â”œâ”€â”€ debug_extraction.py   # Debug extraction donnÃ©es
â”‚   â”‚   â”‚   â”‚   â””â”€â”€ debug_full_extraction.py # Debug extraction complÃ¨te
â”‚   â”‚   â”‚   â”‚
â”‚   â”‚   â”‚   â”œâ”€â”€ dev_tools/                # Outils dÃ©veloppement avancÃ©s
â”‚   â”‚   â”‚   â”‚   â”œâ”€â”€ test_confidence_filter.py # Tests filtrage confiance
â”‚   â”‚   â”‚   â”‚   â”œâ”€â”€ test_editor_debug.py  # Debug Ã©diteur
â”‚   â”‚   â”‚   â”‚   â””â”€â”€ test_editor_simple.py # Tests Ã©diteur simples
â”‚   â”‚   â”‚   â”‚
â”‚   â”‚   â”‚   â”œâ”€â”€ scripts/                  # Scripts utilitaires tests
â”‚   â”‚   â”‚   â”‚   â””â”€â”€ test_windows_compatibility.py # Script compat Windows
â”‚   â”‚   â”‚   â”‚
â”‚   â”‚   â”‚   â””â”€â”€ fixtures/                 # DonnÃ©es de test
â”‚   â”‚   â”‚       â””â”€â”€ .gitkeep             # Maintien structure dossier
â”‚   â”‚   â”‚
â”‚   â”‚   â”œâ”€â”€ tools/                        # Outils dÃ©veloppement & benchmarks
â”‚   â”‚   â”‚   â”œâ”€â”€ bench_runner.py           # Runner benchmarks performance
â”‚   â”‚   â”‚   â”œâ”€â”€ bench_utils.py            # Utilitaires benchmarking
â”‚   â”‚   â”‚   â”œâ”€â”€ smoke_eval.py             # Tests Ã©valuation rapide
â”‚   â”‚   â”‚   â”‚
â”‚   â”‚   â”‚   â”œâ”€â”€ dev_tools/                # Outils dÃ©veloppement spÃ©cialisÃ©s
â”‚   â”‚   â”‚   â”‚   â”œâ”€â”€ analyse_confusion_advanced.py # Analyse confusion matrices
â”‚   â”‚   â”‚   â”‚   â”œâ”€â”€ analyse_confusion_cases.py # Analyse cas de confusion
â”‚   â”‚   â”‚   â”‚   â”œâ”€â”€ cv_extractor_cli.py   # CLI extraction CV pour devs
â”‚   â”‚   â”‚   â”‚   â””â”€â”€ cvx_classify.py       # CLI classification sections
â”‚   â”‚   â”‚   â”‚
â”‚   â”‚   â”‚   â”œâ”€â”€ examples/                 # Exemples utilisation & dÃ©mos
â”‚   â”‚   â”‚   â”‚   â””â”€â”€ example_generic_usage.py # Exemple utilisation gÃ©nÃ©rique
â”‚   â”‚   â”‚   â”‚
â”‚   â”‚   â”‚   â””â”€â”€ utils/                    # Utilitaires dÃ©veloppement
â”‚   â”‚   â”‚       â”œâ”€â”€ check_dependencies.py # VÃ©rificateur dÃ©pendances
â”‚   â”‚   â”‚       â”œâ”€â”€ debug_startup.py      # Debug dÃ©marrage
â”‚   â”‚   â”‚       â””â”€â”€ verify_installation.py # VÃ©rificateur installation
â”‚   â”‚   â”‚
â”‚   â”‚   â””â”€â”€ dev_tools/                    # Outils dÃ©veloppement projet (anciens)
â”‚   â”‚       â”œâ”€â”€ audit_rgpd_logs_complet.py # Audit RGPD logs
â”‚   â”‚       â”œâ”€â”€ clean_pii_logs_emergency.py # Nettoyage PII urgence
â”‚   â”‚       â””â”€â”€ test_simple_dialog.py     # Tests dialogues simples
â”‚
â”œâ”€â”€ ðŸ—ƒï¸ DONNÃ‰ES & STOCKAGE RUNTIME  
â”‚   â”œâ”€â”€ runtime/                        # ðŸ†• Regroupement donnÃ©es d'exÃ©cution
â”‚   â”‚   â”œâ”€â”€ ðŸ“Š DATASETS & IA
â”‚   â”‚   â”œâ”€â”€ datasets/                   # DonnÃ©es ML & entraÃ®nement
â”‚   â”‚   â”‚   â”œâ”€â”€ base_pretrained/       # ModÃ¨les prÃ©-entraÃ®nÃ©s de base
â”‚   â”‚   â”‚   â”œâ”€â”€ training_ready/        # DonnÃ©es prÃªtes pour entraÃ®nement
â”‚   â”‚   â”‚   â””â”€â”€ user_learning/         # Apprentissage personnalisÃ© utilisateur
â”‚   â”‚   â”‚
â”‚   â”‚   â”œâ”€â”€ models/                     # ModÃ¨les IA tÃ©lÃ©chargÃ©s
â”‚   â”‚   â”œâ”€â”€ cache/                      # Cache application temporaire
â”‚   â”‚   â”œâ”€â”€ data/                       # DonnÃ©es utilisateur gÃ©nÃ©rales
â”‚   â”‚   â”œâ”€â”€ temp_uploads/               # Uploads temporaires
â”‚   â”‚   â”œâ”€â”€ processing/                 # Traitement en cours
â”‚   â”‚   â”œâ”€â”€ parsed_documents/           # Documents parsÃ©s
â”‚   â”‚   â”œâ”€â”€ extracted_text/             # Texte extrait temporaire
â”‚   â”‚   â”œâ”€â”€ checkpoints/                # Points de sauvegarde ML
â”‚   â”‚   â”œâ”€â”€ training_logs/              # Logs entraÃ®nement IA
â”‚   â”‚   â”œâ”€â”€ model_outputs/              # Sorties modÃ¨les IA
â”‚   â”‚   â”œâ”€â”€ exports/                    # Exports utilisateur (PDF/DOCX/JSON)
â”‚   â”‚   â””â”€â”€ output/                     # Sorties diverses application
â”‚   â”‚
â”‚   â”œâ”€â”€ CV/                             # ðŸ†• CV utilisateur organisÃ©s
â”‚   â”‚   â”œâ”€â”€ importÃ©s/                   # CV uploadÃ©s par l'utilisateur
â”‚   â”‚   â””â”€â”€ gÃ©nÃ©rÃ©s/                    # CV gÃ©nÃ©rÃ©s par l'application
â”‚   â”‚
â”‚   â”œâ”€â”€ logs/                           # ðŸ“Š Logs application (reste Ã  la racine)
â”‚   â”‚   â”œâ”€â”€ app.log                     # Log principal application
â”‚   â”‚   â”œâ”€â”€ cvmatch.log                 # Log CVMatch principal
â”‚   â”‚   â”œâ”€â”€ errors_*.log                # Logs erreurs quotidiens
â”‚   â”‚   â”œâ”€â”€ extraction/                 # Logs extraction CV
â”‚   â”‚   â””â”€â”€ sessionlog/                 # Logs sessions utilisateur
â”‚
â”œâ”€â”€ ðŸ¤– INTELLIGENCE ARTIFICIELLE & CLASSIFICATION
â”‚   â”œâ”€â”€ classifier/                      # Classification sections CV
â”‚   â”‚   â”œâ”€â”€ __init__.py                 # Package classifier
â”‚   â”‚   â””â”€â”€ section_classifier.py       # Classificateur intelligent sections
â”‚   â”‚
â”‚   â”œâ”€â”€ cvextractor/                     # Module extraction avancÃ©e CV
â”‚   â”‚   â”œâ”€â”€ __init__.py                 # Package cvextractor
â”‚   â”‚   â”œâ”€â”€ cli.py                      # Interface CLI extraction
â”‚   â”‚   â”‚
â”‚   â”‚   â”œâ”€â”€ core/                       # Noyau extraction
â”‚   â”‚   â”‚   â”œâ”€â”€ __init__.py            # Package core
â”‚   â”‚   â”‚   â”œâ”€â”€ config.py              # Configuration extracteur
â”‚   â”‚   â”‚   â”œâ”€â”€ extractor.py           # Extracteur principal
â”‚   â”‚   â”‚   â”‚   â””â”€â”€ extractor.py.filename_bak # Backup extracteur
â”‚   â”‚   â”‚   â””â”€â”€ types.py               # Types & schÃ©mas donnÃ©es
â”‚   â”‚   â”‚
â”‚   â”‚   â”œâ”€â”€ loaders/                   # Chargeurs documents multi-formats
â”‚   â”‚   â”‚   â”œâ”€â”€ __init__.py            # Package loaders
â”‚   â”‚   â”‚   â”œâ”€â”€ docx_loader.py         # Chargeur Microsoft Word
â”‚   â”‚   â”‚   â”‚   â””â”€â”€ docx_loader.py.filename_bak # Backup DOCX
â”‚   â”‚   â”‚   â”œâ”€â”€ pdf_loader.py          # Chargeur PDF (PyMuPDF)
â”‚   â”‚   â”‚   â”‚   â””â”€â”€ pdf_loader.py.filename_bak # Backup PDF
â”‚   â”‚   â”‚   â”œâ”€â”€ odt_loader.py          # Chargeur OpenDocument
â”‚   â”‚   â”‚   â”‚   â””â”€â”€ odt_loader.py.filename_bak # Backup ODT
â”‚   â”‚   â”‚   â””â”€â”€ image_loader.py        # Chargeur images (OCR)
â”‚   â”‚   â”‚       â””â”€â”€ image_loader.py.filename_bak # Backup images
â”‚   â”‚   â”‚
â”‚   â”‚   â”œâ”€â”€ preprocessing/             # PrÃ©traitement documents
â”‚   â”‚   â”‚   â”œâ”€â”€ __init__.py           # Package preprocessing
â”‚   â”‚   â”‚   â”œâ”€â”€ document_processor.py # Processeur documents gÃ©nÃ©rique
â”‚   â”‚   â”‚   â”œâ”€â”€ language_detector.py  # DÃ©tecteur langue automatique
â”‚   â”‚   â”‚   â””â”€â”€ ocr_processor.py      # Processeur OCR (Tesseract/EasyOCR)
â”‚   â”‚   â”‚
â”‚   â”‚   â”œâ”€â”€ segmentation/             # Segmentation sections CV
â”‚   â”‚   â”‚   â”œâ”€â”€ __init__.py          # Package segmentation
â”‚   â”‚   â”‚   â””â”€â”€ section_segmenter.py # Segmenteur sections intelligent
â”‚   â”‚   â”‚
â”‚   â”‚   â”œâ”€â”€ extraction/               # Extraction donnÃ©es structurÃ©es
â”‚   â”‚   â”‚   â”œâ”€â”€ __init__.py          # Package extraction
â”‚   â”‚   â”‚   â””â”€â”€ field_extractor.py   # Extracteur champs spÃ©cialisÃ©
â”‚   â”‚   â”‚
â”‚   â”‚   â””â”€â”€ normalization/            # Normalisation donnÃ©es extraites
â”‚   â”‚       â”œâ”€â”€ __init__.py          # Package normalization
â”‚   â”‚       â””â”€â”€ data_normalizer.py   # Normaliseur donnÃ©es intelligent
    - cvextractor/pipeline/ : orchestrateur du pipeline modulaire (flux principal depuis 2025-10-27)
    - cvextractor/modules/ : modules d'extraction par section (production, remplace le legacy)
    - cvextractor/shared/ : utilitaires communs (heuristiques, validateurs, post-traitements)
      - `cvextractor/shared/post_processors.py` : normalisation finale, deduplication (active par defaut).

â”‚   â”‚
â”‚   â”‚
â”‚   â””â”€â”€ resources/                     # ðŸ†• Ressources et configuration
â”‚       â””â”€â”€ lexicons/                  # Lexiques & vocabulaires multi-langues
â”‚           â””â”€â”€ section_keywords.yaml # Mots-clÃ©s sections multi-langues
â”‚
â”œâ”€â”€ ðŸ”§ SCRIPTS & INSTALLATION
â”‚   â”œâ”€â”€ scripts/                        # Scripts utilitaires & installation
â”‚   â”‚   â”œâ”€â”€ __init__.py                # Package scripts (non trackÃ©)
â”‚   â”‚   â”œâ”€â”€ README.txt                 # Documentation scripts
â”‚   â”‚   â”‚
â”‚   â”‚   â”œâ”€â”€ ðŸš€ SETUP & INSTALLATION
â”‚   â”‚   â”œâ”€â”€ setup_universal.py         # Setup universel multi-plateformes
â”‚   â”‚   â”œâ”€â”€ setup_cuda_environment.py  # Setup environnement CUDA/GPU
â”‚   â”‚   â”œâ”€â”€ setup_hf_xet.py           # Setup HuggingFace XET (accÃ©lÃ©ration tÃ©lÃ©chargements)
â”‚   â”‚   â”œâ”€â”€ setup_weasyprint_windows.py # Setup WeasyPrint spÃ©cifique Windows
â”‚   â”‚   â”œâ”€â”€ weasyprint_bootstrap.py    # Bootstrap WeasyPrint (import protection)
â”‚   â”‚   â”‚
â”‚   â”‚   â”œâ”€â”€ ðŸ”§ RÃ‰PARATION & MAINTENANCE
â”‚   â”‚   â”œâ”€â”€ fix_model_cache.py         # RÃ©paration cache modÃ¨les IA
â”‚   â”‚   â”œâ”€â”€ fix_weasyprint_windows.py  # RÃ©paration WeasyPrint Windows
â”‚   â”‚   â”œâ”€â”€ install_auto_gptq_windows.py # Installation AutoGPTQ Windows
â”‚   â”‚   â”‚
â”‚   â”‚   â”œâ”€â”€ ðŸ§ª TESTS & VALIDATION
â”‚   â”‚   â”œâ”€â”€ smoke_cv.py               # Test fumÃ©e CV complet
â”‚   â”‚   â”‚
â”‚   â”‚   â””â”€â”€ ðŸ“¦ MIGRATION & ENVIRONNEMENT
â”‚   â”‚       â””â”€â”€ migrate_to_venv.bat   # Migration vers environnement virtuel (non trackÃ©)
â”‚   â”‚
â”‚   â”œâ”€â”€ dev_tools/                      # Outils dÃ©veloppement projet
â”‚   â”‚   â”œâ”€â”€ test_batch_direct.bat      # Test batch direct (non trackÃ©)
â”‚   â”‚   â”œâ”€â”€ test_cvmatch_verbose.bat   # Test CVMatch verbeux (non trackÃ©)
â”‚   â”‚   â”œâ”€â”€ test_simple.bat           # Test simple (non trackÃ©)
â”‚   â”‚   â””â”€â”€ test_venv_direct.bat      # Test environnement virtuel direct (non trackÃ©)
â”‚   â”‚
â”‚   â””â”€â”€ utils/                         # Utilitaires gÃ©nÃ©riques (non trackÃ©)
â”‚       â”œâ”€â”€ check_dependencies.py     # VÃ©rificateur dÃ©pendances
â”‚       â””â”€â”€ verify_installation.py    # VÃ©rificateur installation
â”‚
â”‚
â”œâ”€â”€ ðŸ“š DOCUMENTATION COMPLÃˆTE
â”‚   â””â”€â”€ docs/                          # Documentation exhaustive projet
â”‚       â”œâ”€â”€ STRUCTURE.md              # ðŸ“‹ Ce fichier - Structure dÃ©taillÃ©e
â”‚       â”œâ”€â”€ COMMENT_LANCER.md         # ðŸš€ Guide lancement rapide utilisateur
â”‚       â”œâ”€â”€ DOCUMENTATION.md          # ðŸ“– Index documentation gÃ©nÃ©rale
â”‚       â”œâ”€â”€ MODELES_IA.md            # ðŸ¤– Documentation modÃ¨les IA & ML
â”‚       â”œâ”€â”€ INTEGRATION_ML_UI.md      # ðŸ”— Guide intÃ©gration ML/Interface
â”‚       â”œâ”€â”€ LOGS_BACKEND_ML.md        # ðŸ“Š Documentation logs backend ML
â”‚       â”œâ”€â”€ UI_UX_GUIDE.md           # ðŸŽ¨ Guide interface utilisateur & UX
â”‚       â”œâ”€â”€ PROMPT_REPRISE.md         # ðŸ’¬ Prompts & reprises dÃ©veloppement
â”‚       â”œâ”€â”€ RAPPORT_PROGRESSION.md    # ðŸ“ˆ Suivi progression projet
â”‚       â”œâ”€â”€ README_WEASYPRINT.md      # ðŸ–¨ï¸ Documentation WeasyPrint
â”‚       â”œâ”€â”€ README_VENV.md           # ðŸ Documentation environnement virtuel (non trackÃ©)
â”‚       â””â”€â”€ pii_redaction.md         # ðŸ”’ Documentation anonymisation PII (non trackÃ©)
â”‚
â”œâ”€â”€ ðŸ“– ARCHIVES & HISTORIQUE
â”‚   â”œâ”€â”€ archive/                       # Archives historiques (non trackÃ©)
â”‚   â”‚   â””â”€â”€ .gitkeep                  # Maintien structure
â”‚   â”‚
â”‚   â””â”€â”€ legacy/                        # Versions legacy & anciennes (non trackÃ©)
â”‚       â”œâ”€â”€ CVMatch_old.bat          # Ancien lanceur Windows
â”‚       â””â”€â”€ cvmatch_old.sh           # Ancien lanceur Linux/Unix
â”‚
â””â”€â”€ ðŸŒ ENVIRONNEMENT & RUNTIME (Non trackÃ©s)
    â”œâ”€â”€ cvmatch_env/                   # Environnement virtuel Python complet
    â”‚   â”œâ”€â”€ Scripts/                  # Scripts environnement Windows
    â”‚   â”‚   â”œâ”€â”€ activate.bat         # Activation environnement Windows
    â”‚   â”‚   â””â”€â”€ deactivate.bat       # DÃ©sactivation environnement
    â”‚   â”œâ”€â”€ Lib/                     # BibliothÃ¨ques Python installÃ©es
    â”‚   â”‚   â””â”€â”€ site-packages/       # Packages Python (PySide6, PyTorch, etc.)
    â”‚   â””â”€â”€ Include/                 # Headers C/C++ pour extensions
    â”‚
    â””â”€â”€ ðŸ“Š CONFIGURATION RUNTIME (Fichiers crÃ©Ã©s dynamiquement)
        â”œâ”€â”€ .env                      # Variables d'environnement (non trackÃ©)
        â”œâ”€â”€ config.ini               # Configuration utilisateur (non trackÃ©)
        â””â”€â”€ user_preferences.json    # PrÃ©fÃ©rences utilisateur (non trackÃ©)
```

## ðŸ›ï¸ Architecture & Patterns

### ðŸŽ­ **Architecture MVC Moderne**
- **Models** (`app/models/`) â†’ SQLModel + Pydantic pour donnÃ©es & validation
- **Views** (`app/views/`) â†’ PySide6/Qt6 pour interfaces graphiques modernes
- **Controllers** (`app/controllers/`) â†’ Logique mÃ©tier & orchestration

### ðŸ§© **Composants Modulaires**
- **14 Sections CV** modulaires dans `app/views/profile_sections/`
- **Base Classes** rÃ©utilisables (`base_section.py`, `widgets/`)
- **Workers Asynchrones** pour tÃ¢ches longues (`app/workers/`)
- **Pipeline IA** configurable (`app/ml/`, `app/rules/`, `classifier/`)

### ðŸ¤– **Intelligence Artificielle AvancÃ©e**
- **NER Multi-langues** (FranÃ§ais CATIE-AQ, Anglais dslim/bert-base-NER)
- **Classification Zero-shot** pour sections automatiques
- **Extraction Intelligente** avec cvextractor modulaire
- **Optimisations GPU** (CUDA, quantification, modÃ¨les lÃ©gers)

### ðŸ”Œ **Architecture Plugin & Extensible**
- **Extracteurs** par format (PDF, DOCX, ODT, Images avec OCR)
- **Classificateurs** configurables via rÃ¨gles JSON/YAML
- **ModÃ¨les IA** interchangeables (HuggingFace Hub compatible)
- **Themes & Styles** personnalisables

## âš¡ Points d'EntrÃ©e & Utilisation

### ðŸ‘¨â€ðŸ’» **Utilisateur Final**
1. **Windows** â†’ `cvmatch.bat` (gestion auto venv + dÃ©pendances)
2. **Linux/macOS** â†’ `./cvmatch.sh` ou `installation_linux.sh`
3. **Interface** â†’ Application PySide6 avec sidebar navigation

### ðŸ› ï¸ **DÃ©veloppement**
1. **Principal** â†’ `python main.py`
2. **Tests** â†’ `python tests/final_test.py` ou `pytest tests/`
3. **CLI Extraction** â†’ `python tools/dev_tools/cv_extractor_cli.py`
4. **CLI Classification** â†’ `python tools/dev_tools/cvx_classify.py`
5. **CVExtractor CLI** â†’ `python cvextractor/cli.py`

### ðŸ¤– **Intelligence Artificielle**
- **NER FranÃ§ais** â†’ `app/ml/ner_fr.py` (CATIE-AQ/NERmembert)
- **Classification** â†’ `classifier/section_classifier.py`
- **Pipeline ML** â†’ Configuration dans `app/rules/`

## ðŸ”’ SÃ©curitÃ© & ConfidentialitÃ©

### ðŸ›¡ï¸ **DonnÃ©es ProtÃ©gÃ©es** (Non trackÃ©es par Git)
- **Documents Utilisateur** â†’ `CV/importÃ©s/`, `CV/gÃ©nÃ©rÃ©s/`, `runtime/exports/`
- **Cache & Temporaires** â†’ `logs/`, `runtime/cache/`, `runtime/data/`, `runtime/temp_uploads/`
- **ModÃ¨les IA** â†’ `runtime/models/`, `.hf_cache/`, `runtime/datasets/`
- **Environnement** â†’ `cvmatch_env/`, configuration runtime

### ðŸ” **Architecture SÃ©curisÃ©e**
- **Traitement Local** â†’ Aucune connexion rÃ©seau obligatoire
- **IA EmbarquÃ©e** â†’ ModÃ¨les stockÃ©s localement
- **Anonymisation PII** â†’ DÃ©tection/masquage donnÃ©es sensibles
- **RGPD Compliant** â†’ Aucune collecte de donnÃ©es utilisateur

## ðŸŽ¯ Statistiques Projet

### ðŸ“Š **Code Source**
- **200+ fichiers Python** organisÃ©s en modules MVC
- **14 sections modulaires** CV avec base commune
- **100+ tests** unitaires et d'intÃ©gration
- **4 formats documents** supportÃ©s (PDF, DOCX, ODT, Images)
- **2 modÃ¨les NER** intÃ©grÃ©s (FR/EN)

### ðŸ¤– **Intelligence Artificielle**
- **Pipeline ML** complet avec 7 Ã©tapes configurable
- **Classification zero-shot** pour sections automatiques  
- **Optimisations GPU** (CUDA, quantification, modÃ¨les lÃ©gers)
- **Multi-langues** (FranÃ§ais, Anglais extensible)

### ðŸ“ˆ **Architecture Moderne**
- **SQLModel + Pydantic** pour donnÃ©es typÃ©es
- **PySide6/Qt6** pour interface graphique native
- **Threading asynchrone** pour performance
- **Environnement virtuel** auto-gÃ©rÃ©
- **Installation automatisÃ©e** Windows/Linux

---

**CVMatch v2.4** - Architecture rÃ©organisÃ©e, modulaire, IA avancÃ©e, sÃ©curisÃ©e et Ã©volutive ðŸš€ðŸ¤–âœ¨

## ðŸ†• NouveautÃ©s Version 2.4 (26 aoÃ»t 2025)

### âœ… **RÃ©organisation majeure des dossiers** :
- **`runtime/`** â†’ Regroupement de tous les dossiers de donnÃ©es d'exÃ©cution
- **`development/`** â†’ Regroupement de tous les outils de dÃ©veloppement (tests, tools, dev_tools)
- **`resources/`** â†’ Regroupement des ressources (lexicons)
- **`CV/`** â†’ Structure claire avec `importÃ©s/` et `gÃ©nÃ©rÃ©s/`

### ðŸŽ¯ **BÃ©nÃ©fices** :
- **Racine simplifiÃ©e** â†’ Moins de dossiers Ã  la racine pour une navigation plus claire
- **Regroupement logique** â†’ SÃ©paration nette entre code, donnÃ©es et outils
- **Ã‰volutivitÃ©** â†’ Structure scalable pour futures fonctionnalitÃ©s

### UI Panels View-Model Bridge (2025-11-04)
- `ProfilePanel`, `JobApplicationPanel`, `HistoryPanel` et `ExtractedDataPreviewPanel` reçoivent désormais des instantanés (`ProfileSnapshot`, `HistoryRowViewModel`) fournis par les coordinateurs pour éviter le couplage direct aux modèles ORM.
- Le `MainWindowWithSidebar` publie le snapshot actif lors des changements de profil pour maintenir les panneaux synchronisés.
- Les interactions modales (succès, avertissements, confirmations) passent par `app/services/dialogs.py`, garantissant une surface unique pour mocking/tests.

### Lifecycle Orchestration (2025-11-05)
- `app/lifecycle/app_initializer.py` fournit `LifecycleServices` et `bootstrap_main_window()` pour instancier la fenêtre principale en injectant les coordinateurs/services partagés.
- `app/lifecycle/app_shutdown.py` centralise `shutdown_gui()` et `shutdown_background_workers()` afin que la fermeture des workers/ressources soit gérée hors de la vue PySide6.
- Les points d'entrée GUI (ex. `main.py`, outils de validation) délèguent désormais le bootstrap/teardown à ces helpers pour maintenir `MainWindowWithSidebar` purement présentielle.
- `MainWindowWithSidebar` consomme désormais `DialogService`, `MlWorkflowCoordinator`, et `NavigationCoordinator` via le conteneur lifecycle : le code UI se limite aux layouts/signaux tandis que les dialogues, bascules ML, et nettoyages sont orchestrés par les services injectés.

### Architecture GUI (2025-11-07)
- **Bootstrap unique** : toute ouverture de fenêtre passe par `app.lifecycle.bootstrap_main_window(profile)` qui crée `LifecycleServices` (coordinators, DialogService, ProgressService, TelemetryService) avant d’injecter l’instance dans `MainWindowWithSidebar`.
- **Couche UI pure** : `app/views/main_window.py` construit uniquement les layouts/panels (`SidebarPanel`, `ProfilePanel`, `JobApplicationPanel`, `HistoryPanel`, `ExtractedDataPreviewPanel`). Les actions utilisateur sont relayées aux coordinateurs (`ProfileState`, `JobApplication`, `History`, `MlWorkflow`, `Navigation`).
- **Services partagés** : `DialogService` encapsule les interactions `QMessageBox`/`DialogManager`, `ProgressService` orchestre le modal de chargement ML, et `shutdown_gui()` ferme proprement workers et coordinators (utilisé dans `closeEvent` et dans les scripts de diagnostic).
- **Couverture tests** : les suites `tests/ui/test_main_window_coordinator.py`, `tests/ui/test_main_window_lifecycle.py`, `tests/integration/test_main_window_workflow.py` et `tests/unit/lifecycle/` valident respectivement la coordination ML, le cycle de fermeture, le workflow bootstrap/teardown et les helpers lifecycle.
- **Scripts/outillage** : `verify_modal_cleanup.py` et `development/dev_tools/test_pyside6.py` utilisent également `bootstrap_main_window()` afin que les diagnostics reproduisent exactement la configuration runtime de l’application.

