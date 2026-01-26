#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Final comprehensive mojibake fixer - handles all identified files safely.
Works around Windows console encoding issues.
"""

import shutil
from pathlib import Path
import re

class SafeMojibakeFixer:
    """Safe mojibake fixer that avoids syntax errors."""
    
    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        
        # Safe pattern mappings using only valid Python syntax
        self.fixes = {
            # French accents
            'Ã©': 'é', 'Ã¨': 'è', 'Ã ': 'à', 'Ãª': 'ê', 'Ã«': 'ë',
            'Ã¢': 'â', 'Ã¹': 'ù', 'Ã¼': 'ü', 'Ã´': 'ô', 'Ã§': 'ç',
            'Ã®': 'î', 'Ã¯': 'ï', 'Ã»': 'û',
            'Ã‰': 'É', 'Ã€': 'À', 'ÃŠ': 'Ê', 'ÃŽ': 'Î', 'Ã"': 'Ô',
            'Ã™': 'Ù', 'Ãœ': 'Ü', 'Ã‡': 'Ç', 'Ã‹': 'Ë',
            
            # Special characters
            'â€™': "'", 'â€œ': '"', 'â€': '"', 'â€"': '–', 'â€"': '—',
            'â€¦': '…', 'â€¢': '•', 'Â°': '°', 'Â«': '«', 'Â»': '»',
            'â€': '€', 'â„¢': '™', 'Â®': '®', 'Â©': '©',
            'Â ': ' ', 'Â': '',
            
            # Common corrupted words
            'activitÃ©s': 'activités',
            'spÃ©cialitÃ©': 'spécialité',
            'universitÃ©': 'université',
            'diplÃ´me': 'diplôme',
            'expÃ©rience': 'expérience',
            'compÃ©tences': 'compétences',
            'intÃ©rÃªts': 'intérêts',
            'rÃ©fÃ©rences': 'références',
            'bÃ©nÃ©volat': 'bénévolat',
            'rÃ©compenses': 'récompenses',
            'dÃ©veloppement': 'développement',
            'ingÃ©nieur': 'ingénieur',
            'mÃ©thodologie': 'méthodologie',
            'Ã©quipe': 'équipe',
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
        }
    
    def get_target_files(self):
        """Get all files that need fixing."""
        target_files = []
        
        # Main UI files
        main_files = [
            'app/views/main_window.py',
            'app/workers/cv_extractor.py',
        ]
        
        # Profile sections (all 11 files with issues)
        profile_sections = [
            'app/views/profile_sections/education_section.py',
            'app/views/profile_sections/soft_skills_section.py',
            'app/views/profile_sections/experience_section.py',
            'app/views/profile_sections/volunteering_section.py',
            'app/views/profile_sections/references_section.py',
            'app/views/profile_sections/publications_section.py',
            'app/views/profile_sections/projects_section.py',
            'app/views/profile_sections/languages_section.py',
            'app/views/profile_sections/interests_section.py',
            'app/views/profile_sections/certifications_section.py',
            'app/views/profile_sections/awards_section.py',
            'app/views/profile_sections/personal_info_section.py',
            'app/views/profile_sections/skills_section.py',
            'app/views/profile_sections/base_section.py',
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
        
        all_files = main_files + profile_sections + utility_files
        
        for file_path in all_files:
            full_path = self.project_root / file_path
            if full_path.exists():
                target_files.append(full_path)
        
        return target_files
    
    def fix_file(self, file_path):
        """Fix mojibake in a single file."""
        # Create backup
        backup_path = file_path.with_suffix(file_path.suffix + '.final_backup')
        shutil.copy2(file_path, backup_path)
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            original_content = content
            corrections = 0
            
            # Apply all fixes
            for corrupt, correct in self.fixes.items():
                if corrupt in content:
                    count = content.count(corrupt)
                    content = content.replace(corrupt, correct)
                    corrections += count
            
            # Save if changed
            if content != original_content:
                with open(file_path, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(content)
                return corrections
            else:
                # Remove unnecessary backup
                backup_path.unlink()
                return 0
                
        except Exception as e:
            # Restore backup on error
            shutil.copy2(backup_path, file_path)
            print(f"ERROR fixing {file_path.name}: {e}")
            return -1
    
    def fix_all(self):
        """Fix all target files."""
        target_files = self.get_target_files()
        
        print("COMPREHENSIVE MOJIBAKE FIX - CVMATCH")
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
                print(f"[FIX] {file_path.name}: {corrections} corrections")
            elif corrections == 0:
                print(f"[OK]  {file_path.name}: no fixes needed")
            else:
                errors += 1
        
        print()
        print("FINAL REPORT")
        print("=" * 50)
        print(f"Files processed: {len(target_files)}")
        print(f"Files fixed: {files_fixed}")
        print(f"Total corrections: {total_corrections}")
        print(f"Errors: {errors}")
        
        if total_corrections > 0:
            print(f"\n[SUCCESS] {total_corrections} mojibake issues fixed across {files_fixed} files!")
        else:
            print("\n[INFO] No mojibake issues found - all files clean!")
        
        return errors == 0

def main():
    """Main entry point."""
    fixer = SafeMojibakeFixer()
    success = fixer.fix_all()
    return 0 if success else 1

if __name__ == "__main__":
    exit(main())