#!/usr/bin/env python3
"""
Test script for Phase 3: NER and ORG Heuristics De-noising
Tests the noise filtering for NER entities and organization validation
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.utils.section_mapper import (
    filter_ner_noise,
    validate_organization_candidates,
    apply_ner_org_denoising,
    _calculate_org_validation_score,
    _classify_org_type,
    _calculate_org_noise_score
)

def test_ner_noise_filtering():
    """Test NER entity noise filtering"""
    print("=== Testing NER Noise Filtering ===")
    
    # Mock NER entities with mix of valid and noisy ones
    mock_entities = [
        # Valid entities
        {"text": "Microsoft", "label": "ORG", "confidence": 0.95, "start": 10, "end": 19},
        {"text": "Université de Paris", "label": "ORG", "confidence": 0.88, "start": 30, "end": 49},
        
        # Noisy entities (should be filtered)
        {"text": "je", "label": "PERSON", "confidence": 0.60, "start": 50, "end": 52},  # Low confidence + pronoun
        {"text": "javascript", "label": "ORG", "confidence": 0.80, "start": 60, "end": 70},  # Tech stack noise
        {"text": "123", "label": "ORG", "confidence": 0.90, "start": 80, "end": 83},  # Just numbers
        {"text": "équipe", "label": "ORG", "confidence": 0.85, "start": 90, "end": 96},  # Common word
        
        # Border cases
        {"text": "Google France", "label": "ORG", "confidence": 0.76, "start": 100, "end": 113},  # Valid
        {"text": "ab", "label": "ORG", "confidence": 0.90, "start": 120, "end": 122},  # Too short
    ]
    
    mock_lines = ["Sample CV text with entities"]
    
    # Filter entities
    filtered = filter_ner_noise(mock_entities, mock_lines)
    
    print(f"Total entities: {len(mock_entities)}")
    print(f"After filtering: {len(filtered)}")
    print(f"Clean entities: {len([e for e in filtered if not e.is_noise])}")
    
    # Check results
    clean_entities = [e for e in filtered if not e.is_noise]
    expected_clean = ["Microsoft", "Université de Paris", "Google France"]
    
    success = len(clean_entities) >= 3  # Should keep at least 3 clean entities
    print(f"Test result: {'PASS' if success else 'FAIL'}")
    
    for entity in filtered:
        status = "CLEAN" if not entity.is_noise else "NOISE"
        print(f"  {status}: '{entity.text}' (conf={entity.confidence:.2f}, noise_score={1-entity.context_score:.2f})")
    
    return success

def test_organization_validation():
    """Test organization candidate validation"""
    print("\n=== Testing Organization Validation ===")
    
    # Test organization validation scoring
    test_cases = [
        {
            "org_name": "Microsoft Corporation",
            "context": ["Développeur Senior chez Microsoft Corporation", "Équipe produit", "Missions clients"],
            "expected_valid": True,
            "description": "Major company with employment context"
        },
        {
            "org_name": "Université de Lyon",
            "context": ["Master Informatique", "Université de Lyon", "Formation académique"],
            "expected_valid": True,
            "description": "Educational institution"
        },
        {
            "org_name": "équipe",
            "context": ["Travail en équipe", "Projet collaboratif"],
            "expected_valid": False,
            "description": "Common word, not organization"
        },
        {
            "org_name": "ABC",
            "context": ["Quelques tâches ABC"],
            "expected_valid": False,  
            "description": "Short acronym without context"
        },
        {
            "org_name": "TechCorp SARL",
            "context": ["Startup TechCorp SARL", "Société en croissance", "Équipe technique"],
            "expected_valid": True,
            "description": "Company with legal form"
        }
    ]
    
    success_count = 0
    
    for case in test_cases:
        org_name = case["org_name"]
        context_lines = case["context"]
        expected = case["expected_valid"]
        desc = case["description"]
        
        validation_score = _calculate_org_validation_score(org_name, context_lines)
        org_type = _classify_org_type(org_name, context_lines)
        noise_score = _calculate_org_noise_score(org_name)
        
        # Determine if valid (matching the logic in validate_organization_candidates)
        is_valid = validation_score >= 0.6 and noise_score < 0.4
        
        result = "PASS" if is_valid == expected else "FAIL"
        if is_valid == expected:
            success_count += 1
        
        print(f"{result} {desc}")
        print(f"      '{org_name}' -> valid={is_valid} type={org_type}")
        print(f"      validation={validation_score:.2f} noise={noise_score:.2f}")
    
    overall_success = success_count >= 4  # At least 4/5 should pass
    print(f"\nOverall validation test: {'PASS' if overall_success else 'FAIL'} ({success_count}/5)")
    
    return overall_success

def test_complete_organization_validation():
    """Test complete organization validation pipeline"""
    print("\n=== Testing Complete Organization Validation ===")
    
    # Mock CV lines
    lines = [
        "EXPÉRIENCES PROFESSIONNELLES",
        "",
        "Développeur Senior - Microsoft Corporation",
        "2020-2023",
        "Équipe produit, missions clients",
        "",
        "Stage développeur - Université de Lyon",
        "2019",
        "Formation académique, projets étudiants",
        "",
        "Consultant chez startup ABC",
        "2018",
        "Petite équipe, développement web"
    ]
    
    # Organization candidates (mix of valid and invalid)
    org_candidates = [
        "Microsoft Corporation",  # Should be valid business
        "Université de Lyon",     # Should be valid school
        "startup ABC",            # Border case
        "équipe",                 # Should be invalid (common word)
        "web"                     # Should be invalid (tech term)
    ]
    
    # Validate organizations
    validated = validate_organization_candidates(org_candidates, lines)
    
    valid_orgs = [org for org in validated if org.is_valid]
    
    print(f"Organization candidates: {len(org_candidates)}")
    print(f"After validation: {len(validated)}")
    print(f"Valid organizations: {len(valid_orgs)}")
    
    # Print results
    for org in validated:
        status = "VALID" if org.is_valid else "INVALID"
        print(f"  {status}: '{org.name}' type={org.org_type} conf={org.confidence:.2f} noise={org.noise_score:.2f}")
    
    # Should find at least 2 valid orgs (Microsoft and Université)
    success = len(valid_orgs) >= 2
    print(f"Test result: {'PASS' if success else 'FAIL'}")
    
    return success

def test_denoising_integration():
    """Test the complete de-noising integration"""
    print("\n=== Testing Complete De-noising Integration ===")
    
    lines = ["Sample CV", "With organizations", "Microsoft and Google"]
    boundaries = [(0, 3, "experiences")]
    
    # Test with mock entities and organizations
    mock_entities = [
        {"text": "Microsoft", "label": "ORG", "confidence": 0.95, "start": 0, "end": 9}
    ]
    mock_orgs = ["Microsoft", "Google", "noise"]
    
    try:
        result = apply_ner_org_denoising(boundaries, lines, mock_entities, mock_orgs)
        print(f"De-noising completed successfully: {len(result)} boundaries")
        return True
    except Exception as e:
        print(f"De-noising failed: {e}")
        return False

if __name__ == "__main__":
    print("Phase 3 NER and ORG De-noising Test Suite")
    print("=" * 50)
    
    success1 = test_ner_noise_filtering()
    success2 = test_organization_validation()
    success3 = test_complete_organization_validation() 
    success4 = test_denoising_integration()
    
    if all([success1, success2, success3, success4]):
        print("\nPhase 3 NER and ORG de-noising tests completed successfully!")
    else:
        print("\nSome Phase 3 tests failed!")