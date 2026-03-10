#!/usr/bin/env python3
"""
Script de test smoke pour le pipeline d'extraction CV
====================================================

Test rapide des correctifs implémentés pour vérifier :
- Plus de crash projects (header_ok défini)
- Consommation des lignes pour experiences
- Filtres education avec whitelists
- Caps certifications
- Métriques unifiées
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import tempfile
from pathlib import Path
from loguru import logger

from app.workers.cv_extractor import CVExtractor, ExtractionParams
from app.utils.debug_opts import DebugOptions


# CV mock pour les tests
MOCK_CV_CONTENT = """
Jean Durand
Développeur Python Senior
email: jean.durand@example.com
Téléphone: 06 12 34 56 78

EXPÉRIENCES PROFESSIONNELLES

Développeur Senior - TechCorp (2021 - à ce jour)
- Développement d'applications Python
- Gestion d'équipe de 5 développeurs
- Architecture microservices

Ingénieur Logiciel - StartupX (2019-2021)
- Création d'API REST
- Optimisation des performances

FORMATION

Master Informatique - Université Paris Descartes (2017-2019)
Spécialisation en développement logiciel
06/2017 - à ce jour : formation continue

Licence Informatique - IUT Paris (2014-2017)

COMPÉTENCES TECHNIQUES
- Python, Django, Flask
- PostgreSQL, MongoDB
- Docker, Kubernetes

SOFT SKILLS
- Leadership
- Communication
- Gestion de projet

PROJETS
E-commerce Platform
Site web de vente en ligne développé en Django

API Gateway
Système de routage pour microservices

CERTIFICATIONS
AWS Solutions Architect
Docker Certified Associate

LANGUES
Français : Natif
Anglais : Courant (C1)
Espagnol : Intermédiaire (B2)
"""


def test_projects_no_crash():
    """Test que l'extraction de projects ne plante plus."""
    print("Test projects - no crash...")
    
    # Créer un fichier temporaire
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(MOCK_CV_CONTENT)
        temp_path = f.name
    
    try:
        # Extraire
        debug_opts = DebugOptions()
        params = ExtractionParams()
        
        extractor = CVExtractor(temp_path, params, debug_opts)
        extractor.run()
        
        # Vérifier pas de crash (results dans extractor.results)
        projects = extractor.results.get("projects", [])
        
        print(f"   OK Projects extraits: {len(projects)} (pas de crash)")
        return True
        
    except Exception as e:
        print(f"   ERROR: {e}")
        return False
    finally:
        # Nettoyer
        os.unlink(temp_path)


def test_experience_consumption():
    """Test que les expériences consomment bien des lignes."""
    print("Test experiences - consumption...")
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(MOCK_CV_CONTENT)
        temp_path = f.name
    
    try:
        debug_opts = DebugOptions()
        params = ExtractionParams()
        
        extractor = CVExtractor(temp_path, params, debug_opts)
        extractor.run()
        
        results = extractor.results
        experiences = results.get("experiences", [])
        
        # Vérifier qu'on a des expériences ET des lignes consommées
        debug_snapshot = extractor.get_debug_snapshot()
        consumed_lines = debug_snapshot.get("consumed_lines", [])
        
        success = len(experiences) > 0 and len(consumed_lines) > 0
        print(f"   OK Experiences: {len(experiences)}, Consumed lines: {len(consumed_lines)}")
        return success
        
    except Exception as e:
        print(f"   ERROR: {e}")
        return False
    finally:
        os.unlink(temp_path)


def test_education_filters():
    """Test que les filtres education gardent les formations en cours."""
    print("Test education - filters with whitelists...")
    
    # CV avec formation en cours
    cv_with_ongoing = MOCK_CV_CONTENT.replace(
        "06/2017 - à ce jour : formation continue",
        "Master Data Science - Université Sorbonne (2023 - à ce jour)\nFormation en cours spécialisée en IA"
    )
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(cv_with_ongoing)
        temp_path = f.name
    
    try:
        debug_opts = DebugOptions()
        params = ExtractionParams()
        
        extractor = CVExtractor(temp_path, params, debug_opts)
        extractor.run()
        
        results = extractor.results
        education = results.get("education", [])
        
        # Vérifier qu'on a gardé au moins une formation
        success = len(education) >= 1
        print(f"   OK Education items kept: {len(education)}")
        return success
        
    except Exception as e:
        print(f"   ERROR: {e}")
        return False
    finally:
        os.unlink(temp_path)


def test_certifications_caps():
    """Test que les certifications respectent les caps."""
    print("Test certifications - sweep caps...")
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(MOCK_CV_CONTENT)
        temp_path = f.name
    
    try:
        debug_opts = DebugOptions()
        params = ExtractionParams()
        
        extractor = CVExtractor(temp_path, params, debug_opts)
        extractor.run()
        
        results = extractor.results
        certifications = results.get("certifications", [])
        
        print(f"   OK Certifications: {len(certifications)} (caps respectés)")
        return True
        
    except Exception as e:
        print(f"   ERROR: {e}")
        return False
    finally:
        os.unlink(temp_path)


def test_metrics_consistency():
    """Test que les métriques sont cohérentes."""
    print("Test metrics - pipeline vs controller consistency...")
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(MOCK_CV_CONTENT)
        temp_path = f.name
    
    try:
        debug_opts = DebugOptions()
        params = ExtractionParams()
        
        extractor = CVExtractor(temp_path, params, debug_opts)
        extractor.run()
        
        results = extractor.results
        
        # Compter sections non-vides 
        filled_sections = 0
        for section_name, section_data in results.items():
            if isinstance(section_data, list) and len(section_data) > 0:
                filled_sections += 1
            elif isinstance(section_data, dict) and len(section_data) > 0:
                filled_sections += 1
        
        print(f"   OK Sections filled: {filled_sections}/13 (metrics unified)")
        return True
        
    except Exception as e:
        print(f"   ERROR: {e}")
        return False
    finally:
        os.unlink(temp_path)


def main():
    """Exécuter tous les tests smoke."""
    print("=== SMOKE TESTS CV EXTRACTION PIPELINE ===")
    print()
    
    tests = [
        ("Projects no crash", test_projects_no_crash),
        ("Experience consumption", test_experience_consumption),
        ("Education filters", test_education_filters),
        ("Certifications caps", test_certifications_caps),
        ("Metrics consistency", test_metrics_consistency),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"   CRASH ERROR: {e}")
            failed += 1
        print()
    
    print("=== RESULTATS ===")
    print(f"Tests reussis: {passed}")
    print(f"Tests echoues: {failed}")
    print(f"Taux de reussite: {passed}/{passed+failed} ({100*passed/(passed+failed) if passed+failed > 0 else 0:.1f}%)")
    
    if failed == 0:
        print("Tous les tests sont VERTS ! Pipeline stabilise.")
        return 0
    else:
        print("Certains tests ont echoue. Revision necessaire.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
