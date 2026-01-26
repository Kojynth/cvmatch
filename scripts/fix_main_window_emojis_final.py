#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Final Main Window Emoji Fix - Target specific UI corruption
"""

import shutil
from pathlib import Path

def fix_main_window_final():
    """Fix remaining emoji corruption in main_window.py."""
    project_root = Path(__file__).parent.parent
    main_window_path = project_root / "app" / "views" / "main_window.py"
    
    if not main_window_path.exists():
        print("[ERROR] main_window.py not found")
        return False
    
    # Create backup
    backup_path = main_window_path.with_suffix('.py.final_emoji_backup')
    shutil.copy2(main_window_path, backup_path)
    print(f"[BACKUP] Created: {backup_path.name}")
    
    try:
        # Read file
        with open(main_window_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Use bytes-level replacement to handle corrupted patterns
        content_bytes = content.encode('utf-8')
        
        # Define byte-level replacements for corrupted emojis
        byte_fixes = [
            # Eye emoji corruption
            (b'\\xf0\\x9f\\x91\\x81\\xef\\xb8\\x8f', '👁️'.encode('utf-8')),
            # Document/page corruption  
            (b'\\xf0\\x9f\\x93\\x84', '🔄'.encode('utf-8')),
            # Link corruption
            (b'\\xf0\\x9f\\x94\\x97', '🔗'.encode('utf-8')),
            # Save corruption
            (b'\\xf0\\x9f\\x92\\xbe', '💾'.encode('utf-8')),
            # Phone corruption
            (b'\\xf0\\x9f\\x93\\x9e', '📞'.encode('utf-8')),
            # Bullet corruption
            (b'\\xe2\\x82\\xac\\xc2\\xa2', '•'.encode('utf-8')),
        ]
        
        corrections = 0
        
        # Apply byte-level fixes
        for old_bytes, new_bytes in byte_fixes:
            if old_bytes in content_bytes:
                count = content_bytes.count(old_bytes)
                content_bytes = content_bytes.replace(old_bytes, new_bytes)
                corrections += count
                print(f"[FIX] Fixed {count} byte-level emoji corruptions")
        
        # Convert back to string
        try:
            content = content_bytes.decode('utf-8')
        except:
            print("[ERROR] Could not decode fixed content")
            return False
        
        # Apply string-level fixes for patterns we can handle safely
        string_fixes = {
            # Safe patterns only
            '€¢': '•',    # Bullet point
            '• •': '•',   # Double bullets
        }
        
        for old, new in string_fixes.items():
            if old in content:
                count = content.count(old)
                content = content.replace(old, new)
                corrections += count
                print(f"[FIX] Fixed {count}x '{old}' -> '{new}'")
        
        # Save if changes made
        if content != original_content:
            with open(main_window_path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(content)
            print(f"[SUCCESS] Applied {corrections} corrections to main_window.py")
        else:
            print("[INFO] No corrections needed")
            # Remove unnecessary backup
            backup_path.unlink()
        
        return True
        
    except Exception as e:
        print(f"[ERROR] {e}")
        # Restore backup
        if backup_path.exists():
            shutil.copy2(backup_path, main_window_path)
            print("[RESTORE] Restored from backup")
        return False

if __name__ == "__main__":
    success = fix_main_window_final()
    exit(0 if success else 1)