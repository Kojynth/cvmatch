#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validation script for UI emoji fixes - Safe Windows console output
"""

from pathlib import Path

def validate_main_window_fixes():
    """Validate that main UI emoji corruptions are fixed."""
    project_root = Path(__file__).parent.parent
    main_window_path = project_root / "app" / "views" / "main_window.py"
    
    if not main_window_path.exists():
        print("[ERROR] main_window.py not found")
        return False
    
    try:
        with open(main_window_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        print("UI EMOJI FIX VALIDATION")
        print("=" * 40)
        
        # Check for key fixes
        fixes_verified = []
        
        # Check sidebar navigation emojis
        if '("👤", "Profil", "profile")' in content:
            fixes_verified.append("Profile icon: 👤 FIXED")
        else:
            fixes_verified.append("Profile icon: STILL CORRUPTED")
        
        if '("📋", "Nouvelle candidature", "job_application")' in content:
            fixes_verified.append("Job app icon: 📋 FIXED")
        else:
            fixes_verified.append("Job app icon: STILL CORRUPTED")
        
        if '("📙", "Historique", "history")' in content:
            fixes_verified.append("History icon: 📙 FIXED")
        else:
            fixes_verified.append("History icon: STILL CORRUPTED")
        
        if '("⚙️", "Paramètres", "settings")' in content:
            fixes_verified.append("Settings icon: ⚙️ FIXED")
        else:
            fixes_verified.append("Settings icon: STILL CORRUPTED")
        
        # Check for remaining corruptions (using safe detection)
        remaining_issues = []
        
        # Check for corruption indicators without using the actual corrupted chars
        if 'ðŸ' in content:
            remaining_issues.append("Still contains corrupted emoji patterns")
        
        if 'â€' in content:
            remaining_issues.append("Still contains corrupted special chars")
        
        # Report results
        print("\nFIXES VERIFIED:")
        for fix in fixes_verified:
            status = "[OK]" if "FIXED" in fix else "[FAIL]"
            print(f"  {status} {fix}")
        
        print(f"\nREMAINING ISSUES: {len(remaining_issues)}")
        if remaining_issues:
            for issue in remaining_issues[:3]:  # Limit output
                print(f"  [WARN] {issue}")
            if len(remaining_issues) > 3:
                print(f"  ... and {len(remaining_issues) - 3} more")
        else:
            print("  [SUCCESS] No sidebar corruption detected!")
        
        # Overall status
        fixes_working = len([f for f in fixes_verified if "FIXED" in f])
        total_expected = 4  # Profile, New app, History, Settings
        
        success_rate = fixes_working / total_expected * 100
        print(f"\nOVERALL SUCCESS: {fixes_working}/{total_expected} ({success_rate:.0f}%)")
        
        if success_rate >= 75:
            print("[SUCCESS] Major UI emoji corruptions are fixed!")
            print("The sidebar should now display properly in the running app.")
            return True
        else:
            print("[PARTIAL] Some fixes applied, but more work needed.")
            return False
        
    except Exception as e:
        print(f"[ERROR] Validation failed: {e}")
        return False

def main():
    """Main validation entry point."""
    success = validate_main_window_fixes()
    
    if success:
        print("\n🎉 UI EMOJI FIXES VALIDATED!")
        print("✅ Main sidebar icons should display correctly")
        print("✅ Ready to test in running application")
    else:
        print("\n⚠️ VALIDATION INCOMPLETE")
        print("❌ Additional fixes may be needed")
    
    return 0 if success else 1

if __name__ == "__main__":
    exit(main())
