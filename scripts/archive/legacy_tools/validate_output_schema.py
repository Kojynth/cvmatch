#!/usr/bin/env python3
"""
Output Schema Validation Script
===============================

Validates CV extraction output against the defined JSON schema
and provides detailed validation reports.
"""

import sys
import json
import jsonschema
from pathlib import Path
from typing import Dict, Any, List, Optional
import time
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def load_schema() -> Dict[str, Any]:
    """Load the JSON schema for validation."""
    schema_path = project_root / "schemas" / "cv_extraction_output.json"

    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    with open(schema_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def create_sample_output() -> Dict[str, Any]:
    """Create a sample valid output for testing."""
    return {
        "document_metadata": {
            "document_id": "test_doc_001",
            "extraction_timestamp": datetime.now().isoformat(),
            "pipeline_version": "1.0.0",
            "extraction_mode": "AI_FIRST",
            "document_properties": {
                "filename": "sample_cv.pdf",
                "file_size_bytes": 245760,
                "page_count": 2,
                "language_detected": "en",
                "primary_script": "LATIN",
                "text_direction": "LTR",
                "reading_order_hint": "natural"
            }
        },
        "extraction_results": {
            "sections": [
                {
                    "section_type": "experience",
                    "section_id": "exp_001",
                    "confidence": 0.92,
                    "bounding_box": {
                        "page": 1,
                        "x": 50,
                        "y": 100,
                        "width": 400,
                        "height": 200
                    },
                    "items": [
                        {
                            "item_id": "exp_item_001",
                            "item_type": "experience",
                            "confidence": 0.89,
                            "fields": {
                                "title": "Senior Software Engineer",
                                "organization": "TechCorp Inc",
                                "location": "San Francisco, CA",
                                "start_date": "2020-01",
                                "end_date": "PRESENT",
                                "description": "Led development of microservices architecture",
                                "employment_type": "full_time"
                            },
                            "triad_scores": {
                                "date_confidence": 0.95,
                                "role_confidence": 0.87,
                                "organization_confidence": 0.91,
                                "association_score": 0.88
                            },
                            "normalization_details": {
                                "date_normalization": {
                                    "original": "2020-present",
                                    "normalized": "2020-01 - PRESENT",
                                    "format_type": "range",
                                    "is_present": True
                                }
                            }
                        }
                    ],
                    "structure_flags": {
                        "is_sidebar": False,
                        "is_timeline": True,
                        "column_id": 1,
                        "reading_order": "ltr",
                        "is_quarantined": False,
                        "merge_candidate": False
                    },
                    "normalization_applied": {
                        "date_normalization": True,
                        "language_normalization": False,
                        "field_contamination_cleaning": True
                    }
                },
                {
                    "section_type": "languages",
                    "section_id": "lang_001",
                    "confidence": 0.85,
                    "bounding_box": {
                        "page": 2,
                        "x": 50,
                        "y": 300,
                        "width": 300,
                        "height": 80
                    },
                    "items": [
                        {
                            "item_id": "lang_item_001",
                            "item_type": "language_skill",
                            "confidence": 0.88,
                            "fields": {
                                "language": "English",
                                "proficiency_description": "Native",
                                "cefr_level": "NATIVE",
                                "cefr_confidence": 0.98
                            }
                        }
                    ],
                    "structure_flags": {
                        "is_sidebar": True,
                        "is_timeline": False,
                        "column_id": 2,
                        "reading_order": "ltr",
                        "is_quarantined": False,
                        "merge_candidate": False
                    },
                    "normalization_applied": {
                        "date_normalization": False,
                        "language_normalization": True,
                        "field_contamination_cleaning": False
                    }
                }
            ]
        },
        "quality_metrics": {
            "overall_quality_score": 0.82,
            "association_rate": 0.78,
            "experience_coverage": 0.85,
            "education_keep_rate": 0.90,
            "boundary_overlap_count": 0,
            "extraction_warnings": [
                "Low confidence in organization detection for item exp_item_002"
            ],
            "success_criteria_met": True,
            "robustness_score": 0.79
        },
        "processing_metadata": {
            "total_processing_time_seconds": 2.34,
            "ai_gate_health_score": 0.91,
            "heuristic_fallback_triggered": False,
            "sections_quarantined": 0,
            "items_normalized": 5,
            "routing_decisions": {
                "experience_to_education": 0,
                "experience_to_certifications": 1,
                "internship_rebindings": 2
            }
        },
        "internationalization": {
            "detected_languages": [
                {
                    "language_code": "en",
                    "confidence": 0.95,
                    "script_type": "LATIN",
                    "text_samples": [
                        "Senior Software Engineer",
                        "Led development of microservices"
                    ]
                }
            ]
        }
    }


def create_invalid_sample() -> Dict[str, Any]:
    """Create an invalid sample for testing validation errors."""
    return {
        "document_metadata": {
            "document_id": "test_doc_002",
            "extraction_timestamp": "not-a-valid-datetime",  # Invalid datetime
            "pipeline_version": "invalid-version",  # Invalid version format
            "extraction_mode": "INVALID_MODE"  # Invalid enum value
        },
        "extraction_results": {
            "sections": [
                {
                    "section_type": "invalid_section",  # Invalid enum value
                    "section_id": "",  # Empty string
                    "confidence": 1.5,  # Out of range
                    "items": [
                        {
                            "item_id": "item_001",
                            "item_type": "test",
                            "confidence": -0.1,  # Negative confidence
                            "fields": {}
                        }
                    ]
                }
            ]
        },
        "quality_metrics": {
            "overall_quality_score": 2.0,  # Out of range
            "success_criteria_met": "not-a-boolean"  # Wrong type
        }
    }


def validate_output(data: Dict[str, Any], schema: Dict[str, Any]) -> tuple[bool, List[str]]:
    """
    Validate output data against schema.

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    try:
        jsonschema.validate(data, schema)
        return True, []
    except jsonschema.ValidationError as e:
        # Collect all validation errors
        errors = []
        validator = jsonschema.Draft202012Validator(schema)

        for error in validator.iter_errors(data):
            error_path = " -> ".join(str(p) for p in error.absolute_path) if error.absolute_path else "root"
            error_message = f"Path: {error_path} | Error: {error.message}"
            errors.append(error_message)

        return False, errors
    except Exception as e:
        return False, [f"Schema validation exception: {str(e)}"]


def run_validation_tests():
    """Run comprehensive validation tests."""
    print("CV Extraction Output Schema Validation")
    print("=" * 50)

    # Load schema
    try:
        schema = load_schema()
        print("[OK] Schema loaded successfully")
        print(f"  Schema ID: {schema.get('$id', 'Not specified')}")
        print(f"  Title: {schema.get('title', 'Not specified')}")
    except Exception as e:
        print(f"[ERROR] Failed to load schema: {e}")
        return 1

    print()

    # Test 1: Valid sample
    print("Test 1: Validating valid sample output")
    try:
        valid_sample = create_sample_output()
        is_valid, errors = validate_output(valid_sample, schema)

        if is_valid:
            print("[PASS] Valid sample passed validation")
        else:
            print("[FAIL] Valid sample failed validation:")
            for error in errors[:5]:  # Show first 5 errors
                print(f"  - {error}")
            if len(errors) > 5:
                print(f"  ... and {len(errors) - 5} more errors")
    except Exception as e:
        print(f"[ERROR] Error testing valid sample: {e}")

    print()

    # Test 2: Invalid sample
    print("Test 2: Validating invalid sample output")
    try:
        invalid_sample = create_invalid_sample()
        is_valid, errors = validate_output(invalid_sample, schema)

        if not is_valid:
            print(f"[PASS] Invalid sample correctly rejected ({len(errors)} errors found)")
            print("  Sample error messages:")
            for error in errors[:3]:
                print(f"  - {error}")
            if len(errors) > 3:
                print(f"  ... and {len(errors) - 3} more errors")
        else:
            print("[FAIL] Invalid sample incorrectly passed validation")
    except Exception as e:
        print(f"[ERROR] Error testing invalid sample: {e}")

    print()

    # Test 3: Edge cases
    print("Test 3: Testing edge cases")

    edge_cases = [
        # Minimal valid document
        {
            "name": "Minimal valid document",
            "data": {
                "document_metadata": {
                    "document_id": "minimal_001",
                    "extraction_timestamp": datetime.now().isoformat(),
                    "pipeline_version": "1.0.0",
                    "extraction_mode": "HEURISTIC_ONLY"
                },
                "extraction_results": {
                    "sections": []  # Empty sections array
                },
                "quality_metrics": {
                    "overall_quality_score": 0.0,
                    "success_criteria_met": False
                }
            }
        },
        # Missing required field
        {
            "name": "Missing required field",
            "data": {
                "document_metadata": {
                    "document_id": "missing_field_001",
                    "extraction_timestamp": datetime.now().isoformat(),
                    "pipeline_version": "1.0.0"
                    # Missing extraction_mode
                },
                "extraction_results": {
                    "sections": []
                },
                "quality_metrics": {
                    "overall_quality_score": 0.5,
                    "success_criteria_met": True
                }
            }
        },
        # Boundary values
        {
            "name": "Boundary values test",
            "data": {
                "document_metadata": {
                    "document_id": "boundary_001",
                    "extraction_timestamp": datetime.now().isoformat(),
                    "pipeline_version": "1.0.0",
                    "extraction_mode": "AI_STRICT"
                },
                "extraction_results": {
                    "sections": []
                },
                "quality_metrics": {
                    "overall_quality_score": 1.0,  # Maximum value
                    "association_rate": 0.0,  # Minimum value
                    "boundary_overlap_count": 0,
                    "success_criteria_met": True
                }
            }
        }
    ]

    for test_case in edge_cases:
        is_valid, errors = validate_output(test_case["data"], schema)
        status = "[PASS]" if (is_valid and "Missing" not in test_case["name"]) or (not is_valid and "Missing" in test_case["name"]) else "[FAIL]"
        print(f"  {status} {test_case['name']}: {'Valid' if is_valid else f'Invalid ({len(errors)} errors)'}")

    print()

    # Test 4: Performance test
    print("Test 4: Performance test")
    start_time = time.time()

    # Validate the same document 100 times
    sample = create_sample_output()
    for _ in range(100):
        validate_output(sample, schema)

    end_time = time.time()
    avg_time_ms = ((end_time - start_time) / 100) * 1000

    print(f"  [OK] Average validation time: {avg_time_ms:.2f}ms per document")

    print()
    print("=" * 50)
    print("Schema validation tests completed")

    return 0


def main():
    """Main entry point."""
    return run_validation_tests()


if __name__ == "__main__":
    sys.exit(main())