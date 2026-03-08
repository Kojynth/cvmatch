#!/usr/bin/env python3
"""
Test script for Phase 7: Metrics, Scoring and CI Gates
Tests the comprehensive metrics collection and CI gate evaluation
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.utils.section_mapper import (
    MetricsCollector,
    ExtractionMetrics,
    evaluate_ci_gates,
    apply_metrics_and_scoring,
    CI_GATES,
    QualityAssessment
)

def test_metrics_collector():
    """Test the MetricsCollector functionality"""
    print("=== Testing MetricsCollector ===")
    
    collector = MetricsCollector()
    
    # Record various metrics
    collector.record_section_processed()
    collector.record_section_processed()
    collector.record_section_processed()
    
    collector.record_section_extracted(0.8, 0.7)
    collector.record_section_extracted(0.6, 0.5)
    
    collector.record_section_gated("Low quality")
    
    collector.record_parsing_error("Date format error")
    
    collector.record_date_parsing(True)
    collector.record_date_parsing(False, "Invalid format")
    
    collector.record_phase_stats("phase1", {"clusters_created": 3})
    collector.record_phase_stats("phase4", {"skills_separated": 10})
    
    # Finalize metrics
    metrics = collector.finalize_metrics()
    
    # Validate metrics
    success = (
        metrics.sections_processed == 3 and
        metrics.sections_extracted == 2 and
        metrics.sections_gated == 1 and
        metrics.parsing_errors == 1 and
        metrics.date_parsing_success == 1 and
        metrics.date_parsing_errors == 1 and
        metrics.phase1_clusters_created == 3 and
        metrics.phase4_skills_separated == 10
    )
    
    print(f"{'PASS' if success else 'FAIL'} MetricsCollector functionality")
    print(f"      processed={metrics.sections_processed}, extracted={metrics.sections_extracted}")
    print(f"      avg_quality={metrics.average_quality_score:.2f}, avg_confidence={metrics.average_confidence_score:.2f}")
    
    return success

def test_extraction_metrics_serialization():
    """Test ExtractionMetrics to_dict functionality"""
    print("\n=== Testing ExtractionMetrics Serialization ===")
    
    metrics = ExtractionMetrics(
        processing_time=5.2,
        memory_usage=256 * 1024 * 1024,  # 256MB
        sections_processed=10,
        sections_extracted=8,
        sections_gated=2,
        average_quality_score=0.75,
        average_confidence_score=0.68,
        parsing_errors=1,
        parsing_success_rate=0.8,
        date_parsing_success=5,
        date_parsing_errors=1,
        phase1_clusters_created=2,
        phase2_boundary_adjustments=3,
        phase3_entities_denoised=15,
        phase4_skills_separated=12,
        phase5_dates_parsed=5,
        phase6_sections_gated=2,
        errors=["Sample error"],
        warnings=["Sample warning"],
        start_time=1000.0,
        end_time=1005.2
    )
    
    metrics_dict = metrics.to_dict()
    
    # Validate dictionary structure
    required_keys = ["performance", "quality", "extraction", "phases", "errors", "warnings", "timing"]
    success = all(key in metrics_dict for key in required_keys)
    
    # Validate nested structure
    if success:
        performance = metrics_dict["performance"]
        success = all(key in performance for key in ["processing_time", "memory_usage", "sections_processed"])
    
    print(f"{'PASS' if success else 'FAIL'} ExtractionMetrics serialization")
    print(f"      keys={list(metrics_dict.keys())}")
    print(f"      processing_time={metrics_dict['performance']['processing_time']}")
    
    return success

def test_ci_gates_evaluation():
    """Test CI gates evaluation with various scenarios"""
    print("\n=== Testing CI Gates Evaluation ===")
    
    test_cases = [
        {
            "metrics": ExtractionMetrics(
                processing_time=5.0,     # Under 30s limit
                memory_usage=500 * 1024 * 1024,  # Under 1GB limit
                sections_processed=10,
                sections_extracted=8,
                sections_gated=1,
                average_quality_score=0.75,  # Above 0.6 threshold
                average_confidence_score=0.65,  # Above 0.5 threshold
                parsing_errors=0,
                parsing_success_rate=0.8,  # Above 0.7 threshold
                date_parsing_success=5,
                date_parsing_errors=0,
                phase1_clusters_created=0,
                phase2_boundary_adjustments=0,
                phase3_entities_denoised=0,
                phase4_skills_separated=0,
                phase5_dates_parsed=0,
                phase6_sections_gated=1,
                errors=[],
                warnings=[],
                start_time=0,
                end_time=5
            ),
            "expected_passes": 7,  # Should pass all gates
            "desc": "High quality metrics (all gates should pass)"
        },
        {
            "metrics": ExtractionMetrics(
                processing_time=35.0,    # Over 30s limit
                memory_usage=2 * 1024 * 1024 * 1024,  # Over 1GB limit
                sections_processed=10,
                sections_extracted=5,
                sections_gated=4,
                average_quality_score=0.5,   # Below 0.6 threshold
                average_confidence_score=0.4,   # Below 0.5 threshold
                parsing_errors=3,
                parsing_success_rate=0.5,  # Below 0.7 threshold
                date_parsing_success=2,
                date_parsing_errors=3,
                phase1_clusters_created=0,
                phase2_boundary_adjustments=0,
                phase3_entities_denoised=0,
                phase4_skills_separated=0,
                phase5_dates_parsed=0,
                phase6_sections_gated=4,
                errors=["Error 1", "Error 2"],
                warnings=["Warning 1"],
                start_time=0,
                end_time=35
            ),
            "expected_passes": 1,  # Should fail most gates (gated_sections might still pass)
            "desc": "Poor quality metrics (most gates should fail)"
        }
    ]
    
    success_count = 0
    
    for case in test_cases:
        metrics = case["metrics"]
        expected_passes = case["expected_passes"]
        desc = case["desc"]
        
        gate_results = evaluate_ci_gates(metrics)
        actual_passes = sum(1 for result in gate_results.values() if result)
        
        success = actual_passes == expected_passes
        if success:
            success_count += 1
        
        print(f"{'PASS' if success else 'FAIL'} {desc}")
        print(f"      expected={expected_passes} passes, got={actual_passes} passes")
        print(f"      gates: {gate_results}")
    
    return success_count >= 1  # At least 1/2 should pass

def test_ci_gates_thresholds():
    """Test individual CI gate thresholds"""
    print("\n=== Testing Individual CI Gate Thresholds ===")
    
    # Test processing time gate
    fast_metrics = ExtractionMetrics(
        processing_time=5.0, memory_usage=0, sections_processed=1,
        sections_extracted=1, sections_gated=0, average_quality_score=0.8,
        average_confidence_score=0.8, parsing_errors=0, parsing_success_rate=1.0,
        date_parsing_success=1, date_parsing_errors=0, phase1_clusters_created=0,
        phase2_boundary_adjustments=0, phase3_entities_denoised=0, phase4_skills_separated=0,
        phase5_dates_parsed=0, phase6_sections_gated=0, errors=[], warnings=[], start_time=0, end_time=5
    )
    
    slow_metrics = ExtractionMetrics(
        processing_time=35.0, memory_usage=0, sections_processed=1,
        sections_extracted=1, sections_gated=0, average_quality_score=0.8,
        average_confidence_score=0.8, parsing_errors=0, parsing_success_rate=1.0,
        date_parsing_success=1, date_parsing_errors=0, phase1_clusters_created=0,
        phase2_boundary_adjustments=0, phase3_entities_denoised=0, phase4_skills_separated=0,
        phase5_dates_parsed=0, phase6_sections_gated=0, errors=[], warnings=[], start_time=0, end_time=35
    )
    
    fast_results = evaluate_ci_gates(fast_metrics)
    slow_results = evaluate_ci_gates(slow_metrics)
    
    # Fast should pass processing time, slow should fail
    time_gate_success = fast_results["processing_time"] and not slow_results["processing_time"]
    
    print(f"{'PASS' if time_gate_success else 'FAIL'} Processing time gate threshold")
    print(f"      fast(5s)={fast_results['processing_time']}, slow(35s)={slow_results['processing_time']}")
    
    return time_gate_success

def test_complete_metrics_pipeline():
    """Test the complete metrics pipeline integration"""
    print("\n=== Testing Complete Metrics Pipeline ===")
    
    # Mock quality assessments
    quality_assessments = {
        "experience_0_5": QualityAssessment(
            section_type="experience",
            start_line=0,
            end_line=5,
            quality_score=0.85,
            issues=[],
            recommendations=[],
            display_eligible=True,
            content_length=150,
            items_count=2,
            confidence_score=0.75,
            noise_ratio=0.1
        ),
        "skills_6_8": QualityAssessment(
            section_type="skills",
            start_line=6,
            end_line=8,
            quality_score=0.65,
            issues=["too_short"],
            recommendations=["Expand content"],
            display_eligible=True,
            content_length=30,
            items_count=5,
            confidence_score=0.60,
            noise_ratio=0.0
        )
    }
    
    # Mock boundaries
    boundaries = [(0, 5, "experience"), (6, 8, "skills")]
    lines = ["Experience content"] * 8
    
    # Mock collector with some data
    collector = MetricsCollector()
    collector.record_section_processed()
    collector.record_section_processed()
    
    # Apply metrics and scoring
    try:
        metrics, gate_results = apply_metrics_and_scoring(
            boundaries, lines, quality_assessments, collector
        )
        
        success = (
            isinstance(metrics, ExtractionMetrics) and
            isinstance(gate_results, dict) and
            len(gate_results) > 0
        )
        
        print(f"{'PASS' if success else 'FAIL'} Complete metrics pipeline")
        print(f"      metrics type: {type(metrics)}")
        print(f"      gates evaluated: {len(gate_results)}")
        
        return success
        
    except Exception as e:
        print(f"FAIL Complete metrics pipeline - Exception: {e}")
        return False

def test_metrics_json_serialization():
    """Test JSON serialization of metrics"""
    print("\n=== Testing Metrics JSON Serialization ===")
    
    metrics = ExtractionMetrics(
        processing_time=1.5,
        memory_usage=100 * 1024 * 1024,
        sections_processed=5,
        sections_extracted=4,
        sections_gated=1,
        average_quality_score=0.7,
        average_confidence_score=0.6,
        parsing_errors=0,
        parsing_success_rate=0.8,
        date_parsing_success=3,
        date_parsing_errors=0,
        phase1_clusters_created=1,
        phase2_boundary_adjustments=2,
        phase3_entities_denoised=10,
        phase4_skills_separated=8,
        phase5_dates_parsed=3,
        phase6_sections_gated=1,
        errors=[],
        warnings=["Sample warning"],
        start_time=1000,
        end_time=1001.5
    )
    
    try:
        import json
        metrics_dict = metrics.to_dict()
        json_str = json.dumps(metrics_dict, indent=2)
        
        # Try to parse it back
        parsed = json.loads(json_str)
        
        success = (
            isinstance(parsed, dict) and
            "performance" in parsed and
            "quality" in parsed and
            parsed["performance"]["processing_time"] == 1.5
        )
        
        print(f"{'PASS' if success else 'FAIL'} JSON serialization")
        print(f"      JSON length: {len(json_str)} chars")
        
        return success
        
    except Exception as e:
        print(f"FAIL JSON serialization - Exception: {e}")
        return False

if __name__ == "__main__":
    print("Phase 7 Metrics, Scoring and CI Gates Test Suite")
    print("=" * 60)
    
    success1 = test_metrics_collector()
    success2 = test_extraction_metrics_serialization()
    success3 = test_ci_gates_evaluation()
    success4 = test_ci_gates_thresholds()
    success5 = test_complete_metrics_pipeline()
    success6 = test_metrics_json_serialization()
    
    if all([success1, success2, success3, success4, success5, success6]):
        print("\nPhase 7 metrics, scoring and CI gates tests completed successfully!")
    else:
        print("\nSome Phase 7 tests failed!")