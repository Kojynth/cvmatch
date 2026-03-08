#!/usr/bin/env python3
"""
Syntax Validation Script for CVMatch
===================================

Pre-launch syntax validation to catch indentation errors, syntax errors,
and import issues before they cause app crashes.

Usage:
    python scripts/validate_syntax.py
    python scripts/validate_syntax.py --critical-only
    python scripts/validate_syntax.py --module app.utils.education_extractor_enhanced
"""

import py_compile
import ast
import sys
import os
import importlib
import traceback
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import argparse


class SyntaxValidator:
    """Comprehensive syntax validation for Python files."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.errors = []
        self.warnings = []

        # Critical modules that must work for app startup
        self.critical_modules = [
            'app.views.main_window',
            'app.workers.cv_extractor',
            'app.utils.education_extractor_enhanced',
            'app.utils.boundary_guards',
            'app.utils.robust_date_parser',
            'app.utils.extraction_mapper',
            'app.utils.text_norm',
            'app.models.user_profile',
            'main'
        ]

        # File patterns to validate
        self.file_patterns = [
            'app/**/*.py',
            'tests/**/*.py',
            'scripts/**/*.py',
            'main.py'
        ]

    def validate_all(self, critical_only: bool = False) -> Dict[str, Any]:
        """
        Validate all Python files or only critical modules.

        Args:
            critical_only: If True, only validate critical startup modules

        Returns:
            Dict with validation results
        """
        print("[VALIDATE] Starting syntax validation...")

        if critical_only:
            results = self._validate_critical_modules()
        else:
            results = self._validate_all_files()

        self._print_summary(results)
        return results

    def validate_specific_module(self, module_name: str) -> Dict[str, Any]:
        """
        Validate a specific module by name.

        Args:
            module_name: Python module name (e.g., 'app.utils.text_norm')

        Returns:
            Dict with validation results for the module
        """
        print(f"[VALIDATE] Validating module: {module_name}")

        try:
            # Convert module name to file path
            file_path = self.project_root / (module_name.replace('.', '/') + '.py')

            if not file_path.exists():
                return {
                    'success': False,
                    'error': f"Module file not found: {file_path}",
                    'type': 'file_not_found'
                }

            result = self._validate_single_file(file_path)
            self._print_file_result(file_path, result)

            return {
                'success': result['success'],
                'file_path': str(file_path),
                'result': result
            }

        except Exception as e:
            error_msg = f"Error validating module {module_name}: {e}"
            print(f"[ERROR] {error_msg}")
            return {
                'success': False,
                'error': error_msg,
                'type': 'validation_error'
            }

    def _validate_critical_modules(self) -> Dict[str, Any]:
        """Validate only critical startup modules."""
        results = {
            'validated_count': 0,
            'error_count': 0,
            'warning_count': 0,
            'files': {},
            'critical_failures': []
        }

        for module_name in self.critical_modules:
            file_path = self.project_root / (module_name.replace('.', '/') + '.py')

            if not file_path.exists():
                error = f"Critical module not found: {module_name}"
                results['critical_failures'].append(error)
                results['error_count'] += 1
                print(f"[ERROR] {error}")
                continue

            result = self._validate_single_file(file_path)
            results['files'][str(file_path)] = result
            results['validated_count'] += 1

            if not result['success']:
                results['error_count'] += 1
                results['critical_failures'].append(f"{module_name}: {result.get('error', 'Unknown error')}")

            if result.get('warnings'):
                results['warning_count'] += len(result['warnings'])

            self._print_file_result(file_path, result)

        return results

    def _validate_all_files(self) -> Dict[str, Any]:
        """Validate all Python files in the project."""
        results = {
            'validated_count': 0,
            'error_count': 0,
            'warning_count': 0,
            'files': {},
            'critical_failures': []
        }

        for pattern in self.file_patterns:
            for file_path in self.project_root.glob(pattern):
                if file_path.is_file() and file_path.suffix == '.py':
                    result = self._validate_single_file(file_path)
                    results['files'][str(file_path)] = result
                    results['validated_count'] += 1

                    if not result['success']:
                        results['error_count'] += 1

                        # Check if this is a critical module
                        module_name = self._file_path_to_module_name(file_path)
                        if module_name in self.critical_modules:
                            results['critical_failures'].append(f"{module_name}: {result.get('error', 'Unknown error')}")

                    if result.get('warnings'):
                        results['warning_count'] += len(result['warnings'])

                    self._print_file_result(file_path, result)

        return results

    def _validate_single_file(self, file_path: Path) -> Dict[str, Any]:
        """
        Validate a single Python file.

        Args:
            file_path: Path to the Python file

        Returns:
            Dict with validation result
        """
        result = {
            'success': True,
            'errors': [],
            'warnings': [],
            'checks': {
                'syntax': False,
                'compilation': False,
                'import': False,
                'indentation': False
            }
        }

        try:
            # Read file content
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # Check 1: AST parsing (syntax validation)
            try:
                ast.parse(content)
                result['checks']['syntax'] = True
            except SyntaxError as e:
                result['success'] = False
                result['errors'].append({
                    'type': 'syntax_error',
                    'message': str(e),
                    'line': getattr(e, 'lineno', None),
                    'offset': getattr(e, 'offset', None)
                })
            except IndentationError as e:
                result['success'] = False
                result['errors'].append({
                    'type': 'indentation_error',
                    'message': str(e),
                    'line': getattr(e, 'lineno', None),
                    'offset': getattr(e, 'offset', None)
                })

            # Check 2: Compilation
            if result['checks']['syntax']:
                try:
                    py_compile.compile(str(file_path), doraise=True)
                    result['checks']['compilation'] = True
                except py_compile.PyCompileError as e:
                    result['success'] = False
                    result['errors'].append({
                        'type': 'compilation_error',
                        'message': str(e)
                    })

            # Check 3: Indentation consistency
            indentation_issues = self._check_indentation_consistency(content)
            if indentation_issues:
                result['warnings'].extend(indentation_issues)
            else:
                result['checks']['indentation'] = True

            # Check 4: Import validation (for critical modules)
            module_name = self._file_path_to_module_name(file_path)
            if module_name in self.critical_modules:
                import_result = self._validate_imports(file_path, content)
                result['checks']['import'] = import_result['success']
                if not import_result['success']:
                    result['errors'].extend(import_result['errors'])
            else:
                result['checks']['import'] = True  # Skip for non-critical

        except Exception as e:
            result['success'] = False
            result['errors'].append({
                'type': 'validation_error',
                'message': f"Unexpected error during validation: {e}"
            })

        return result

    def _check_indentation_consistency(self, content: str) -> List[Dict[str, Any]]:
        """Check for indentation consistency issues."""
        warnings = []
        lines = content.split('\n')

        # Track indentation patterns
        indent_chars = set()
        for line_num, line in enumerate(lines, 1):
            if line.strip():  # Skip empty lines
                leading_whitespace = line[:len(line) - len(line.lstrip())]
                if leading_whitespace:
                    if '\t' in leading_whitespace and ' ' in leading_whitespace:
                        warnings.append({
                            'type': 'mixed_indentation',
                            'message': 'Mixed tabs and spaces in indentation',
                            'line': line_num
                        })

                    if '\t' in leading_whitespace:
                        indent_chars.add('tab')
                    if ' ' in leading_whitespace:
                        indent_chars.add('space')

        if len(indent_chars) > 1:
            warnings.append({
                'type': 'inconsistent_indentation',
                'message': 'File uses both tabs and spaces for indentation'
            })

        return warnings

    def _validate_imports(self, file_path: Path, content: str) -> Dict[str, Any]:
        """Validate that all imports can be resolved."""
        result = {'success': True, 'errors': []}

        try:
            # Parse AST to extract imports
            tree = ast.parse(content)

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if not self._can_import_module(alias.name):
                            result['success'] = False
                            result['errors'].append({
                                'type': 'import_error',
                                'message': f"Cannot import module: {alias.name}",
                                'line': node.lineno
                            })

                elif isinstance(node, ast.ImportFrom):
                    module_name = node.module
                    if module_name and not self._can_import_module(module_name):
                        result['success'] = False
                        result['errors'].append({
                            'type': 'import_error',
                            'message': f"Cannot import from module: {module_name}",
                            'line': node.lineno
                        })

        except Exception as e:
            result['success'] = False
            result['errors'].append({
                'type': 'import_validation_error',
                'message': f"Error validating imports: {e}"
            })

        return result

    def _can_import_module(self, module_name: str) -> bool:
        """Check if a module can be imported."""
        try:
            importlib.import_module(module_name)
            return True
        except ImportError:
            # Check if it's a relative import within the project
            if module_name.startswith('.'):
                return True  # Skip relative imports

            # Check if it's a project module
            if module_name.startswith('app'):
                module_path = self.project_root / (module_name.replace('.', '/') + '.py')
                return module_path.exists()

            return False
        except Exception:
            return False

    def _file_path_to_module_name(self, file_path: Path) -> str:
        """Convert file path to Python module name."""
        relative_path = file_path.relative_to(self.project_root)
        module_name = str(relative_path.with_suffix(''))
        return module_name.replace('/', '.').replace('\\', '.')

    def _print_file_result(self, file_path: Path, result: Dict[str, Any]):
        """Print validation result for a single file."""
        relative_path = file_path.relative_to(self.project_root)

        if result['success']:
            print(f"[OK] {relative_path}")
        else:
            print(f"[FAIL] {relative_path}")

            for error in result['errors']:
                error_type = error.get('type', 'unknown')
                message = error.get('message', 'Unknown error')
                line = error.get('line')

                if line:
                    print(f"   {error_type} (line {line}): {message}")
                else:
                    print(f"   {error_type}: {message}")

        # Print warnings
        for warning in result.get('warnings', []):
            warning_type = warning.get('type', 'unknown')
            message = warning.get('message', 'Unknown warning')
            line = warning.get('line')

            if line:
                print(f"[WARN] {relative_path} - {warning_type} (line {line}): {message}")
            else:
                print(f"[WARN] {relative_path} - {warning_type}: {message}")

    def _print_summary(self, results: Dict[str, Any]):
        """Print validation summary."""
        print("\n" + "="*60)
        print("[SUMMARY] VALIDATION SUMMARY")
        print("="*60)

        print(f"Files validated: {results['validated_count']}")
        print(f"Errors found: {results['error_count']}")
        print(f"Warnings found: {results['warning_count']}")

        if results['critical_failures']:
            print(f"\n[CRITICAL] CRITICAL FAILURES ({len(results['critical_failures'])}):")
            for failure in results['critical_failures']:
                print(f"   • {failure}")

        if results['error_count'] == 0:
            print("\n[SUCCESS] All files passed syntax validation!")
        else:
            print(f"\n[FAIL] {results['error_count']} files failed syntax validation")

        if results['critical_failures']:
            print("\n[CRITICAL] App launch will fail due to critical module errors!")
            return False
        else:
            print("\n[SUCCESS] All critical modules passed validation - app should launch successfully")
            return True


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Validate Python syntax for CVMatch')
    parser.add_argument('--critical-only', action='store_true',
                       help='Only validate critical startup modules')
    parser.add_argument('--module', type=str,
                       help='Validate specific module (e.g., app.utils.text_norm)')

    args = parser.parse_args()

    # Find project root
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    if not (project_root / 'main.py').exists():
        print("[ERROR] Could not find project root (main.py not found)")
        sys.exit(1)

    validator = SyntaxValidator(project_root)

    try:
        if args.module:
            # Validate specific module
            result = validator.validate_specific_module(args.module)
            success = result['success']
        else:
            # Validate all or critical only
            results = validator.validate_all(critical_only=args.critical_only)
            success = len(results['critical_failures']) == 0

        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n[INTERRUPT] Validation interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"[ERROR] Unexpected error: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()