#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script pour corriger spécifiquement les problèmes mojibake dans main_window.py
"""

import shutil
from pathlib import Path

def fix_main_window_mojibake():
    """Corrige les problèmes mojibake dans main_window.py."""
    project_root = Path(__file__).parent.parent
    main_window_path = project_root / "app" / "views" / "main_window.py"
    
    if not main_window_path.exists():
        print(f"[ERROR] Fichier non trouvé: {main_window_path}")
        return False
    
    # Backup du fichier original
    backup_path = main_window_path.with_suffix('.py.mojibake_backup')
    shutil.copy2(main_window_path, backup_path)
    print(f"[BACKUP] Sauvegarde créée: {backup_path}")
    
    # Mapping complet des corrections mojibake
    fixes = {
        # Accents français corrompus
        'Ã©': 'é',  'Ã¨': 'è',  'Ã ': 'à',  'Ãª': 'ê',  'Ã«': 'ë',
        'Ã¢': 'â',  'Ã¹': 'ù',  'Ã¼': 'ü',  'Ã´': 'ô',  'Ã§': 'ç',
        'Ã®': 'î',  'Ã¯': 'ï',  'Ã»': 'û',
        # Majuscules avec accents
        'Ã‰': 'É',  'Ã€': 'À',  'ÃŠ': 'Ê',  'ÃŽ': 'Î',  'Ã"': 'Ô',
        'Ã™': 'Ù',  'Ãœ': 'Ü',  'Ã‡': 'Ç',  'Ã‹': 'Ë',
        
        # Patterns spécifiques trouvés dans main_window.py
        'refactorisÃ©e': 'refactorisée',
        'sÃ©curisÃ©': 'sécurisé', 
        'systÃ¨me': 'système',
        'zÃ©ro': 'zéro',
        'personnalisÃ©': 'personnalisé',
        'PremiÃ¨re': 'Première',
        'immÃ©diatement': 'immédiatement',
        'gÃ©nÃ©rÃ©s': 'générés',
        'ModÃ¨le': 'Modèle',
        'sÃ©lectionner': 'sélectionner',
        'DÃ©sÃ©lectionner': 'Désélectionner',
        'tÃ©lÃ©phone': 'téléphone',
        'sÃ©lecteur': 'sélecteur',
        'TÃ©lÃ©phone': 'Téléphone',
        'donnÃ©es': 'données',
        'automatiquement': 'automatiquement',
        'maÃ®tre': 'maître',
        'rÃ©fÃ©rence': 'référence',
        'dÃ©tails': 'détails',
        'uniformisÃ©': 'uniformisé',
        'toujours': 'toujours',
        'dÃ©sactivÃ©': 'désactivé',
        'affichÃ©': 'affiché',
        'privÃ©': 'privé',
        'rÃ©cupÃ©rÃ©es': 'récupérées',
        'synchronisÃ©': 'synchronisé',
        'synchronisÃ©e': 'synchronisée',
        'PrÃªt': 'Prêt',
        'renseignÃ©e': 'renseignée',
        'PrÃ©fÃ©rences': 'Préférences',
        'prÃ©fÃ©rÃ©': 'préféré',
        'dÃ©faut': 'défaut',
        'adaptÃ©e': 'adaptée',
        'pertinente': 'pertinente',
        'caractÃ¨res': 'caractères',
        'prÃ©visualisation': 'prévisualisation',
        'PrÃ©visualiser': 'Prévisualiser',
        'validÃ©s': 'validés',
        'RÃ©entraÃ®ner': 'Réentraîner',
        'modÃ¨le': 'modèle',
        'rÃ©fÃ©rences': 'références',
        'dÃ©sactiver': 'désactiver',
        'aprÃ¨s': 'après',
        'crÃ©ation': 'création',
        'systÃ¨me': 'système',
        'SÃ©lectionner': 'Sélectionner',
        'supportÃ©s': 'supportés',
        'succÃ¨s': 'succès',
        'RÃ©entraÃ®nement': 'Réentraînement',
        'arriÃ¨re-plan': 'arrière-plan',
        'lancÃ©': 'lancé',
        'SuccÃ¨s': 'Succès',
        'sauvegardÃ©': 'sauvegardé',
        'Ã©tat': 'état',
        'RÃ©initialiser': 'Réinitialiser',
        'prÃ©fÃ©rences': 'préférences',
        'dÃ©clenchÃ©e': 'déclenchée',
        'mÃªme': 'même',
        'RÃ©cupÃ©rer': 'Récupérer',
        'numÃ©ro': 'numéro',
        'tÃ©lÃ©phone': 'téléphone',
        'RafraÃ®chir': 'Rafraîchir',
        'Ã‰mettre': 'Émettre',
        'rÃ©ussie': 'réussie',
        'dÃ©clenchÃ©e': 'déclenchée',
        'mÃ©thode': 'méthode',
        'trouvÃ©': 'trouvé',
        'opÃ©ration': 'opération',
        'Ã  nouveau': 'à nouveau',
        
        # Caractères spéciaux corrompus  
        'â€™': "'",  'â€œ': '"',  'â€': '"',  'â€"': '–',  'â€"': '—',
        'â€¦': '…',  'â€¢': '•',  'â€ ': ' ',
        
        # Emojis corrompus utilisant des escapes Unicode valides
        'ðŸ'¤': '👤',   # Profil utilisateur
        'ðŸ"‹': '📋',   # Presse-papier  
        'ðŸ"™': '📙',   # Livre orange
        'âš™ï¸': '⚙️',  # Engrenage
        'ðŸ"Š': '📊',   # Graphique barres
        'ðŸ"': '🔍',    # Loupe
        'ðŸ"Ž': '🔎',    # Loupe droite
        'ðŸ'ï¸': '👁️',  # Oeil
        'ðŸ"': '📁',    # Dossier
        'ðŸ"—': '🔗',    # Lien
        'âš ï¸': '⚠️',  # Attention
        'âœ…': '✅',    # Case cochée
        'ðŸ"„': '🔄',    # Flèches circulaires
        'ðŸ'¾': '💾',    # Disquette
        'ðŸ"': '📄',    # Page
        'ðŸ'ï¸': '👁️',  # Oeil
        'ðŸ"ž': '📞',    # Téléphone
        'ðŸ'¼': '💼',    # Mallette
        'ðŸŽ"': '🎓',    # Chapeau diplômé
        'â„¹ï¸': 'ℹ️',   # Information
    }
    
    try:
        # Lire le fichier avec UTF-8
        with open(main_window_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Appliquer les corrections
        corrections_made = 0
        for mojibake, correct in fixes.items():
            if mojibake in content:
                count_before = content.count(mojibake)
                content = content.replace(mojibake, correct)
                corrections_made += count_before
                if count_before > 0:
                    print(f"[FIX] Remplacé {count_before}x '{mojibake}' → '{correct}'")
        
        # Sauvegarder le fichier corrigé
        if corrections_made > 0:
            with open(main_window_path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(content)
            print(f"[SUCCESS] {corrections_made} corrections appliquées dans main_window.py")
        else:
            print("[INFO] Aucune correction nécessaire dans main_window.py")
        
        return True
        
    except Exception as e:
        print(f"[ERROR] Erreur lors de la correction: {e}")
        # Restaurer depuis le backup en cas d'erreur
        if backup_path.exists():
            shutil.copy2(backup_path, main_window_path)
            print("[RESTORE] Fichier original restauré depuis la sauvegarde")
        return False

if __name__ == "__main__":
    success = fix_main_window_mojibake()
    exit(0 if success else 1)