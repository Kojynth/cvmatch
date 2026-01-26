#!/usr/bin/env python3
"""
Test script for Phase 6: Post-mapping QA and Display Gating
Tests the quality assessment and display gating functionality
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.utils.section_mapper import (
    assess_section_quality,
    apply_post_mapping_qa,
    _calculate_quality_metrics,
    _count_section_items,
    _estimate_section_confidence,
    _calculate_noise_ratio,
    _identify_quality_issues,
    _determine_display_eligibility,
    QualityAssessment
)

def test_quality_metrics_calculation():
    """Test quality metrics calculation for various section types"""
    print("=== Testing Quality Metrics Calculation ===")
    
    test_cases = [
        {
            "lines": ["EXPÉRIENCE PROFESSIONNELLE", "Développeur Senior chez TechCorp", "2020-2023", "Responsable équipe de 5 développeurs"],
            "section_type": "experience",
            "desc": "Good experience section"
        },
        {
            "lines": ["COMPÉTENCES", "Python, Java, JavaScript", "SQL, NoSQL", "Git, Docker"],
            "section_type": "skills",
            "desc": "Good skills section"
        },
        {
            "lines": ["", "", "Texte très court"],
            "section_type": "experience",
            "desc": "Low quality section with empty lines"
        },
        {
            "lines": ["... ... ...", "--- --- ---", "**** ****"],
            "section_type": "interests",
            "desc": "High noise section"
        }
    ]
    
    success_count = 0
    
    for case in test_cases:
        lines = case["lines"]
        section_type = case["section_type"]
        desc = case["desc"]
        section_text = "\n".join(lines)
        
        metrics = _calculate_quality_metrics(lines, section_text, section_type)
        
        # Basic validation of metrics
        success = (
            0 <= metrics["empty_lines_ratio"] <= 1 and
            metrics["content_length"] >= 0 and
            metrics["items_count"] >= 0 and
            0 <= metrics["confidence_score"] <= 1 and
            0 <= metrics["noise_ratio"] <= 1
        )
        
        if success:
            success_count += 1
        
        status = "PASS" if success else "FAIL"
        print(f"{status} {desc}")
        print(f"      length={metrics['content_length']}, items={metrics['items_count']}, "
              f"conf={metrics['confidence_score']:.2f}, noise={metrics['noise_ratio']:.2f}")
    
    overall_success = success_count >= 3  # At least 3/4 should pass
    print(f"\nQuality metrics test: {'PASS' if overall_success else 'FAIL'} ({success_count}/4)")
    
    return overall_success

def test_section_items_counting():
    """Test items counting for different section types"""
    print("\n=== Testing Section Items Counting ===")
    
    test_cases = [
        {
            "lines": ["EXPÉRIENCE", "Développeur chez Google", "Stage à Microsoft", "Consultant freelance"],
            "section_type": "experience",
            "expected_min": 2,
            "desc": "Experience section items"
        },
        {
            "lines": ["COMPÉTENCES", "Python, Java, C++", "Git, Docker, Kubernetes", "Agile, Scrum"],
            "section_type": "skills", 
            "expected_min": 6,
            "desc": "Skills section items"
        },
        {
            "lines": ["FORMATION", "Master à l'Université Paris", "Licence en informatique"],
            "section_type": "education",
            "expected_min": 1,
            "desc": "Education section items"
        }
    ]
    
    success_count = 0
    
    for case in test_cases:
        lines = case["lines"]
        section_type = case["section_type"]
        expected_min = case["expected_min"]
        desc = case["desc"]
        
        items_count = _count_section_items(lines, section_type)
        
        success = items_count >= expected_min
        if success:
            success_count += 1
        
        status = "PASS" if success else "FAIL"
        print(f"{status} {desc}")
        print(f"      found {items_count} items (expected >= {expected_min})")
    
    return success_count >= 2  # At least 2/3 should pass

def test_confidence_estimation():
    """Test confidence estimation for section classification"""
    print("\n=== Testing Confidence Estimation ===")
    
    test_cases = [
        {
            "text": "EXPÉRIENCE PROFESSIONNELLE Développeur Senior dans une grande entreprise",
            "section_type": "experience",
            "expected_min": 0.5,
            "desc": "High confidence experience"
        },
        {
            "text": "FORMATION Master en informatique à l'université",
            "section_type": "education",
            "expected_min": 0.5,
            "desc": "High confidence education"
        },
        {
            "text": "Texte aléatoire sans mots-clés pertinents",
            "section_type": "experience",
            "expected_max": 0.4,
            "desc": "Low confidence text"
        },
        {
            "text": "xyz",
            "section_type": "skills",
            "expected_max": 0.2,
            "desc": "Very short text"
        }
    ]
    
    success_count = 0
    
    for case in test_cases:
        text = case["text"]
        section_type = case["section_type"]
        desc = case["desc"]
        
        confidence = _estimate_section_confidence(text, section_type)
        
        success = True
        if "expected_min" in case:
            success = confidence >= case["expected_min"]
        elif "expected_max" in case:
            success = confidence <= case["expected_max"]
        
        if success:
            success_count += 1
        
        status = "PASS" if success else "FAIL"
        print(f"{status} {desc}")
        print(f"      confidence={confidence:.2f}")
    
    return success_count >= 3  # At least 3/4 should pass

def test_noise_detection():
    """Test noise ratio calculation"""
    print("\n=== Testing Noise Detection ===")
    
    test_cases = [
        {
            "text": "Développeur Python avec 5 ans d'expérience",
            "lines": ["Développeur Python avec 5 ans d'expérience"],
            "expected_max": 0.3,
            "desc": "Clean text"
        },
        {
            "text": "... ... ... --- --- --- *** *** ***",
            "lines": ["... ... ...", "--- --- ---", "*** *** ***"],
            "expected_min": 0.5,
            "desc": "High noise text"
        },
        {
            "text": "Normal text!!!!!!!!!!!!",
            "lines": ["Normal text!!!!!!!!!!!!"],
            "expected_min": 0.2,
            "desc": "Excessive punctuation"
        }
    ]
    
    success_count = 0
    
    for case in test_cases:
        text = case["text"]
        lines = case["lines"]
        desc = case["desc"]
        
        noise_ratio = _calculate_noise_ratio(text, lines)
        
        success = True
        if "expected_min" in case:
            success = noise_ratio >= case["expected_min"]
        elif "expected_max" in case:
            success = noise_ratio <= case["expected_max"]
        
        if success:
            success_count += 1
        
        status = "PASS" if success else "FAIL"
        print(f"{status} {desc}")
        print(f"      noise_ratio={noise_ratio:.2f}")
    
    return success_count >= 2  # At least 2/3 should pass

def test_quality_issues_identification():
    """Test quality issues identification"""
    print("\n=== Testing Quality Issues Identification ===")
    
    # Mock metrics for different scenarios
    test_cases = [
        {
            "metrics": {
                "content_length": 5,
                "empty_lines_ratio": 0.3,
                "confidence_score": 0.8,
                "noise_ratio": 0.1,
                "items_count": 2
            },
            "section_type": "experience",
            "expected_issues": ["too_short"],
            "desc": "Too short section"
        },
        {
            "metrics": {
                "content_length": 100,
                "empty_lines_ratio": 0.8,
                "confidence_score": 0.8,
                "noise_ratio": 0.1,
                "items_count": 2
            },
            "section_type": "skills",
            "expected_issues": ["mostly_empty"],
            "desc": "Mostly empty section"
        },
        {
            "metrics": {
                "content_length": 100,
                "empty_lines_ratio": 0.3,
                "confidence_score": 0.1,
                "noise_ratio": 0.1,
                "items_count": 2
            },
            "section_type": "education",
            "expected_issues": ["low_confidence"],
            "desc": "Low confidence section"
        }
    ]
    
    success_count = 0
    
    for case in test_cases:
        metrics = case["metrics"]
        section_type = case["section_type"]
        expected_issues = case["expected_issues"]
        desc = case["desc"]
        
        issues = _identify_quality_issues(metrics, section_type)
        
        # Check if expected issues are detected
        success = all(issue in issues for issue in expected_issues)
        if success:
            success_count += 1
        
        status = "PASS" if success else "FAIL"
        print(f"{status} {desc}")
        print(f"      expected={expected_issues}, found={issues}")
    
    return success_count >= 2  # At least 2/3 should pass

def test_display_eligibility():
    """Test display eligibility determination"""
    print("\n=== Testing Display Eligibility ===")
    
    test_cases = [
        {
            "quality_score": 0.8,
            "issues": [],
            "section_type": "experience",
            "expected": True,
            "desc": "High quality section"
        },
        {
            "quality_score": 0.2,
            "issues": [],
            "section_type": "skills",
            "expected": False,
            "desc": "Low quality score"
        },
        {
            "quality_score": 0.6,
            "issues": ["no_items"],
            "section_type": "education",
            "expected": False,
            "desc": "Critical issue present"
        },
        {
            "quality_score": 0.3,
            "issues": ["too_short"],
            "section_type": "experience",
            "expected": True,
            "desc": "Essential section with acceptable score"
        }
    ]
    
    success_count = 0
    
    for case in test_cases:
        quality_score = case["quality_score"]
        issues = case["issues"]
        section_type = case["section_type"]
        expected = case["expected"]
        desc = case["desc"]
        
        eligible = _determine_display_eligibility(quality_score, issues, section_type)
        
        success = eligible == expected
        if success:
            success_count += 1
        
        status = "PASS" if success else "FAIL"
        print(f"{status} {desc}")
        print(f"      score={quality_score}, issues={issues} -> eligible={eligible}")
    
    return success_count >= 3  # At least 3/4 should pass

def test_complete_qa_pipeline():
    """Test the complete QA pipeline"""
    print("\n=== Testing Complete QA Pipeline ===")
    
    # Mock CV with various quality sections
    lines = [
        "EXPÉRIENCE PROFESSIONNELLE",
        "Développeur Senior chez TechCorp - 2020 à présent",
        "Responsable équipe de 5 développeurs",
        "Projets: application web, mobile, API",
        "",
        "COMPÉTENCES",
        "Python, Java, JavaScript, SQL",
        "",
        "SECTION VIDE",
        "",
        "",
        "SECTION BRUYANTE",
        "... ... ...",
        "--- --- ---"
    ]
    
    # Mock boundaries
    boundaries = [
        (0, 4, "experience"),     # Good quality
        (5, 7, "skills"),         # Medium quality
        (8, 11, "interests"),     # Poor quality (empty)
        (12, 14, "other")         # Poor quality (noisy)
    ]
    
    # Apply QA pipeline
    filtered_boundaries, assessments = apply_post_mapping_qa(boundaries, lines)
    
    print(f"Original sections: {len(boundaries)}")
    print(f"Filtered sections: {len(filtered_boundaries)}")
    print(f"Quality assessments: {len(assessments)}")
    
    # Should filter out poor quality sections
    success = len(filtered_boundaries) < len(boundaries)
    print(f"QA Pipeline test: {'PASS' if success else 'FAIL'}")
    
    return success

if __name__ == "__main__":
    print("Phase 6 Post-mapping QA and Display Gating Test Suite")
    print("=" * 60)
    
    success1 = test_quality_metrics_calculation()
    success2 = test_section_items_counting()
    success3 = test_confidence_estimation()
    success4 = test_noise_detection()
    success5 = test_quality_issues_identification()
    success6 = test_display_eligibility()
    success7 = test_complete_qa_pipeline()
    
    if all([success1, success2, success3, success4, success5, success6, success7]):
        print("\nPhase 6 post-mapping QA and display gating tests completed successfully!")
    else:
        print("\nSome Phase 6 tests failed!")