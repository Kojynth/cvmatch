#!/usr/bin/env python3
"""
Test script for Phase 4: Soft Skills vs Interests Separation
Tests the classification and separation logic for skills and interests
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.utils.section_mapper import (
    classify_skill_or_interest,
    separate_skills_and_interests,
    apply_soft_skills_interests_separation,
    _extract_items_from_section,
    _analyze_context_for_classification
)

def test_skill_interest_classification():
    """Test individual skill/interest classification"""
    print("=== Testing Skill vs Interest Classification ===")
    
    test_cases = [
        # Clear soft skills
        {"text": "communication", "expected": "soft_skill", "desc": "Clear communication skill"},
        {"text": "leadership", "expected": "soft_skill", "desc": "Leadership skill"},  
        {"text": "travail d'équipe", "expected": "soft_skill", "desc": "Teamwork in French"},
        {"text": "problem solving", "expected": "soft_skill", "desc": "Problem solving skill"},
        
        # Clear interests/hobbies
        {"text": "football", "expected": "interest", "desc": "Sports interest"},
        {"text": "cuisine", "expected": "interest", "desc": "Cooking hobby"},
        {"text": "photographie", "expected": "interest", "desc": "Photography hobby"},
        {"text": "voyage", "expected": "interest", "desc": "Travel interest"},
        
        # Ambiguous cases
        {"text": "créativité", "expected": "soft_skill", "desc": "Creativity (work skill)"},
        {"text": "lecture", "expected": "interest", "desc": "Reading (personal hobby)"},
        {"text": "écriture", "expected": "ambiguous", "desc": "Writing (could be either)"},
        
        # Edge cases
        {"text": "bénévolat", "expected": "interest", "desc": "Volunteering (hobby context)"},
        {"text": "innovation", "expected": "soft_skill", "desc": "Innovation (work skill)"}
    ]
    
    success_count = 0
    
    for case in test_cases:
        text = case["text"]
        expected = case["expected"]
        desc = case["desc"]
        
        # Test without context first
        classification = classify_skill_or_interest(text)
        
        result = "PASS" if classification.category == expected else "FAIL"
        if classification.category == expected:
            success_count += 1
        
        print(f"{result} {desc}")
        print(f"      '{text}' -> {classification.category} (conf={classification.confidence:.2f})")
    
    overall_success = success_count >= 10  # At least 10/13 should pass
    print(f"\nOverall classification test: {'PASS' if overall_success else 'FAIL'} ({success_count}/13)")
    
    return overall_success

def test_context_analysis():
    """Test context-aware classification"""
    print("\n=== Testing Context-Aware Classification ===")
    
    test_cases = [
        {
            "text": "créativité",
            "context": ["COMPÉTENCES PROFESSIONNELLES", "Travail en équipe", "Management de projet"],
            "expected": "soft_skill",
            "desc": "Creativity in professional context"
        },
        {
            "text": "photographie", 
            "context": ["LOISIRS ET CENTRES D'INTÉRÊT", "Temps libre", "Passion pour la photo"],
            "expected": "interest",
            "desc": "Photography in hobby context"
        },
        {
            "text": "communication",
            "context": ["CENTRES D'INTÉRÊT", "J'aime communiquer", "Loisirs personnels"],
            "expected": "soft_skill",  # Should still be classified as skill despite interest context
            "desc": "Communication skill in interest context"
        }
    ]
    
    success_count = 0
    
    for case in test_cases:
        text = case["text"]
        context = case["context"]
        expected = case["expected"]
        desc = case["desc"]
        
        classification = classify_skill_or_interest(text, context)
        
        result = "PASS" if classification.category == expected else "FAIL"
        if classification.category == expected:
            success_count += 1
        
        print(f"{result} {desc}")
        print(f"      '{text}' -> {classification.category} (conf={classification.confidence:.2f})")
    
    return success_count >= 2  # At least 2/3 should pass

def test_mixed_separation():
    """Test separation of mixed skills and interests lists"""
    print("\n=== Testing Mixed Skills/Interests Separation ===")
    
    # Mixed list with both skills and interests
    mixed_items = [
        "communication",      # soft skill
        "leadership",         # soft skill
        "football",          # interest
        "cuisine",           # interest
        "travail d'équipe",  # soft skill
        "photographie",      # interest
        "créativité",        # soft skill (ambiguous but should resolve to skill)
        "voyage",            # interest
        "problem solving",   # soft skill
        "jardinage"          # interest
    ]
    
    # Context suggesting a skills section
    context_lines = ["COMPÉTENCES", "Mes principales qualités professionnelles"]
    
    soft_skills, interests, ambiguous = separate_skills_and_interests(mixed_items, context_lines)
    
    print(f"Total items: {len(mixed_items)}")
    print(f"Soft skills: {len(soft_skills)} - {soft_skills}")
    print(f"Interests: {len(interests)} - {interests}")
    print(f"Ambiguous: {len(ambiguous)} - {ambiguous}")
    
    # Should have approximately 5 skills and 5 interests
    success = (len(soft_skills) >= 4 and len(interests) >= 4)
    print(f"Separation test: {'PASS' if success else 'FAIL'}")
    
    return success

def test_section_item_extraction():
    """Test extraction of items from section text"""
    print("\n=== Testing Section Item Extraction ===")
    
    section_text = """COMPÉTENCES
    • Communication
    • Leadership 
    • Travail d'équipe
    - Problem solving
    ; Créativité
    , Innovation"""
    
    items = _extract_items_from_section(section_text)
    
    print(f"Section text: {repr(section_text[:50])}...")
    print(f"Extracted items: {items}")
    
    # Should extract individual skills, filtering out the header
    expected_count = 6  # 6 skills
    success = (len(items) == expected_count and "COMPÉTENCES" not in items)
    
    print(f"Item extraction test: {'PASS' if success else 'FAIL'} (expected {expected_count}, got {len(items)})")
    
    return success

def test_complete_separation_pipeline():
    """Test the complete skills/interests separation pipeline"""
    print("\n=== Testing Complete Separation Pipeline ===")
    
    # Mock CV with mixed skills/interests sections
    lines = [
        "COMPÉTENCES",
        "Communication, leadership, football, cuisine",
        "Travail d'équipe, photographie, problem solving",
        "",
        "LOISIRS",
        "Voyage, créativité, jardinage",
        "Innovation, tennis, lecture"
    ]
    
    # Boundaries representing a skills section and interests section
    boundaries = [
        (0, 3, "skills"),      # Skills section with mixed content
        (4, 7, "interests")    # Interests section with mixed content
    ]
    
    # Apply separation
    result = apply_soft_skills_interests_separation(boundaries, lines)
    
    print(f"Original boundaries: {len(boundaries)}")
    print(f"After separation: {len(result)}")
    
    for start, end, section_type in result:
        print(f"  Section [{start}:{end}] -> {section_type}")
    
    # Should maintain the sections but log the separation
    success = len(result) == len(boundaries)
    print(f"Pipeline test: {'PASS' if success else 'FAIL'}")
    
    return success

def test_context_bonus_analysis():
    """Test context bonus analysis"""
    print("\n=== Testing Context Bonus Analysis ===")
    
    # Professional context
    prof_context = "COMPÉTENCES PROFESSIONNELLES Travail en équipe Management Projet client"
    result_prof = _analyze_context_for_classification(prof_context, "créativité")
    
    # Personal context
    personal_context = "LOISIRS J'aime faire de la photographie Week-end Personnel"
    result_personal = _analyze_context_for_classification(personal_context, "photographie")
    
    print(f"Professional context bonus: {result_prof}")
    print(f"Personal context bonus: {result_personal}")
    
    # Should detect appropriate context types
    success = (result_prof['type'] == 'soft_skill' and result_personal['type'] == 'interest')
    print(f"Context analysis test: {'PASS' if success else 'FAIL'}")
    
    return success

if __name__ == "__main__":
    print("Phase 4 Soft Skills vs Interests Separation Test Suite")
    print("=" * 60)
    
    success1 = test_skill_interest_classification()
    success2 = test_context_analysis()
    success3 = test_mixed_separation()
    success4 = test_section_item_extraction()
    success5 = test_complete_separation_pipeline()
    success6 = test_context_bonus_analysis()
    
    if all([success1, success2, success3, success4, success5, success6]):
        print("\nPhase 4 soft skills vs interests separation tests completed successfully!")
    else:
        print("\nSome Phase 4 tests failed!")