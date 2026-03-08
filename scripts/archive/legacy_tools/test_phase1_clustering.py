#!/usr/bin/env python3
"""
Test script for Phase 1: Multi-block Experience Clustering
Tests the clustering functionality added to section_mapper.py
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.utils.section_mapper import (
    scan_dates_in_line, scan_organization_in_line, scan_role_in_line,
    compute_line_features, group_into_experience_clusters,
    cluster_experience_sections, enhance_section_boundaries
)

def test_date_scanning():
    """Test French-first date scanning"""
    print("=== Testing Date Scanning ===")
    
    test_cases = [
        ("Janvier 2020 - Décembre 2022", True),
        ("15/03/2021 - 30/06/2023", True),
        ("2019-2021", True),
        ("Mars 2020", True),
        ("No dates here", False),
        ("Hello world", False)
    ]
    
    for text, expected in test_cases:
        has_date, match = scan_dates_in_line(text)
        status = "PASS" if has_date == expected else "FAIL"
        print(f"{status} '{text}' -> {has_date} (match: {match})")

def test_organization_scanning():
    """Test organization detection"""
    print("\n=== Testing Organization Scanning ===")
    
    test_cases = [
        ("Développeur chez Microsoft", True),
        ("Consultant at Google Inc", True), 
        ("Ingénieur Société Générale SA", True),
        ("Stage Groupe Renault", True),
        ("Simple text", False)
    ]
    
    for text, expected in test_cases:
        has_org, match = scan_organization_in_line(text)
        status = "PASS" if has_org == expected else "FAIL"
        print(f"{status} '{text}' -> {has_org} (match: {match})")

def test_role_scanning():
    """Test role/title detection"""
    print("\n=== Testing Role Scanning ===")
    
    test_cases = [
        ("Développeur Full Stack", True),
        ("Senior Software Engineer", True),
        ("Chef de projet", True), 
        ("Consultant en sécurité", True),
        ("Random text", False)
    ]
    
    for text, expected in test_cases:
        has_role, match = scan_role_in_line(text)
        status = "PASS" if has_role == expected else "FAIL"
        print(f"{status} '{text}' -> {has_role} (match: {match})")

def test_clustering():
    """Test the complete clustering pipeline"""
    print("\n=== Testing Experience Clustering ===")
    
    # Mock CV lines with mixed content
    lines = [
        "EXPÉRIENCES PROFESSIONNELLES",
        "",
        "Développeur Senior - Google France",  
        "Mars 2020 - Présent",
        "• Développement d'applications web",
        "• Encadrement équipe de 5 développeurs",
        "",
        "Ingénieur Logiciel - Microsoft",
        "Janvier 2018 - Février 2020", 
        "• Conception architecture microservices",
        "• Formation des équipes",
        "",
        "FORMATION",
        "Master Informatique - ENSIMAG",
        "2016-2018"
    ]
    
    # Test boundaries (experiences section from line 2 to 12)
    boundaries = [(2, 12, "experiences")]
    
    # Apply clustering
    clustered = cluster_experience_sections(lines, boundaries)
    
    print(f"Original boundaries: {len(boundaries)}")
    print(f"After clustering: {len(clustered)}")
    
    for start, end, section_type in clustered:
        print(f"  Cluster [{start}:{end}] ({section_type})")
        cluster_lines = lines[start:end]
        for i, line in enumerate(cluster_lines):
            if line.strip():
                print(f"    {start+i}: {line}")

def test_enhanced_boundaries():
    """Test the complete enhanced boundaries pipeline"""
    print("\n=== Testing Enhanced Boundaries ===")
    
    lines = [
        "EXPÉRIENCES PROFESSIONNELLES",
        "",
        "Développeur Senior chez TechCorp",
        "2020-2023",
        "Missions principales:",
        "• Développement applications",
        "",
        "Consultant Microsoft",
        "2018-2020",
        "• Architecture solutions",
        "",
        "FORMATION",
        "Master MIAGE",
        "2016-2018"
    ]
    
    # Original section boundaries
    boundaries = [(0, 11, "experiences"), (11, 14, "education")]
    
    # Apply full enhancement
    enhanced = enhance_section_boundaries(boundaries, lines)
    
    print(f"Original: {len(boundaries)} sections")
    print(f"Enhanced: {len(enhanced)} sections")
    
    for start, end, section_type in enhanced:
        print(f"  Section [{start}:{end}] ({section_type})")

if __name__ == "__main__":
    print("Phase 1 Clustering Test Suite")
    print("=" * 40)
    
    test_date_scanning()
    test_organization_scanning() 
    test_role_scanning()
    test_clustering()
    test_enhanced_boundaries()
    
    print("\nPhase 1 clustering tests completed!")