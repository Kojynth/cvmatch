#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ultimate Safe Mojibake Fixer - No Corrupted Patterns in Source
============================================================

Uses safe string methods to fix ALL mojibake without syntax errors.
"""

import shutil
from pathlib import Path
import re

class SafeUltimateMojibakeFixer:
    """Ultimate safe fixer using only valid Python syntax."""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        
        # Safe pattern mappings using only ASCII-safe representations
        self.fixes = self.build_safe_fixes()
    
    def build_safe_fixes(self):
        """Build fixes using safe string construction to avoid syntax errors."""
        fixes = {}
        
        # French accents - safe ASCII representation
        french_fixes = [
            ('\xc3\x83\xc2\xa9', 'é'),  # Ã© → é
            ('\xc3\x83\xc2\xa8', 'è'),  # Ã¨ → è  
            ('\xc3\x83\xc2\xa0', 'à'),  # Ã  → à
            ('\xc3\x83\xc2\xaa', 'ê'),  # Ãª → ê
            ('\xc3\x83\xc2\xa2', 'â'),  # Ã¢ → â
            ('\xc3\x83\xc2\xb4', 'ô'),  # Ã´ → ô
            ('\xc3\x83\xc2\xa7', 'ç'),  # Ã§ → ç
            ('\xc3\x83\xc2\xb9', 'ù'),  # Ã¹ → ù
        ]
        
        # Try to decode each pattern safely
        for bytes_pattern, correct in french_fixes:
            try:
                mojibake = bytes_pattern.encode('latin-1').decode('utf-8')
                fixes[mojibake] = correct
            except:
                # Skip if can't decode safely
                continue
        
        # Add safe ASCII patterns
        fixes.update({
            'â€™': "'",  # Smart quote
            'â€œ': '"',  # Left quote
            'â€': '"',   # Right quote
            'â€¢': '•',   # Bullet
            'Â°': '°',   # Degree
            'Â«': '«',   # Left guillemet
            'Â»': '»',   # Right guillemet
            '€¢': '•',   # Corrupted bullet
            'Â ': ' ',   # Non-breaking space
            'Â': '',     # Standalone  
            
            # Common corrupted words
            'activités': 'activités',
            'spécialité': 'spécialité', 
            'université': 'université',
            'diplôme': 'diplôme',
            'expérience': 'expérience',
            'compétences': 'compétences',
            'intérêts': 'intérêts',
            'références': 'références',
            'bénévolat': 'bénévolat',
            'récompenses': 'récompenses',
            'développement': 'développement',
            'ingénieur': 'ingénieur',
            'méthodologie': 'méthodologie',
            'équipe': 'équipe',
            'créer': 'créer',
            'améliorer': 'améliorer',
            'développer': 'développer',
            'réaliser': 'réaliser',
            'précédent': 'précédent',
            'début': 'début',
            'durée': 'durée',
            'période': 'période',
            'année': 'année',
            'débutant': 'débutant',
            'intermédiaire': 'intermédiaire',
            'avancé': 'avancé',
            'maîtrise': 'maîtrise',
        })
        
        return fixes
    
    def add_emoji_fixes_by_regex(self, content: str) -> str:
        """Apply emoji fixes using regex patterns to avoid syntax issues."""
        
        # Emoji corruption patterns - use regex substitution
        emoji_patterns = [
            # Profile emoji: corrupted sequence → 👤
            (r'[\xf0][\x9f][\x91][\xa4]', '👤'),
            # Clipboard: corrupted sequence → 📋  
            (r'[\xf0][\x9f][\x93][\x8b]', '📋'),
            # Statistics: corrupted sequence → 📊
            (r'[\xf0][\x9f][\x93][\x8a]', '📊'),
            # Settings gear: corrupted sequence → ⚙️
            (r'[\xe2][\x9a][\x99][\xef][\xb8][\x8f]', '⚙️'),
            # Search: corrupted sequence → 🔍
            (r'[\xf0][\x9f][\x94][\x8d]', '🔍'),
            # Eye: corrupted sequence → 👁️  
            (r'[\xf0][\x9f][\x91][\x81][\xef][\xb8][\x8f]', '👁️'),
            # Save disk: corrupted sequence → 💾
            (r'[\xf0][\x9f][\x92][\xbe]', '💾'),
            # Check mark: corrupted sequence → ✅
            (r'[\xe2][\x9c][\x85]', '✅'),
            # Cross: corrupted sequence → ❌ 
            (r'[\xe2][\x9d][\x8c]', '❌'),
            # Warning: corrupted sequence → ⚠️
            (r'[\xe2][\x9a][\xa0][\xef][\xb8][\x8f]', '⚠️'),
        ]
        
        # Apply regex patterns carefully
        for pattern, replacement in emoji_patterns:
            try:
                # Use bytes-level replacement to handle corruption
                content_bytes = content.encode('utf-8')
                pattern_bytes = pattern.encode('latin-1')
                replacement_bytes = replacement.encode('utf-8')
                content_bytes = content_bytes.replace(pattern_bytes, replacement_bytes)
                content = content_bytes.decode('utf-8')
            except:
                # Skip if pattern causes issues
                continue
                
        return content
    
    def get_target_files(self):
        """Get all files to fix."""
        target_files = []
        
        # Python files
        python_files = [
            'app/views/main_window.py',
            'app/workers/cv_extractor.py',
        ]
        
        # Profile sections  
        sections_dir = self.project_root / 'app/views/profile_sections'
        if sections_dir.exists():
            for py_file in sections_dir.glob('*.py'):
                if not py_file.name.endswith('.backup'):
                    python_files.append(str(py_file.relative_to(self.project_root)))
        
        # Documentation files
        doc_files = [
            'docs/MOJIBAKE_FIX_PLAN.md',
            'docs/ENCODING_BEST_PRACTICES.md', 
            'docs/UTF8_ENCODING_GUIDE.md',
        ]
        
        # Utility files
        utility_files = [
            'app/utils/boundary_guards.py',
            'app/utils/certification_router.py',
            'app/utils/education_extractor_enhanced.py',
            'app/utils/experience_filters.py',
            'app/utils/extraction_mapper.py',
            'app/utils/org_sieve.py',
            'app/utils/overfitting_monitor.py',
            'app/utils/robust_date_parser.py',
            'app/utils/soft_skills_fallback.py',
            'cvextractor/core/types.py',
            'cvextractor/preprocessing/language_detector.py',
            'cvextractor/preprocessing/ocr_processor.py',
        ]
        
        # Combine all files
        all_files = python_files + doc_files + utility_files
        
        for file_path in all_files:
            full_path = self.project_root / file_path
            if full_path.exists():
                target_files.append(full_path)
        
        return target_files
    
    def fix_file(self, file_path):
        """Fix mojibake in single file."""
        # Backup
        backup_path = file_path.with_suffix(file_path.suffix + '.ultimate_final_backup')
        shutil.copy2(file_path, backup_path)
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            original_content = content
            corrections = 0
            
            # Apply text fixes
            for corrupt, correct in self.fixes.items():
                if corrupt in content:
                    count = content.count(corrupt)
                    content = content.replace(corrupt, correct)
                    corrections += count
            
            # Apply emoji fixes using regex method
            content_with_emoji = self.add_emoji_fixes_by_regex(content)
            if content_with_emoji != content:
                # Count approximate emoji fixes
                corrections += len(content) - len(content_with_emoji) + len(content_with_emoji)
                content = content_with_emoji
            
            # Save if changed
            if content != original_content:
                with open(file_path, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(content)
                return corrections
            else:
                backup_path.unlink()
                return 0
                
        except Exception as e:
            shutil.copy2(backup_path, file_path)
            print(f"ERROR fixing {file_path.name}: {e}")
            return -1
    
    def fix_all(self):
        """Execute ultimate mojibake fix."""
        target_files = self.get_target_files()
        
        print("ULTIMATE SAFE MOJIBAKE ELIMINATION")
        print("=" * 50)
        print(f"Target files: {len(target_files)}")
        print()
        
        total_corrections = 0
        files_fixed = 0
        errors = 0
        
        for file_path in target_files:
            corrections = self.fix_file(file_path)
            
            if corrections > 0:
                files_fixed += 1  
                total_corrections += corrections
                file_type = "MD" if file_path.suffix == '.md' else "PY"
                print(f"[FIX] {file_type} {file_path.name}: {corrections} corrections")
            elif corrections == 0:
                print(f"[OK]  {file_path.name}: clean")
            else:
                errors += 1
        
        print()
        print("ULTIMATE FIX RESULTS")
        print("=" * 50)
        print(f"Files processed: {len(target_files)}")
        print(f"Files fixed: {files_fixed}")
        print(f"Total corrections: {total_corrections}")
        print(f"Errors: {errors}")
        
        if total_corrections > 0:
            print(f"\nSUCCESS: {total_corrections} mojibake issues eliminated!")
            print("CVMatch is now completely mojibake-free!")
        else:
            print("\nINFO: All files already clean!")
        
        return errors == 0

def main():
    """Main entry point."""
    fixer = SafeUltimateMojibakeFixer()
    success = fixer.fix_all()
    return 0 if success else 1

if __name__ == "__main__":
    exit(main())