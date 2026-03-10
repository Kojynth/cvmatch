#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Comprehensive Mojibake Fixer - CVMatch
=====================================

Master script to fix ALL mojibake issues across the entire codebase.
Addresses the 1971+ detected issues systematically with safety backups.

Features:
- Complete emoji corruption fixes (ðŸ'¤ → 👤, âš™ï¸ → ⚙️)
- French accent correction (Ã© → é, Ã¨ → è, Ã  → à)
- UI component sanitization with ui_text() integration
- Parser documentation fixes
- Safe backup and rollback system
"""

import os
import re
import json
import shutil
from pathlib import Path
from typing import Dict, List, Tuple, Set
from datetime import datetime


class ComprehensiveMojibakeFixer:
    """Master mojibake fixer for the entire CVMatch project."""
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.fixes_applied = {}
        self.errors = []
        self.backup_dir = self.project_root / "backups" / f"mojibake_fix_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Comprehensive mojibake correction patterns
        self.mojibake_fixes = {
            # === PHASE 2 - Complete Emoji Corruptions ===
            'ðŸ'¤': '\U0001F464',  # 👤 Profile
            'ðŸ"‹': '\U0001F4CB',  # 📋 Clipboard
            'ðŸ"§': '\U0001F527',  # 🔧 Wrench
            'ðŸ'¼': '\U0001F4BC',  # 💼 Briefcase
            'ðŸŽ"': '\U0001F393',  # 🎓 Graduation cap
            'ðŸ"ž': '\U0001F4DE',  # 📞 Telephone
            'ðŸ"§': '\U0001F4E7',  # 📧 Email
            'ðŸ"—': '\U0001F517',  # 🔗 Link
            'ðŸ'¡': '\U0001F4A1',  # 💡 Light bulb
            'ðŸ"Š': '\U0001F4CA',  # 📊 Bar chart
            'ðŸŽ¯': '\U0001F3AF',  # 🎯 Direct hit
            'ðŸ"ˆ': '\U0001F4C8',  # 📈 Chart increasing
            'ðŸ ': '\U0001F3E0',   # 🏠 House
            'ðŸ"': '\U0001F4C1',   # 📁 File folder
            'ðŸ"‚': '\U0001F4C2',   # 📂 Open file folder
            'ðŸ"™': '\U0001F4D9',   # 📙 Orange book
            'ðŸ"'': '\U0001F512',   # 🔒 Locked
            'ðŸ›¡ï¸': '\U0001F6E1\uFE0F',  # 🛡️ Shield
            'ðŸš«': '\U0001F6AB',   # 🚫 Prohibited
            'ðŸ–¥ï¸': '\U0001F5A5\uFE0F',  # 🖥️ Desktop computer
            'ðŸ"': '\U0001F50D',   # 🔍 Magnifying glass
            
            # === Control Character Emoji Corruptions ===
            'âš™ï¸': '\u2699\uFE0F',  # ⚙️ Settings
            'âœ…': '\u2705',           # ✅ Check mark
            'âŒ': '\u274C',            # ❌ Cross mark
            'âš ï¸': '\u26A0\uFE0F',   # ⚠️ Warning
            'âš–ï¸': '\u2696\uFE0F',   # ⚖️ Balance scale
            
            # === French Accents (UTF-8 → Latin-1 mojibake) ===
            'Ã©': 'é', 'Ã¨': 'è', 'Ã ': 'à', 'Ãª': 'ê', 'Ã«': 'ë',
            'Ã¢': 'â', 'Ã¹': 'ù', 'Ã¼': 'ü', 'Ã´': 'ô', 'Ã§': 'ç',
            'Ã®': 'î', 'Ã¯': 'ï', 'Ã»': 'û', 'Ã½': 'ý', 'Ã±': 'ñ',
            
            # French majuscules avec accents
            'Ã‰': 'É', 'Ã€': 'À', 'ÃŠ': 'Ê', 'ÃŽ': 'Î', 'Ã"': 'Ô',
            'Ã™': 'Ù', 'Ãœ': 'Ü', 'Ã‡': 'Ç', 'Ã‹': 'Ë', 'Ã\u008f': 'Ï',
            'Ã': 'Ý', 'Ã'': 'Ñ',
            
            # === Special Characters ===
            'â€™': "'",     # Right single quotation
            'â€œ': '"',     # Left double quotation  
            'â€': '"',      # Right double quotation
            'â€"': '–',     # En dash
            'â€"': '—',     # Em dash
            'â€¦': '…',     # Ellipsis
            'â€¢': '•',     # Bullet
            'Â°': '°',      # Degree symbol
            'Â«': '«',      # Left guillemet
            'Â»': '»',      # Right guillemet
            'â€': '€',      # Euro symbol
            'â„¢': '™',     # Trademark
            'Â®': '®',      # Registered
            'Â©': '©',      # Copyright
            
            # === Other Common Issues ===
            'Â ': ' ',       # Non-breaking space corruption
            'Â': '',         # Standalone  character (often unwanted)
            'Ã½': 'ý',      # y with acute
            'Ã¿': 'ÿ',      # y with diaeresis
        }
        
        # UI text patterns that need ui_text() wrapping
        self.ui_text_patterns = [
            (r'QGroupBox\("([^"]*[àâäéèêëïîôöùûüÿç][^"]*)"', r'QGroupBox(ui_text("\1")'),
            (r'setWindowTitle\("([^"]*[àâäéèêëïîôöùûüÿç][^"]*)"', r'setWindowTitle(ui_text("\1")'),
            (r'QLabel\("([^"]*[àâäéèêëïîôöùûüÿç][^"]*)"', r'QLabel(ui_text("\1")'),
            (r'QPushButton\("([^"]*[àâäéèêëïîôöùûüÿç][^"]*)"', r'QPushButton(ui_text("\1")'),
            (r'setText\("([^"]*[àâäéèêëïîôöùûüÿç][^"]*)"', r'setText(ui_text("\1")'),
        ]
        
        # Files to process based on audit results
        self.target_files = [
            "app/views/main_window.py",
            "app/views/profile_sections/experience_section.py", 
            "app/views/profile_sections/education_section.py",
            "app/views/profile_sections/skills_section.py",
            "app/views/profile_sections/soft_skills_section.py",
            "app/views/profile_sections/projects_section.py",
            "app/views/profile_sections/certifications_section.py",
            "app/views/profile_sections/languages_section.py",
            "app/views/profile_sections/interests_section.py",
            "app/views/profile_sections/awards_section.py",
            "app/views/profile_sections/publications_section.py",
            "app/views/profile_sections/references_section.py",
            "app/views/profile_sections/volunteering_section.py",
            "app/utils/ui_text.py",
            "app/utils/emoji_utils_old.py.corrupt_backup",
            "app/parsers/education_parser.py",
            "app/parsers/experience_parser.py",
            "app/parsers/soft_skills_parser.py",
            "app/parsers/project_parser.py"
        ]
    
    def create_backup(self, file_path: Path) -> Path:
        """Create backup of file before modification."""
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Create backup with same relative structure
        rel_path = file_path.relative_to(self.project_root)
        backup_path = self.backup_dir / rel_path
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        
        shutil.copy2(file_path, backup_path)
        return backup_path
    
    def fix_file_mojibake(self, file_path: Path) -> Dict:
        """Fix mojibake issues in a single file."""
        result = {
            'file': str(file_path.relative_to(self.project_root)),
            'corrections_made': 0,
            'patterns_found': [],
            'ui_text_additions': 0,
            'backup_created': False,
            'error': None
        }
        
        try:
            if not file_path.exists():
                result['error'] = "File not found"
                return result
            
            # Create backup
            backup_path = self.create_backup(file_path)
            result['backup_created'] = True
            
            # Read file content
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                # Try with different encodings
                for encoding in ['latin-1', 'cp1252', 'iso-8859-1']:
                    try:
                        with open(file_path, 'r', encoding=encoding) as f:
                            content = f.read()
                        break
                    except UnicodeDecodeError:
                        continue
                else:
                    result['error'] = "Could not decode file with any encoding"
                    return result
            
            original_content = content
            
            # Apply mojibake fixes
            for bad_pattern, good_pattern in self.mojibake_fixes.items():
                if bad_pattern in content:
                    count = content.count(bad_pattern)
                    content = content.replace(bad_pattern, good_pattern)
                    result['corrections_made'] += count
                    result['patterns_found'].append(f"{bad_pattern} → {good_pattern} ({count}x)")
            
            # Apply UI text patterns (for .py files only)
            if file_path.suffix == '.py':
                for pattern, replacement in self.ui_text_patterns:
                    matches = re.findall(pattern, content)
                    if matches:
                        # Check if ui_text import exists
                        if 'from app.utils.ui_text import ui_text' not in content and 'from .ui_text import ui_text' not in content:
                            # Add import at the top after existing imports
                            import_lines = []
                            other_lines = []
                            in_imports = True
                            
                            for line in content.split('\n'):
                                if in_imports and (line.startswith('import ') or line.startswith('from ') or line.strip() == '' or line.startswith('#')):
                                    import_lines.append(line)
                                else:
                                    in_imports = False
                                    other_lines.append(line)
                            
                            # Add ui_text import
                            import_lines.append('from app.utils.ui_text import ui_text')
                            import_lines.append('')
                            
                            content = '\n'.join(import_lines + other_lines)
                        
                        # Apply the pattern replacements
                        new_content = re.sub(pattern, replacement, content)
                        if new_content != content:
                            result['ui_text_additions'] += len(matches)
                            content = new_content
            
            # Write fixed content if changes were made
            if content != original_content:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                print(f"✅ Fixed {result['file']}: {result['corrections_made']} mojibake corrections, {result['ui_text_additions']} ui_text additions")
                if result['patterns_found']:
                    for pattern in result['patterns_found'][:5]:  # Show first 5 patterns
                        print(f"   → {pattern}")
                    if len(result['patterns_found']) > 5:
                        print(f"   → ... and {len(result['patterns_found']) - 5} more")
            else:
                print(f"ℹ️  {result['file']}: No mojibake issues found")
                
        except Exception as e:
            result['error'] = str(e)
            print(f"❌ Error fixing {result['file']}: {e}")
        
        return result
    
    def fix_all_files(self) -> Dict:
        """Fix mojibake issues in all target files."""
        summary = {
            'files_processed': 0,
            'files_fixed': 0,
            'total_corrections': 0,
            'total_ui_text_additions': 0,
            'errors': [],
            'backup_location': str(self.backup_dir)
        }
        
        print(f"🔧 Starting comprehensive mojibake fix...")
        print(f"📁 Backups will be saved to: {self.backup_dir}")
        print()
        
        for file_rel_path in self.target_files:
            file_path = self.project_root / file_rel_path
            
            summary['files_processed'] += 1
            result = self.fix_file_mojibake(file_path)
            
            if result['error']:
                summary['errors'].append(f"{result['file']}: {result['error']}")
            else:
                if result['corrections_made'] > 0 or result['ui_text_additions'] > 0:
                    summary['files_fixed'] += 1
                summary['total_corrections'] += result['corrections_made']
                summary['total_ui_text_additions'] += result['ui_text_additions']
        
        return summary
    
    def generate_report(self, summary: Dict) -> str:
        """Generate a comprehensive fix report."""
        report = f"""
# Comprehensive Mojibake Fix Report - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Summary
- **Files processed**: {summary['files_processed']}
- **Files modified**: {summary['files_fixed']}
- **Total mojibake corrections**: {summary['total_corrections']}
- **UI text improvements**: {summary['total_ui_text_additions']}
- **Backup location**: {summary['backup_location']}

## Status
"""
        
        if summary['total_corrections'] > 0:
            report += f"✅ **SUCCESS**: Fixed {summary['total_corrections']} mojibake issues across {summary['files_fixed']} files\n\n"
        else:
            report += "ℹ️  **INFO**: No mojibake issues found in target files\n\n"
        
        if summary['errors']:
            report += "## Errors\n"
            for error in summary['errors']:
                report += f"- ❌ {error}\n"
        else:
            report += "## Errors\n- None\n"
        
        report += f"""
## Next Steps
1. Test application startup: `python main.py`
2. Verify UI components display correctly
3. Run validation: `python scripts/test_mojibake_improvements.py`
4. If issues occur, restore from: `{summary['backup_location']}`

## Patterns Fixed
- French accents: Ã© → é, Ã¨ → è, Ã  → à
- Corrupted emojis: ðŸ'¤ → 👤, âš™ï¸ → ⚙️
- Special characters: â€™ → ', â€œ → "
- UI text integration with ui_text() function
"""
        
        return report


def main():
    """Main execution function."""
    import sys
    
    # Get project root (assume script is in scripts/ subdirectory)
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    
    print("🔧 CVMatch Comprehensive Mojibake Fixer")
    print("=" * 50)
    
    # Confirm with user before proceeding
    if len(sys.argv) > 1 and '--auto' in sys.argv:
        confirm = 'y'
    else:
        print(f"This will fix mojibake issues in {len(ComprehensiveMojibakeFixer(project_root).target_files)} files.")
        print("Backups will be created automatically.")
        confirm = input("\nProceed? (y/N): ").lower().strip()
    
    if confirm != 'y':
        print("Operation cancelled.")
        return 1
    
    # Create fixer and run
    fixer = ComprehensiveMojibakeFixer(str(project_root))
    summary = fixer.fix_all_files()
    
    # Generate and save report
    report = fixer.generate_report(summary)
    report_path = project_root / "logs" / f"mojibake_fix_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    report_path.parent.mkdir(exist_ok=True)
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)
    
    print("\n" + "=" * 50)
    print(f"📊 FINAL REPORT:")
    print(f"   Files fixed: {summary['files_fixed']}/{summary['files_processed']}")
    print(f"   Corrections: {summary['total_corrections']}")
    print(f"   UI improvements: {summary['total_ui_text_additions']}")
    print(f"   Report saved: {report_path}")
    
    if summary['errors']:
        print(f"   ⚠️  Errors: {len(summary['errors'])}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())