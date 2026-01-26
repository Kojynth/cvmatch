#!/usr/bin/env python3
"""
Test script for Phase 5: Date Parsing Improvements
Tests the enhanced French-first date parsing with multiple format support
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.utils.section_mapper import (
    parse_enhanced_date,
    _parse_range_dates,
    _parse_month_year_dates,
    _parse_numeric_dates,
    _parse_duration_dates,
    apply_enhanced_date_parsing,
    EnhancedDateParse
)

def test_french_month_parsing():
    """Test French month name parsing"""
    print("=== Testing French Month Parsing ===")
    
    test_cases = [
        {"text": "janvier 2023", "expected_year": 2023, "expected_month": 1, "desc": "French month janvier"},
        {"text": "février 2022", "expected_year": 2022, "expected_month": 2, "desc": "French month février"},
        {"text": "décembre 2021", "expected_year": 2021, "expected_month": 12, "desc": "French month décembre"},
        {"text": "sept 2020", "expected_year": 2020, "expected_month": 9, "desc": "Abbreviated sept"},
        {"text": "oct 2019", "expected_year": 2019, "expected_month": 10, "desc": "Abbreviated oct"},
    ]
    
    success_count = 0
    
    for case in test_cases:
        text = case["text"]
        expected_year = case["expected_year"]
        expected_month = case["expected_month"]
        desc = case["desc"]
        
        result = parse_enhanced_date(text)
        
        success = (result.start_year == expected_year and result.start_month == expected_month)
        if success:
            success_count += 1
        
        status = "PASS" if success else "FAIL"
        print(f"{status} {desc}")
        print(f"      '{text}' -> {result.start_year}/{result.start_month} (conf={result.confidence:.2f})")
    
    overall_success = success_count >= 4  # At least 4/5 should pass
    print(f"\nFrench month parsing test: {'PASS' if overall_success else 'FAIL'} ({success_count}/5)")
    
    return overall_success

def test_english_month_parsing():
    """Test English month name parsing"""
    print("\n=== Testing English Month Parsing ===")
    
    test_cases = [
        {"text": "January 2023", "expected_year": 2023, "expected_month": 1, "desc": "English month January"},
        {"text": "March 2022", "expected_year": 2022, "expected_month": 3, "desc": "English month March"},
        {"text": "Sep 2020", "expected_year": 2020, "expected_month": 9, "desc": "Abbreviated Sep"},
        {"text": "Dec 2019", "expected_year": 2019, "expected_month": 12, "desc": "Abbreviated Dec"},
    ]
    
    success_count = 0
    
    for case in test_cases:
        text = case["text"]
        expected_year = case["expected_year"]
        expected_month = case["expected_month"]
        desc = case["desc"]
        
        result = parse_enhanced_date(text)
        
        success = (result.start_year == expected_year and result.start_month == expected_month)
        if success:
            success_count += 1
        
        status = "PASS" if success else "FAIL"
        print(f"{status} {desc}")
        print(f"      '{text}' -> {result.start_year}/{result.start_month} (conf={result.confidence:.2f})")
    
    return success_count >= 3  # At least 3/4 should pass

def test_numeric_date_parsing():
    """Test numeric date format parsing"""
    print("\n=== Testing Numeric Date Parsing ===")
    
    test_cases = [
        {"text": "01/2023", "expected_year": 2023, "expected_month": 1, "desc": "MM/YYYY format"},
        {"text": "12/2022", "expected_year": 2022, "expected_month": 12, "desc": "MM/YYYY format"},
        {"text": "15/03/2021", "expected_year": 2021, "expected_month": 3, "desc": "DD/MM/YYYY format"},
        {"text": "2020", "expected_year": 2020, "expected_month": None, "desc": "Year only"},
    ]
    
    success_count = 0
    
    for case in test_cases:
        text = case["text"]
        expected_year = case["expected_year"]
        expected_month = case["expected_month"]
        desc = case["desc"]
        
        result = parse_enhanced_date(text)
        
        success = (result.start_year == expected_year and result.start_month == expected_month)
        if success:
            success_count += 1
        
        status = "PASS" if success else "FAIL"
        print(f"{status} {desc}")
        print(f"      '{text}' -> {result.start_year}/{result.start_month} (conf={result.confidence:.2f})")
    
    return success_count >= 3  # At least 3/4 should pass

def test_range_date_parsing():
    """Test date range parsing"""
    print("\n=== Testing Date Range Parsing ===")
    
    test_cases = [
        {"text": "2020 - 2023", "expected_start": 2020, "expected_end": 2023, "desc": "Year range with dash"},
        {"text": "janvier 2020 à mars 2021", "expected_start": 2020, "expected_end": 2021, "desc": "French month range"},
        {"text": "01/2020 - 12/2022", "expected_start": 2020, "expected_end": 2022, "desc": "MM/YYYY range"},
        {"text": "2019 à présent", "expected_start": 2019, "is_current": True, "desc": "Present range"},
    ]
    
    success_count = 0
    
    for case in test_cases:
        text = case["text"]
        desc = case["desc"]
        
        result = parse_enhanced_date(text)
        
        success = False
        if "expected_start" in case and "expected_end" in case:
            success = (result.start_year == case["expected_start"] and 
                      result.end_year == case["expected_end"] and
                      result.is_range)
        elif "expected_start" in case and "is_current" in case:
            success = (result.start_year == case["expected_start"] and
                      result.is_current and
                      result.is_range)
        
        if success:
            success_count += 1
        
        status = "PASS" if success else "FAIL"
        print(f"{status} {desc}")
        print(f"      '{text}' -> {result.start_year}-{result.end_year} current={result.is_current} (conf={result.confidence:.2f})")
    
    return success_count >= 3  # At least 3/4 should pass

def test_duration_parsing():
    """Test duration-based date parsing"""
    print("\n=== Testing Duration Parsing ===")
    
    test_cases = [
        {"text": "3 ans", "desc": "Duration in years"},
        {"text": "6 mois", "desc": "Duration in months"},
        {"text": "2 années", "desc": "Duration in années"},
        {"text": "18 mois", "desc": "Duration 18 months"},
    ]
    
    success_count = 0
    
    for case in test_cases:
        text = case["text"]
        desc = case["desc"]
        
        result = parse_enhanced_date(text)
        
        # Duration parsing should be detected (confidence > 0)
        success = result.confidence > 0.0 and result.parsing_method == "duration"
        if success:
            success_count += 1
        
        status = "PASS" if success else "FAIL"
        print(f"{status} {desc}")
        print(f"      '{text}' -> method={result.parsing_method} (conf={result.confidence:.2f})")
    
    return success_count >= 2  # At least 2/4 should pass

def test_current_indicators():
    """Test current/present indicators"""
    print("\n=== Testing Current Indicators ===")
    
    test_cases = [
        {"text": "2020 - présent", "desc": "Present with dash"},
        {"text": "janvier 2021 à ce jour", "desc": "Current day"},
        {"text": "2022 - aujourd'hui", "desc": "Today indicator"},
        {"text": "mars 2020 - actuel", "desc": "Current indicator"},
    ]
    
    success_count = 0
    
    for case in test_cases:
        text = case["text"]
        desc = case["desc"]
        
        result = parse_enhanced_date(text)
        
        success = result.is_current and result.is_range
        if success:
            success_count += 1
        
        status = "PASS" if success else "FAIL"
        print(f"{status} {desc}")
        print(f"      '{text}' -> current={result.is_current} range={result.is_range} (conf={result.confidence:.2f})")
    
    return success_count >= 3  # At least 3/4 should pass

def test_validation_errors():
    """Test date validation and error detection"""
    print("\n=== Testing Validation Errors ===")
    
    test_cases = [
        {"text": "2025 - 2020", "desc": "Invalid range (future to past)"},
        {"text": "13/2023", "desc": "Invalid month (13)"},
        {"text": "32/01/2023", "desc": "Invalid day (32)"},
        {"text": "xyz abc", "desc": "No date content"},
    ]
    
    success_count = 0
    
    for case in test_cases:
        text = case["text"]
        desc = case["desc"]
        
        result = parse_enhanced_date(text)
        
        # Should have validation errors or very low confidence
        success = (result.validation_errors and len(result.validation_errors) > 0) or result.confidence < 0.3
        if success:
            success_count += 1
        
        status = "PASS" if success else "FAIL"
        print(f"{status} {desc}")
        print(f"      '{text}' -> errors={result.validation_errors} (conf={result.confidence:.2f})")
    
    return success_count >= 3  # At least 3/4 should pass

def test_complete_date_parsing_pipeline():
    """Test the complete date parsing pipeline integration"""
    print("\n=== Testing Complete Date Parsing Pipeline ===")
    
    # Mock CV lines with various date formats
    lines = [
        "EXPÉRIENCE PROFESSIONNELLE",
        "Développeur Senior - janvier 2020 à présent",
        "Consultant IT - 09/2018 - 12/2019", 
        "Stagiaire - 3 mois en 2017",
        "",
        "FORMATION",
        "Master Informatique - 2016 - 2018",
        "Licence - sept 2013 à juin 2016"
    ]
    
    # Mock boundaries for experience and education sections  
    boundaries = [
        (0, 4, "experience"),
        (5, 7, "education")
    ]
    
    # Apply enhanced date parsing
    result = apply_enhanced_date_parsing(boundaries, lines)
    
    print(f"Original boundaries: {len(boundaries)}")
    print(f"After date parsing: {len(result)}")
    
    for start, end, section_type in result:
        print(f"  Section [{start}:{end}] -> {section_type}")
    
    # Should maintain the boundaries (doesn't change structure, just logs parsing)
    success = len(result) == len(boundaries)
    print(f"Pipeline integration test: {'PASS' if success else 'FAIL'}")
    
    return success

if __name__ == "__main__":
    print("Phase 5 Enhanced Date Parsing Test Suite")
    print("=" * 60)
    
    success1 = test_french_month_parsing()
    success2 = test_english_month_parsing()
    success3 = test_numeric_date_parsing()
    success4 = test_range_date_parsing()
    success5 = test_duration_parsing()
    success6 = test_current_indicators()
    success7 = test_validation_errors()
    success8 = test_complete_date_parsing_pipeline()
    
    if all([success1, success2, success3, success4, success5, success6, success7, success8]):
        print("\nPhase 5 enhanced date parsing tests completed successfully!")
    else:
        print("\nSome Phase 5 tests failed!")