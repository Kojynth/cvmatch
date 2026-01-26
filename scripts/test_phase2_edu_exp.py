#!/usr/bin/env python3
"""
Test script for Phase 2: EDU/EXP Boundary Rules
Tests the education/experience classification boundary logic
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.utils.section_mapper import (
    analyze_education_employment_signals,
    classify_education_item,
    apply_edu_exp_boundary_rules,
    enhance_section_boundaries
)

def test_education_employment_analysis():
    """Test education vs employment signal analysis"""
    print("=== Testing Education vs Employment Signal Analysis ===")
    
    test_cases = [
        # Pure education
        ("Master en Informatique à l'Université de Paris, 2018-2020", "education"),
        ("Diplôme d'ingénieur INSA Lyon", "education"),
        ("Licence professionnelle développement web", "education"),
        
        # Education with employment signals 
        ("Stage de 6 mois chez Google, missions de développement, équipe de 5 personnes, salaire 1200€", "employment"),
        ("Alternance développeur chez Microsoft, responsabilités en équipe, projets clients", "employment"), 
        ("Formation professionnelle avec stage en entreprise, missions réelles", "employment"),
        
        # Mixed cases
        ("Master MIAGE avec projet étudiant", "education"),
        ("École 42 - formation développeur avec projets", "education")
    ]
    
    for text, expected_stronger in test_cases:
        edu_score, emp_score = analyze_education_employment_signals(text)
        
        if expected_stronger == "education":
            result = "PASS" if edu_score >= emp_score else "FAIL"
        else:  # employment
            result = "PASS" if emp_score > edu_score else "FAIL"
        
        print(f"{result} '{text[:50]}...'")
        print(f"      edu={edu_score:.2f} emp={emp_score:.2f} stronger={expected_stronger}")

def test_education_classification():
    """Test education item classification"""
    print("\n=== Testing Education Item Classification ===")
    
    # Test cases: lines representing different education items
    test_cases = [
        # Should stay in education
        {
            "lines": [
                "Master Informatique",
                "Université de Lyon",
                "2018-2020",
                "Spécialisation intelligence artificielle"
            ],
            "should_move": False,
            "description": "Pure academic degree"
        },
        
        # Should move to experience
        {
            "lines": [
                "Formation développeur web - École 42",
                "Stage 6 mois chez TechCorp", 
                "Missions: développement applications clients",
                "Équipe de 8 développeurs, salaire stage",
                "Responsabilités: encadrement junior"
            ],
            "should_move": True, 
            "description": "Education with strong employment signals"
        },
        
        # Border case - should stay in education
        {
            "lines": [
                "DUT Informatique",
                "IUT Grenoble",
                "Projet étudiant en équipe"
            ],
            "should_move": False,
            "description": "Academic program with project"
        }
    ]
    
    for i, case in enumerate(test_cases):
        lines = case["lines"]
        expected = case["should_move"]
        desc = case["description"]
        
        item = classify_education_item(lines, 0, len(lines))
        
        result = "PASS" if item.should_move_to_experience == expected else "FAIL"
        print(f"{result} Case {i+1}: {desc}")
        print(f"      move={item.should_move_to_experience} edu={item.education_score:.2f} emp={item.employment_score:.2f}")

def test_boundary_rules_integration():
    """Test the complete EDU/EXP boundary rules system"""
    print("\n=== Testing Complete EDU/EXP Boundary Rules ===")
    
    # Mock CV with education section containing mixed items
    lines = [
        "EXPÉRIENCES PROFESSIONNELLES",
        "Développeur Senior - TechCorp",
        "2020-2023",
        "",
        "FORMATION", 
        "Master Informatique",  # Should stay in education
        "Université de Paris, 2018-2020",
        "",
        "Formation développeur - École 42",  # Should move to experience
        "Stage 6 mois chez Google",
        "Missions développement équipe",
        "Salaire 1500€/mois",
        "",
        "DUT Informatique",  # Should stay in education
        "IUT Lyon, 2016-2018"
    ]
    
    # Original boundaries
    boundaries = [
        (0, 4, "experiences"),    # Experience section
        (4, 15, "education")      # Education section with mixed items
    ]
    
    # Apply boundary rules
    result = apply_edu_exp_boundary_rules(boundaries, lines)
    
    print(f"Original sections: {len(boundaries)}")
    print(f"After EDU/EXP rules: {len(result)}")
    
    # Count sections by type
    experience_sections = [b for b in result if b[2] == "experiences"]
    education_sections = [b for b in result if b[2] == "education"]
    
    print(f"Experience sections: {len(experience_sections)}")
    print(f"Education sections: {len(education_sections)}")
    
    for start, end, section_type in result:
        print(f"  [{start}:{end}] {section_type}")
        
    # Should have moved 1 item from education to experience
    return len(experience_sections) > 1  # Original + 1 moved

def test_enhanced_boundaries_with_phase2():
    """Test the complete pipeline including Phase 2"""
    print("\n=== Testing Enhanced Boundaries with Phase 2 ===")
    
    lines = [
        "EXPÉRIENCES PROFESSIONNELLES",
        "Développeur - Microsoft",
        "2020-2023",
        "",
        "FORMATION",
        "Master Informatique",
        "Université Lyon, 2018-2020", 
        "",
        "Alternance développeur - Google",  # Should move to experience
        "Équipe produit, missions client",
        "Salaire apprenti, responsabilités"
    ]
    
    # Original boundaries  
    boundaries = [(0, 4, "experiences"), (4, 11, "education")]
    
    # Apply full enhancement (Phase 1 + 2 + header-aware)
    try:
        enhanced = enhance_section_boundaries(boundaries, lines)
        print(f"Enhanced pipeline completed: {len(enhanced)} sections")
        return True
    except Exception as e:
        print(f"Enhanced pipeline failed: {e}")
        return False

if __name__ == "__main__":
    print("Phase 2 EDU/EXP Boundary Rules Test Suite")
    print("=" * 50)
    
    test_education_employment_analysis()
    test_education_classification()
    
    success1 = test_boundary_rules_integration()
    success2 = test_enhanced_boundaries_with_phase2()
    
    if success1 and success2:
        print("\nPhase 2 EDU/EXP boundary rules tests completed successfully!")
    else:
        print("\nSome Phase 2 tests failed!")