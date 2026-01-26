"""
CLI configuration system for enhanced CV extraction with all offline flags.
Implements all the CLI flags specified in the prompt requirements.
"""

import argparse
import os
import json
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict
from pathlib import Path

from ..config import EXPERIENCE_CONF, DEFAULT_PII_CONFIG
from ..logging.safe_logger import get_safe_logger

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


@dataclass
class ExtractionFlags:
    """Dataclass to hold all extraction configuration flags."""
    
    # Core offline flags
    offline: bool = True
    mask_pii: bool = True
    
    # RTL and multilingual support  
    rtl_heuristics: bool = True
    
    # Boundary & Header-Conflict Guards
    max_cross_column_distance: int = 2
    header_conflict_killradius: int = 8
    
    # Tri-signal validation
    tri_signal_window: int = 3
    exp_gate_min: float = 0.55
    min_desc_tokens: int = 6
    
    # Pattern diversity enforcement
    pattern_diversity_enforce: bool = False
    pattern_diversity_floor: float = 0.30
    
    # Education extraction
    edu_strong_accept_only_under_threshold: bool = True
    org_conf_min: float = 0.75
    
    # Date precision requirements
    min_date_precision: str = "month"  # month, day, year
    
    # Output and debugging
    verbose: bool = False
    debug_extraction: bool = False
    save_metrics: bool = False
    metrics_output_path: Optional[str] = None


class CLIConfigManager:
    """Manages CLI configuration and flag parsing for CV extraction."""
    
    def __init__(self):
        self.flags = ExtractionFlags()
        self.parser = self._create_argument_parser()
        
    def _create_argument_parser(self) -> argparse.ArgumentParser:
        """Create comprehensive argument parser with all flags."""
        parser = argparse.ArgumentParser(
            description="Enhanced CV Extraction with Robust Gates and Anti-Overfitting",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog="""
Examples:
  # Run with full enforcement
  cvx run --offline --pattern-diversity-enforce --header-conflict-killradius=8 
         --tri-signal-window=3 --exp-gate-min=0.55
  
  # Run mutation tests
  cvx test --suite=e2e_holdout --mutations=all --offline
  
  # Print metrics comparison
  cvx metrics --compare=baseline.json --fields=boundary_quality,assoc_rate,pattern_diversity
"""
        )
        
        # Core operation mode
        parser.add_argument('--offline', 
                          action='store_true', 
                          default=True,
                          help='Run in fully offline mode (no network calls)')
        
        parser.add_argument('--mask-pii', 
                          action='store_true', 
                          default=True,
                          help='Enable PII masking in logs and outputs')
        
        # Multilingual and RTL support
        parser.add_argument('--rtl-heuristics', 
                          action='store_true',
                          default=True, 
                          help='Enable RTL text layout heuristics')
        
        # Boundary and header conflict guards
        parser.add_argument('--max-cross-column-distance', 
                          type=int, 
                          default=2,
                          help='Max line gaps for cross-column entity linking')
        
        parser.add_argument('--header-conflict-killradius', 
                          type=int, 
                          default=8,
                          help='Lines radius to check for education header conflicts')
        
        # Tri-signal experience gates
        parser.add_argument('--tri-signal-window', 
                          type=int, 
                          default=3,
                          help='Window size for tri-signal validation (date+org+role)')
        
        parser.add_argument('--exp-gate-min', 
                          type=float, 
                          default=0.55,
                          help='Minimum confidence gate for experience acceptance')
        
        parser.add_argument('--min-desc-tokens', 
                          type=int, 
                          default=6,
                          help='Minimum description tokens required (unless internship)')
        
        # Pattern diversity enforcement
        parser.add_argument('--pattern-diversity-enforce', 
                          action='store_true',
                          help='Enable pattern diversity enforcement gates')
        
        parser.add_argument('--pattern-diversity-floor', 
                          type=float, 
                          default=0.30,
                          help='Minimum pattern diversity threshold')
        
        # Education extractor settings
        parser.add_argument('--edu-strong-accept-only-under-threshold', 
                          action='store_true',
                          default=True,
                          help='Require strong signals when education keep rate is low')
        
        parser.add_argument('--org-conf-min', 
                          type=float, 
                          default=0.75,
                          help='Minimum organization confidence for fallback acceptance')
        
        # Date precision
        parser.add_argument('--min-date-precision', 
                          choices=['year', 'month', 'day'],
                          default='month',
                          help='Minimum required date precision')
        
        # Output and debugging
        parser.add_argument('--verbose', '-v',
                          action='store_true',
                          help='Enable verbose logging')
        
        parser.add_argument('--debug-extraction',
                          action='store_true', 
                          help='Enable detailed extraction debugging')
        
        parser.add_argument('--save-metrics',
                          action='store_true',
                          help='Save extraction metrics to file')
        
        parser.add_argument('--metrics-output-path',
                          type=str,
                          help='Path to save metrics JSON file')
        
        return parser
        
    def parse_args(self, args: Optional[list] = None) -> ExtractionFlags:
        """Parse command line arguments and return flags."""
        parsed = self.parser.parse_args(args)
        
        # Update flags from parsed arguments
        for field_name in self.flags.__dataclass_fields__:
            if hasattr(parsed, field_name):
                setattr(self.flags, field_name, getattr(parsed, field_name))
            # Handle argument names with dashes
            dash_name = field_name.replace('_', '-')
            if hasattr(parsed, dash_name.replace('-', '_')):
                setattr(self.flags, field_name, getattr(parsed, dash_name.replace('-', '_')))
                
        logger.info(f"CLI_CONFIG: flags_parsed | offline={self.flags.offline} "
                   f"pattern_diversity_enforce={self.flags.pattern_diversity_enforce} "
                   f"header_conflict_killradius={self.flags.header_conflict_killradius}")
        
        return self.flags
        
    def apply_flags_to_config(self, flags: ExtractionFlags) -> Dict[str, Any]:
        """Apply CLI flags to extraction configuration."""
        # Start with base config
        config = EXPERIENCE_CONF.copy()
        
        # Apply boundary guards flags
        config["max_cross_column_distance_lines"] = flags.max_cross_column_distance
        config["header_conflict_killradius_lines"] = flags.header_conflict_killradius
        
        # Apply tri-signal flags
        config["tri_signal_window"] = flags.tri_signal_window
        config["exp_gate_min"] = flags.exp_gate_min
        config["min_desc_tokens"] = flags.min_desc_tokens
        
        # Apply pattern diversity flags
        config["pattern_diversity_enforce"] = flags.pattern_diversity_enforce
        config["pattern_diversity_floor"] = flags.pattern_diversity_floor
        
        # Apply education flags
        config["edu_strong_signals_org_conf_min"] = flags.org_conf_min
        
        # Apply date precision
        config["min_date_precision"] = flags.min_date_precision
        
        # RTL heuristics
        config["rtl_heuristics"] = flags.rtl_heuristics
        
        logger.info("CLI_CONFIG: configuration_updated_from_flags")
        
        return config
        
    def create_extraction_context(self, flags: ExtractionFlags) -> Dict[str, Any]:
        """Create extraction context with all runtime parameters."""
        context = {
            'flags': asdict(flags),
            'config': self.apply_flags_to_config(flags),
            'runtime': {
                'offline_mode': flags.offline,
                'pii_masking': flags.mask_pii,
                'verbose_logging': flags.verbose,
                'debug_extraction': flags.debug_extraction
            }
        }
        
        return context
        
    def save_config_to_file(self, config_path: str, flags: ExtractionFlags):
        """Save current configuration to JSON file."""
        config_data = {
            'flags': asdict(flags),
            'applied_config': self.apply_flags_to_config(flags),
            'metadata': {
                'version': '1.0.0',
                'created_by': 'enhanced_cv_extractor'
            }
        }
        
        Path(config_path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
            
        logger.info(f"CLI_CONFIG: saved_to_file | path={config_path}")
        
    def load_config_from_file(self, config_path: str) -> ExtractionFlags:
        """Load configuration from JSON file."""
        if not Path(config_path).exists():
            logger.warning(f"CLI_CONFIG: file_not_found | path={config_path}")
            return self.flags
            
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                
            flags_dict = config_data.get('flags', {})
            
            # Update flags from loaded data
            for field_name, value in flags_dict.items():
                if hasattr(self.flags, field_name):
                    setattr(self.flags, field_name, value)
                    
            logger.info(f"CLI_CONFIG: loaded_from_file | path={config_path}")
            return self.flags
            
        except Exception as e:
            logger.error(f"CLI_CONFIG: load_error | path={config_path} error={e}")
            return self.flags
            
    def get_help_text(self) -> str:
        """Get comprehensive help text."""
        return self.parser.format_help()
        
    def validate_flags(self, flags: ExtractionFlags) -> Dict[str, Any]:
        """Validate flag combinations and values."""
        validation_result = {
            'valid': True,
            'warnings': [],
            'errors': []
        }
        
        # Validate numeric ranges
        if flags.exp_gate_min < 0.0 or flags.exp_gate_min > 1.0:
            validation_result['errors'].append(
                f"exp_gate_min must be between 0.0 and 1.0, got {flags.exp_gate_min}"
            )
            
        if flags.pattern_diversity_floor < 0.0 or flags.pattern_diversity_floor > 1.0:
            validation_result['errors'].append(
                f"pattern_diversity_floor must be between 0.0 and 1.0, got {flags.pattern_diversity_floor}"
            )
            
        if flags.org_conf_min < 0.0 or flags.org_conf_min > 1.0:
            validation_result['errors'].append(
                f"org_conf_min must be between 0.0 and 1.0, got {flags.org_conf_min}"
            )
            
        # Validate positive integers
        if flags.tri_signal_window <= 0:
            validation_result['errors'].append(
                f"tri_signal_window must be positive, got {flags.tri_signal_window}"
            )
            
        if flags.min_desc_tokens < 0:
            validation_result['errors'].append(
                f"min_desc_tokens must be non-negative, got {flags.min_desc_tokens}"
            )
            
        # Logical validations
        if flags.pattern_diversity_enforce and flags.pattern_diversity_floor >= 0.9:
            validation_result['warnings'].append(
                f"Very high pattern_diversity_floor ({flags.pattern_diversity_floor}) with enforcement may block most extractions"
            )
            
        if flags.exp_gate_min >= 0.9:
            validation_result['warnings'].append(
                f"Very high exp_gate_min ({flags.exp_gate_min}) may reject most experiences"
            )
            
        # Check for conflicting settings
        if not flags.offline and flags.mask_pii:
            validation_result['warnings'].append(
                "PII masking enabled in non-offline mode - ensure compliance with data policies"
            )
            
        validation_result['valid'] = len(validation_result['errors']) == 0
        
        return validation_result


def create_test_commands_parser() -> argparse.ArgumentParser:
    """Create parser for test-specific commands."""
    parser = argparse.ArgumentParser(description="CV Extraction Testing Commands")
    
    subparsers = parser.add_subparsers(dest='test_command', help='Test commands')
    
    # E2E holdout tests
    e2e_parser = subparsers.add_parser('e2e_holdout', help='Run E2E tests on holdout dataset')
    e2e_parser.add_argument('--mutations', 
                           choices=['all', 'coordinate', 'column', 'rtl', 'ocr', 'dates'],
                           default='all',
                           help='Mutation test types to run')
    e2e_parser.add_argument('--holdout-path', 
                           type=str, 
                           help='Path to holdout dataset')
    
    # Metrics comparison
    metrics_parser = subparsers.add_parser('metrics', help='Compare extraction metrics')
    metrics_parser.add_argument('--compare', 
                               type=str, 
                               help='Baseline metrics file to compare against')
    metrics_parser.add_argument('--fields',
                               type=str,
                               help='Comma-separated list of metrics fields to compare')
    
    return parser


def create_run_parser() -> argparse.ArgumentParser:
    """Create parser for run commands."""
    parser = argparse.ArgumentParser(description="Run CV Extraction")
    
    parser.add_argument('input_path', 
                       type=str, 
                       help='Path to CV file or directory')
    
    parser.add_argument('--output-path', '-o',
                       type=str,
                       help='Output path for results')
    
    parser.add_argument('--format',
                       choices=['json', 'yaml', 'csv'],
                       default='json',
                       help='Output format')
    
    return parser


# Global CLI manager instance
cli_manager = CLIConfigManager()


def get_cli_config() -> CLIConfigManager:
    """Get global CLI configuration manager."""
    return cli_manager
