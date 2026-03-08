#!/usr/bin/env python3
"""
Enhanced Emoji Fix Script for CVMatch
=====================================

This script systematically converts emoji usage across the codebase to use
the fallback system, preventing display issues on systems without emoji support.
"""

import os
import re
from typing import List, Tuple, Dict
from pathlib import Path


class EmojiFixManager:
    """Manages emoji fixes across the codebase."""
    
    def __init__(self):
        self.emoji_mappings = {
            # Common UI emojis with their fallbacks
            "👤": "[P]",  # Profile
            "⚙️": "[S]",  # Settings
            "📋": "[N]",  # New/Notes
            "📊": "[G]",  # Graph/Stats
            "📂": "[F]",  # Folder
            "📁": "[F]",  # Folder open
            "🔗": "[L]",  # Link
            "👁️": "[V]", # View
            "✅": "[✓]", # Success
            "❌": "[✗]", # Error/Remove
            "🗑️": "[X]", # Delete
            "ℹ️": "[i]", # Info
        }
        
        self.patterns = {
            # UI elements that need get_display_text()
            'mixed_text': [
                (r'QLabel\("([^"]*[📊⚙️👤📋🏠📁📂🔧💼🎓📞📧🔗💡⚠️✅❌🔒🛡️🚫📈⚖️🎯👁️][^"]*?)"\)', 
                 r'QLabel(get_display_text("\1"))'),
                (r'QPushButton\("([^"]*[📊⚙️👤📋🏠📁📂🔧💼🎓📞📧🔗💡⚠️✅❌🔒🛡️🚫📈⚖️🎯👁️][^"]*?)"\)', 
                 r'QPushButton(get_display_text("\1"))'),
                (r'QGroupBox\("([^"]*[📊⚙️👤📋🏠📁📂🔧💼🎓📞📧🔗💡⚠️✅❌🔒🛡️🚫📈⚖️🎯👁️][^"]*?)"\)', 
                 r'QGroupBox(get_display_text("\1"))'),
                (r'setTitle\("([^"]*[📊⚙️👤📋🏠📁📂🔧💼🎓📞📧🔗💡⚠️✅❌🔒🛡️🚫📈⚖️🎯👁️][^"]*?)"\)', 
                 r'setTitle(get_display_text("\1"))'),
                (r'setText\("([^"]*[📊⚙️👤📋🏠📁📂🔧💼🎓📞📧🔗💡⚠️✅❌🔒🛡️🚫📈⚖️🎯👁️][^"]*?)"\)', 
                 r'setText(get_display_text("\1"))'),
            ],
            # Standalone emojis that need safe_emoji()
            'standalone': [
                (r'QPushButton\("([📊⚙️👤📋🏠📁📂🔧💼🎓📞📧🔗💡⚠️✅❌🔒🛡️🚫📈⚖️🎯👁️🗑️ℹ️])"\)', 
                 self._replace_standalone_emoji),
            ]
        }
    
    def _replace_standalone_emoji(self, match) -> str:
        """Replace standalone emoji with safe_emoji() call."""
        emoji = match.group(1)
        fallback = self.emoji_mappings.get(emoji, "[?]")
        return f'QPushButton(safe_emoji("{emoji}", "{fallback}"))'
    
    def scan_file(self, file_path: Path) -> Tuple[bool, List[str]]:
        """Scan a file for emoji usage and return if changes needed."""
        if not file_path.exists() or file_path.suffix != '.py':
            return False, []
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            return False, [f"Error reading {file_path}: {e}"]
        
        issues = []
        has_emoji_import = 'from ..utils.emoji_utils import' in content or 'from ...utils.emoji_utils import' in content
        
        # Check for raw emoji usage
        emoji_pattern = r'[📊⚙️👤📋🏠📁📂🔧💼🎓📞📧🔗💡⚠️✅❌🔒🛡️🚫📈⚖️🎯👁️🗑️ℹ️]'
        if re.search(emoji_pattern, content):
            issues.append("Contains raw emoji characters")
            
        # Check for missing imports
        if not has_emoji_import and re.search(emoji_pattern, content):
            issues.append("Missing emoji_utils import")
        
        # Check for double-wrapping
        if 'get_display_text(get_display_text(' in content:
            issues.append("Contains double-wrapped get_display_text calls")
        
        return len(issues) > 0, issues
    
    def fix_file(self, file_path: Path) -> Tuple[bool, List[str]]:
        """Apply emoji fixes to a file."""
        if not file_path.exists() or file_path.suffix != '.py':
            return False, ["File does not exist or is not Python"]
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            return False, [f"Error reading file: {e}"]
        
        original_content = content
        changes = []
        
        # Fix double-wrapping first
        if 'get_display_text(get_display_text(' in content:
            content = re.sub(r'get_display_text\(get_display_text\(([^)]+)\)\)', r'get_display_text(\1)', content)
            changes.append("Fixed double-wrapped get_display_text calls")
        
        # Add import if needed and raw emojis present
        emoji_pattern = r'[📊⚙️👤📋🏠📁📂🔧💼🎓📞📧🔗💡⚠️✅❌🔒🛡️🚫📈⚖️🎯👁️🗑️ℹ️]'
        has_emoji = re.search(emoji_pattern, content)
        has_import = 'from ..utils.emoji_utils import' in content or 'from ...utils.emoji_utils import' in content
        
        if has_emoji and not has_import:
            # Determine import depth based on file location
            relative_path = file_path.relative_to(Path.cwd())
            if 'widgets' in relative_path.parts:
                import_line = 'from ..utils.emoji_utils import get_display_text, safe_emoji'
            else:
                import_line = 'from ...utils.emoji_utils import get_display_text, safe_emoji'
            
            # Find a good place to insert the import
            lines = content.split('\n')
            insert_idx = -1
            for i, line in enumerate(lines):
                if line.startswith('from PySide6') or line.startswith('from loguru'):
                    insert_idx = i + 1
            
            if insert_idx > -1:
                lines.insert(insert_idx, import_line)
                content = '\n'.join(lines)
                changes.append("Added emoji_utils import")
        
        # Apply pattern fixes
        for pattern_type, patterns in self.patterns.items():
            for pattern, replacement in patterns:
                if callable(replacement):
                    # Custom replacement function
                    matches = list(re.finditer(pattern, content))
                    for match in reversed(matches):
                        new_text = replacement(match)
                        content = content[:match.start()] + new_text + content[match.end():]
                        changes.append(f"Applied {pattern_type} emoji fix")
                else:
                    # Simple regex replacement
                    if re.search(pattern, content):
                        content = re.sub(pattern, replacement, content)
                        changes.append(f"Applied {pattern_type} emoji fix")
        
        # Write back if changes were made
        if content != original_content:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                return True, changes
            except Exception as e:
                return False, [f"Error writing file: {e}"]
        
        return False, ["No changes needed"]
    
    def scan_codebase(self, root_path: Path = None) -> Dict[str, List[str]]:
        """Scan the entire codebase for emoji issues."""
        if root_path is None:
            root_path = Path.cwd()
        
        results = {}
        target_dirs = ['app/views', 'app/widgets', 'app/utils']
        
        for target_dir in target_dirs:
            dir_path = root_path / target_dir
            if not dir_path.exists():
                continue
                
            for py_file in dir_path.rglob('*.py'):
                needs_fix, issues = self.scan_file(py_file)
                if needs_fix:
                    results[str(py_file.relative_to(root_path))] = issues
        
        return results
    
    def fix_all(self, root_path: Path = None) -> Dict[str, Tuple[bool, List[str]]]:
        """Fix all emoji issues in the codebase."""
        if root_path is None:
            root_path = Path.cwd()
        
        # First scan for issues
        issues = self.scan_codebase(root_path)
        results = {}
        
        for file_path_str in issues:
            file_path = root_path / file_path_str
            success, changes = self.fix_file(file_path)
            results[file_path_str] = (success, changes)
        
        return results


def main():
    """Main execution function."""
    print("=== ENHANCED EMOJI FIX SCRIPT ===")
    
    manager = EmojiFixManager()
    
    # Scan for issues first
    print("\n1. Scanning codebase for emoji issues...")
    issues = manager.scan_codebase()
    
    if not issues:
        print("✅ No emoji issues found!")
        return
    
    print(f"\nFound issues in {len(issues)} files:")
    for file_path, file_issues in issues.items():
        print(f"  📁 {file_path}:")
        for issue in file_issues:
            print(f"    - {issue}")
    
    # Apply fixes
    print("\n2. Applying fixes...")
    results = manager.fix_all()
    
    print("\n=== RESULTS ===")
    for file_path, (success, changes) in results.items():
        status = "FIXED" if success else "FAILED"
        print(f"{file_path}: {status}")
        for change in changes:
            print(f"  - {change}")
    
    # Final verification
    print("\n3. Final verification...")
    remaining_issues = manager.scan_codebase()
    if remaining_issues:
        print(f"⚠️ {len(remaining_issues)} files still have issues:")
        for file_path, file_issues in remaining_issues.items():
            print(f"  📁 {file_path}: {', '.join(file_issues)}")
    else:
        print("✅ All emoji issues resolved!")


if __name__ == "__main__":
    main()