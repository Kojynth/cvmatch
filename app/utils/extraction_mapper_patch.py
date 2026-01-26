"""
Monkey patch to replace apply_smart_mapping with the improved version.
"""

from . import extraction_mapper
from .extraction_mapper_improved import enhance_extraction_mapping_with_validation
from .extraction_postprocessor import redistribute_sections


# Apply the enhancement to the apply_smart_mapping function
original_apply_smart_mapping = extraction_mapper.apply_smart_mapping
enhanced_apply_smart_mapping = enhance_extraction_mapping_with_validation(original_apply_smart_mapping)


def apply_with_postprocessing(data: dict) -> dict:
    result = enhanced_apply_smart_mapping(data)
    return redistribute_sections(result, inplace=False)

# Replace the original function
extraction_mapper.apply_smart_mapping = apply_with_postprocessing

# Also patch the global reference if used elsewhere
import sys
if 'cvmatch.app.utils.extraction_mapper' in sys.modules:
    sys.modules['cvmatch.app.utils.extraction_mapper'].apply_smart_mapping = apply_with_postprocessing
