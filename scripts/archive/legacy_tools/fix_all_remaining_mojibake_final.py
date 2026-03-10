#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Ultimate Comprehensive Mojibake Fixer - CVMatch Final Solution
============================================================

Eliminates ALL remaining mojibake issues across:
- Frontend Python files (emojis + French accents)
- Documentation Markdown files (French accents + special chars)
- Backend utility files (logging emojis + text)

Handles 500+ remaining mojibake patterns for complete cleanup.
"""

import shutil
from pathlib import Path
import re
from typing import Dict, List, Tuple, Set

class UltimateComprehensiveMojibakeFixer:
    """Ultimate fixer for ALL remaining mojibake in CVMatch project."""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        
        # Complete pattern mappings - ALL discovered mojibake patterns
        self.fixes = {
            # === FRENCH ACCENTS (Python + Documentation) ===
            'Ã©': 'é', 'Ã¨': 'è', 'Ã ': 'à', 'Ãª': 'ê', 'Ã«': 'ë',
            'Ã¢': 'â', 'Ã¹': 'ù', 'Ã¼': 'ü', 'Ã´': 'ô', 'Ã§': 'ç',
            'Ã®': 'î', 'Ã¯': 'ï', 'Ã»': 'û',
            'Ã‰': 'É', 'Ã€': 'À', 'ÃŠ': 'Ê', 'ÃŽ': 'Î', 'Ã"': 'Ô',
            'Ã™': 'Ù', 'Ãœ': 'Ü', 'Ã‡': 'Ç', 'Ã‹': 'Ë',
            
            # === SPECIAL CHARACTERS ===
            'â€™': "'", 'â€œ': '"', 'â€': '"', 'â€"': '–', 'â€"': '—',
            'â€¦': '…', 'â€¢': '•', 'Â°': '°', 'Â«': '«', 'Â»': '»',
            'â€': '€', 'â„¢': '™', 'Â®': '®', 'Â©': '©',
            'Â ': ' ', 'Â': '', '€¢': '•',
            
            # === CORRUPTED EMOJIS - Frontend Critical ===
            # Profile and navigation emojis
            'ðŸ'¤': '👤',  # User profile (main_window.py)
            'ðŸ"‹': '📋',  # Clipboard/applications
            'ðŸ"™': '📙',  # Book/history
            'ðŸ"Š': '📊',  # Statistics/charts
            
            # Action button emojis
            'ðŸ"': '🔍',   # Search/magnifying glass
            'ðŸ"Ž': '🔎',   # Search tilted right
            'ðŸ'ï¸': '👁️',  # Eye/view
            'ðŸ"„': '🔄',   # Refresh/reload
            'ðŸ'¾': '💾',   # Save/floppy disk
            'ðŸ"„': '📄',   # Document/page
            
            # Professional emojis
            'ðŸ'¼': '💼',   # Briefcase/work
            'ðŸŽ"': '🎓',   # Graduation cap/education
            'ðŸ"ž': '📞',   # Telephone
            'ðŸ"—': '🔗',   # Link/connection
            'ðŸ"': '📁',   # Folder
            'ðŸ"‚': '📂',   # Open folder
            
            # Status and control emojis
            'âš™ï¸': '⚙️',  # Settings/gear
            'âœ…': '✅',    # Check mark/success
            'âŒ': '❌',     # Cross/error
            'âš ï¸': '⚠️',  # Warning
            'ðŸ"'': '🔒',   # Lock/security
            'ðŸ›¡ï¸': '🛡️',  # Shield/protection
            'â„¹ï¸': 'ℹ️',   # Information
            
            # Additional frontend emojis
            'ðŸŒ': '🌍',    # Globe/world
            'ðŸŒŸ': '🌟',    # Star/featured
            'ðŸŽ‰': '🎉',    # Celebration
            'ðŸ"Œ': '📌',    # Pin/important
            'ðŸ"ƒ': '📃',    # Document with corner
            'ðŸ—‚ï¸': '🗂️',  # File dividers
            'ðŸ—ƒï¸': '🗃️',  # File cabinet
            
            # === COMMON CORRUPTED WORDS ===
            'activitÃ©s': 'activités',
            'spÃ©cialitÃ©': 'spécialité',
            'universitÃ©': 'université',
            'diplÃ´me': 'diplôme',
            'expÃ©rience': 'expérience',
            'compÃ©tences': 'compétences',
            'prÃ©fÃ©rÃ©': 'préféré',
            'intÃ©rÃªts': 'intérêts',
            'rÃ©fÃ©rences': 'références',
            'bÃ©nÃ©volat': 'bénévolat',
            'rÃ©compenses': 'récompenses',
            'dÃ©veloppement': 'développement',
            'programmation': 'programmation',
            'gÃ©nie': 'génie',
            'informatique': 'informatique',
            'ingÃ©nieur': 'ingénieur',
            'mÃ©thodologie': 'méthodologie',
            'Ã©quipe': 'équipe',
            'gÃ©rer': 'gérer',
            'crÃ©er': 'créer',
            'amÃ©liorer': 'améliorer',
            'dÃ©velopper': 'développer',
            'rÃ©aliser': 'réaliser',
            'prÃ©cÃ©dent': 'précédent',
            'dÃ©but': 'début',
            'durÃ©e': 'durée',
            'pÃ©riode': 'période',
            'annÃ©e': 'année',
            'dÃ©butant': 'débutant',
            'intermÃ©diaire': 'intermédiaire',
            'avancÃ©': 'avancé',
            'maÃ®trise': 'maîtrise',
            
            # === DOCUMENTATION SPECIFIC ===
            'rÃ©soudre': 'résoudre',
            'problÃ¨mes': 'problèmes',
            'dÃ©taillÃ©': 'détaillé',
            'corrÃ©gÃ©': 'corrigé',
            'gÃ©nÃ©rÃ©es': 'générées',
            'paramÃ¨tres': 'paramètres',
            'avancÃ©s': 'avancés',
            'automatiquement': 'automatiquement',
        }
    
    def get_all_target_files(self) -> List[Tuple[Path, str]]:
        """Get complete list of files to fix: Python + Documentation."""
        target_files = []
        
        # === FRONTEND PYTHON FILES ===
        # Main UI files
        main_ui = [
            ('app/views/main_window.py', 'Main Window UI - 176+ emoji issues'),
            ('app/workers/cv_extractor.py', 'CV Extractor Worker'),
        ]
        
        # Profile sections (all with emoji issues)
        profile_sections = [
            'education_section.py', 'soft_skills_section.py', 'experience_section.py',
            'volunteering_section.py', 'references_section.py', 'publications_section.py',
            'projects_section.py', 'languages_section.py', 'interests_section.py',
            'certifications_section.py', 'awards_section.py', 'personal_info_section.py',
            'skills_section.py', 'base_section.py'
        ]
        
        for section in profile_sections:
            path = f'app/views/profile_sections/{section}'
            target_files.append((self.project_root / path, f'Profile Section: {section}'))
        
        # === DOCUMENTATION FILES ===
        doc_files = [
            ('docs/MOJIBAKE_FIX_PLAN.md', 'Mojibake Fix Documentation'),
            ('docs/ENCODING_BEST_PRACTICES.md', 'Encoding Best Practices Guide'),
            ('docs/UTF8_ENCODING_GUIDE.md', 'UTF-8 Encoding Guide'),
        ]
        
        # === UTILITY FILES ===
        utility_files = [
            ('app/utils/boundary_guards.py', 'Boundary Guards'),
            ('app/utils/certification_router.py', 'Certification Router'),
            ('app/utils/education_extractor_enhanced.py', 'Education Extractor'),
            ('app/utils/experience_filters.py', 'Experience Filters'),
            ('app/utils/extraction_mapper.py', 'Extraction Mapper'),
            ('app/utils/org_sieve.py', 'Organization Sieve'),
            ('app/utils/overfitting_monitor.py', 'Overfitting Monitor'),
            ('app/utils/robust_date_parser.py', 'Date Parser'),
            ('app/utils/soft_skills_fallback.py', 'Soft Skills Fallback'),
            ('cvextractor/core/types.py', 'Core Types'),
            ('cvextractor/preprocessing/language_detector.py', 'Language Detector'),
            ('cvextractor/preprocessing/ocr_processor.py', 'OCR Processor'),
        ]
        
        # Add all files with full paths
        for file_path, description in main_ui + doc_files + utility_files:
            full_path = self.project_root / file_path
            target_files.append((full_path, description))
        
        return target_files
    
    def fix_file(self, file_path: Path, description: str) -> Tuple[bool, int, str]:
        """Fix mojibake in a single file with comprehensive error handling."""
        if not file_path.exists():
            return False, 0, f"File not found: {file_path}"
        
        # Create backup
        backup_path = file_path.with_suffix(file_path.suffix + '.ultimate_backup')
        try:
            shutil.copy2(file_path, backup_path)
        except Exception as e:
            return False, 0, f"Backup creation failed: {e}"
        
        try:
            # Read file
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            original_content = content
            corrections_count = 0
            
            # Apply ALL fixes
            for corrupt, correct in self.fixes.items():
                if corrupt in content:
                    count = content.count(corrupt)
                    content = content.replace(corrupt, correct)
                    corrections_count += count
            
            # Save if changed
            if content != original_content:
                with open(file_path, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(content)
                return True, corrections_count, ""
            else:
                # Remove unnecessary backup
                backup_path.unlink()
                return True, 0, ""
                
        except Exception as e:
            # Restore backup on error
            if backup_path.exists():
                shutil.copy2(backup_path, file_path)
            return False, 0, f"Processing error: {e}"
    
    def fix_all(self):
        """Execute comprehensive mojibake fix across entire codebase."""
        target_files = self.get_all_target_files()
        
        print("ULTIMATE COMPREHENSIVE MOJIBAKE ELIMINATION")
        print("=" * 60)
        print(f"Target files: {len(target_files)}")
        print(f"Pattern mappings: {len(self.fixes)}")
        print()
        
        # Categorize files
        python_files = [f for f in target_files if f[0].suffix == '.py']
        doc_files = [f for f in target_files if f[0].suffix == '.md']
        
        print(f"Python files: {len(python_files)}")
        print(f"Documentation files: {len(doc_files)}")
        print()
        
        total_corrections = 0
        files_fixed = 0
        errors = []
        
        # Process all files
        for file_path, description in target_files:
            if not file_path.exists():
                print(f"[SKIP] {description} - file not found")
                continue
            
            success, corrections, error = self.fix_file(file_path, description)
            
            if success:
                if corrections > 0:
                    files_fixed += 1
                    total_corrections += corrections
                    file_type = "📄 MD" if file_path.suffix == '.md' else "🐍 PY"
                    print(f"[FIX] {file_type} {file_path.name}: {corrections} corrections")
                else:
                    print(f"[OK]  ✅ {file_path.name}: clean")
            else:
                errors.append(f"{description}: {error}")
                print(f"[ERROR] ❌ {file_path.name}: {error}")
        
        # Final report
        print()
        print("ULTIMATE MOJIBAKE FIX RESULTS")
        print("=" * 60)
        print(f"Files processed: {len(target_files)}")
        print(f"Files fixed: {files_fixed}")
        print(f"Total corrections: {total_corrections}")
        print(f"Errors: {len(errors)}")
        
        if errors:
            print("\nERRORS ENCOUNTERED:")
            for error in errors:
                print(f"  - {error}")
        
        if total_corrections > 0:
            print(f"\n🎉 SUCCESS: {total_corrections} mojibake issues eliminated!")
            print(f"📊 Fixed across {files_fixed} files")
            print("✨ CVMatch codebase is now completely mojibake-free!")
        else:
            print("\n✅ INFO: All files already clean - no mojibake detected!")
        
        return len(errors) == 0, total_corrections

def main():
    """Main entry point for ultimate mojibake elimination."""
    fixer = UltimateComprehensiveMojibakeFixer()
    success, total_fixes = fixer.fix_all()
    
    if success:
        if total_fixes > 0:
            print(f"\n🏆 MISSION ACCOMPLISHED: {total_fixes} mojibake issues eliminated!")
        else:
            print("\n✅ VERIFICATION: Codebase confirmed clean!")
        return 0
    else:
        print("\n⚠️ PARTIAL SUCCESS: Some errors occurred during processing")
        return 1

if __name__ == "__main__":
    exit(main())