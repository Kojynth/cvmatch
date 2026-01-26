"""
Regex Lint - Validate and fix regex patterns throughout the codebase.

Scans Python files for regex patterns and validates them for syntax errors.
Provides automatic fixes for common regex issues.
"""

import re
import ast
from typing import List, Dict, Tuple, Optional
from pathlib import Path
from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class RegexIssue:
    """Represents a regex validation issue."""
    
    def __init__(self, file_path: str, line_number: int, pattern: str, error: str, suggested_fix: Optional[str] = None):
        self.file_path = file_path
        self.line_number = line_number
        self.pattern = pattern
        self.error = error
        self.suggested_fix = suggested_fix
    
    def __str__(self):
        fix_info = f" | Fix: {self.suggested_fix}" if self.suggested_fix else ""
        return f"{self.file_path}:{self.line_number} | Pattern: {self.pattern!r} | Error: {self.error}{fix_info}"


class RegexLinter:
    """Validates regex patterns in Python code."""
    
    def __init__(self, base_path: Optional[Path] = None):
        self.base_path = base_path or Path(".")
        self.logger = get_safe_logger(f"{__name__}.RegexLinter", cfg=DEFAULT_PII_CONFIG)
        
        # Common regex pattern fixes
        self.common_fixes = {
            # Unmatched parentheses
            r'([^\\])\(([^)]*$)': r'\1\(\2\)',  # Add closing paren
            r'(^[^(]*)\)': r'\1',  # Remove extra closing paren
            
            # Unmatched brackets  
            r'([^\\])\[([^\]]*$)': r'\1\[\2\]',  # Add closing bracket
            r'(^[^\[]*)\]': r'\1',  # Remove extra closing bracket
            
            # Unmatched braces
            r'([^\\])\{([^}]*$)': r'\1\{\2\}',  # Add closing brace
            r'(^[^{]*)\}': r'\1',  # Remove extra closing brace
            
            # Common escaping issues
            r'\\d[^+*?{]': r'\\d+',  # Add quantifier to \d
            r'\\w[^+*?{]': r'\\w+',  # Add quantifier to \w
        }
    
    def extract_regex_patterns_from_file(self, file_path: Path) -> List[Tuple[int, str]]:
        """Extract regex patterns from a Python file."""
        patterns = []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse as AST to find regex calls
            tree = ast.parse(content)
            
            # Also do line-by-line scan for raw strings
            lines = content.split('\n')
            for line_num, line in enumerate(lines, 1):
                # Look for raw strings that look like regex patterns
                raw_string_matches = re.findall(r'r[\'"]([^\'"]*)[\'"]', line)
                for match in raw_string_matches:
                    if self._looks_like_regex(match):
                        patterns.append((line_num, match))
                
                # Look for re.compile calls
                compile_matches = re.findall(r're\.compile\s*\(\s*[\'"]([^\'"]*)[\'"]', line)
                for match in compile_matches:
                    patterns.append((line_num, match))
                
                # Look for regex in lists/assignments that look like patterns
                if any(indicator in line.lower() for indicator in ['pattern', 'regex', '_re']):
                    string_matches = re.findall(r'[\'"]([^\'"]*)[\'"]', line)
                    for match in string_matches:
                        if self._looks_like_regex(match):
                            patterns.append((line_num, match))
        
        except Exception as e:
            self.logger.warning(f"REGEX_LINT: failed to parse {file_path} | error={e}")
        
        return patterns
    
    def _looks_like_regex(self, pattern: str) -> bool:
        """Heuristic to determine if a string looks like a regex pattern."""
        if len(pattern) < 3:
            return False
        
        regex_indicators = [
            r'\b', r'\d', r'\w', r'\s',  # Character classes
            r'[.*+?{}]', r'(?:', r'(?=', r'(?!',  # Regex syntax
            r'\|', r'\^', r'\$',  # Anchors and alternation
        ]
        
        return any(indicator in pattern for indicator in regex_indicators)
    
    def validate_regex_pattern(self, pattern: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validate a regex pattern.
        
        Returns:
            (is_valid, error_message, suggested_fix)
        """
        try:
            re.compile(pattern)
            return True, None, None
        except re.error as e:
            error_msg = str(e)
            suggested_fix = self._suggest_fix(pattern, error_msg)
            return False, error_msg, suggested_fix
    
    def _suggest_fix(self, pattern: str, error_msg: str) -> Optional[str]:
        """Suggest a fix for a broken regex pattern."""
        # Try common fixes
        for fix_pattern, replacement in self.common_fixes.items():
            try:
                fixed = re.sub(fix_pattern, replacement, pattern)
                if fixed != pattern:
                    # Test if fix works
                    re.compile(fixed)
                    return fixed
            except:
                continue
        
        # Pattern-specific fixes based on error message
        if "unmatched group" in error_msg.lower() or "unbalanced parenthesis" in error_msg.lower():
            # Try to balance parentheses
            open_count = pattern.count('(') - pattern.count(r'\(')
            close_count = pattern.count(')') - pattern.count(r'\)')
            
            if open_count > close_count:
                fixed = pattern + ')' * (open_count - close_count)
                try:
                    re.compile(fixed)
                    return fixed
                except:
                    pass
            elif close_count > open_count:
                # Remove extra closing parens from the end
                fixed = pattern
                for _ in range(close_count - open_count):
                    fixed = fixed.rsplit(')', 1)[0] if ')' in fixed else fixed
                try:
                    re.compile(fixed)
                    return fixed
                except:
                    pass
        
        return None
    
    def lint_file(self, file_path: Path) -> List[RegexIssue]:
        """Lint regex patterns in a single file."""
        issues = []
        patterns = self.extract_regex_patterns_from_file(file_path)
        
        for line_num, pattern in patterns:
            is_valid, error, suggested_fix = self.validate_regex_pattern(pattern)
            if not is_valid:
                issues.append(RegexIssue(
                    file_path=str(file_path.relative_to(self.base_path)),
                    line_number=line_num,
                    pattern=pattern,
                    error=error,
                    suggested_fix=suggested_fix
                ))
        
        return issues
    
    def lint_directory(self, directory: Path, pattern: str = "**/*.py") -> List[RegexIssue]:
        """Lint all Python files in a directory."""
        all_issues = []
        
        for file_path in directory.glob(pattern):
            if file_path.is_file():
                issues = self.lint_file(file_path)
                all_issues.extend(issues)
        
        return all_issues
    
    def generate_report(self, issues: List[RegexIssue]) -> str:
        """Generate a formatted report of regex issues."""
        if not issues:
            return "✅ No regex issues found!"
        
        report_lines = [
            f"🔍 Regex Lint Report - {len(issues)} issues found",
            "=" * 60
        ]
        
        # Group by file
        issues_by_file = {}
        for issue in issues:
            if issue.file_path not in issues_by_file:
                issues_by_file[issue.file_path] = []
            issues_by_file[issue.file_path].append(issue)
        
        for file_path, file_issues in issues_by_file.items():
            report_lines.append(f"\n📄 {file_path} ({len(file_issues)} issues)")
            report_lines.append("-" * 40)
            
            for issue in file_issues:
                report_lines.append(f"  Line {issue.line_number}: {issue.error}")
                report_lines.append(f"    Pattern: {issue.pattern!r}")
                if issue.suggested_fix:
                    report_lines.append(f"    Fix: {issue.suggested_fix!r}")
                else:
                    report_lines.append(f"    Fix: Manual review required")
                report_lines.append("")
        
        # Summary
        fixable_count = sum(1 for issue in issues if issue.suggested_fix)
        report_lines.extend([
            "=" * 60,
            f"📊 Summary: {len(issues)} total issues",
            f"🔧 {fixable_count} automatically fixable",
            f"⚠️  {len(issues) - fixable_count} require manual review"
        ])
        
        return "\n".join(report_lines)
    
    def apply_fixes(self, issues: List[RegexIssue], dry_run: bool = True) -> Dict[str, int]:
        """Apply automatic fixes to files."""
        stats = {"files_modified": 0, "patterns_fixed": 0, "patterns_skipped": 0}
        
        # Group by file
        fixes_by_file = {}
        for issue in issues:
            if issue.suggested_fix:
                if issue.file_path not in fixes_by_file:
                    fixes_by_file[issue.file_path] = []
                fixes_by_file[issue.file_path].append(issue)
        
        for file_path, file_fixes in fixes_by_file.items():
            full_path = self.base_path / file_path
            
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    lines = content.split('\n')
                
                modified = False
                for fix in file_fixes:
                    if fix.line_number <= len(lines):
                        old_line = lines[fix.line_number - 1]
                        new_line = old_line.replace(fix.pattern, fix.suggested_fix)
                        
                        if new_line != old_line:
                            lines[fix.line_number - 1] = new_line
                            modified = True
                            stats["patterns_fixed"] += 1
                            self.logger.info(f"REGEX_LINT: fixed pattern in {file_path}:{fix.line_number}")
                        else:
                            stats["patterns_skipped"] += 1
                
                if modified and not dry_run:
                    with open(full_path, 'w', encoding='utf-8') as f:
                        f.write('\n'.join(lines))
                    stats["files_modified"] += 1
                    
            except Exception as e:
                self.logger.error(f"REGEX_LINT: failed to apply fixes to {file_path} | error={e}")
        
        return stats


def lint_project_regex(base_path: Optional[Path] = None, apply_fixes: bool = False, dry_run: bool = True) -> str:
    """Lint regex patterns in the entire project."""
    linter = RegexLinter(base_path)
    
    # Lint specific directories that likely contain regex
    important_dirs = ["app/parsers", "app/utils", "app/rules", "app/workers"]
    all_issues = []
    
    base = linter.base_path
    for dir_name in important_dirs:
        dir_path = base / dir_name
        if dir_path.exists():
            issues = linter.lint_directory(dir_path)
            all_issues.extend(issues)
    
    # Generate report
    report = linter.generate_report(all_issues)
    
    # Apply fixes if requested
    if apply_fixes and all_issues:
        fix_stats = linter.apply_fixes(all_issues, dry_run=dry_run)
        report += f"\n\n🔧 Fix Results:"
        report += f"\n  Files modified: {fix_stats['files_modified']}"
        report += f"\n  Patterns fixed: {fix_stats['patterns_fixed']}"
        report += f"\n  Patterns skipped: {fix_stats['patterns_skipped']}"
        if dry_run:
            report += f"\n  (DRY RUN - no files actually modified)"
    
    return report


if __name__ == "__main__":
    # Command line interface
    import argparse
    
    parser = argparse.ArgumentParser(description="CVMatch Regex Linter")
    parser.add_argument("--path", type=Path, default=Path("."), help="Base path to lint")
    parser.add_argument("--fix", action="store_true", help="Apply automatic fixes")
    parser.add_argument("--no-dry-run", action="store_true", help="Actually modify files (not just preview)")
    parser.add_argument("--file", type=Path, help="Lint specific file only")
    
    args = parser.parse_args()
    
    if args.file:
        # Lint single file
        linter = RegexLinter(args.path)
        issues = linter.lint_file(args.file)
        report = linter.generate_report(issues)
        print(report)
        
        if args.fix and issues:
            stats = linter.apply_fixes(issues, dry_run=not args.no_dry_run)
            print(f"\nFix stats: {stats}")
    else:
        # Lint project
        report = lint_project_regex(
            base_path=args.path,
            apply_fixes=args.fix,
            dry_run=not args.no_dry_run
        )
        print(report)