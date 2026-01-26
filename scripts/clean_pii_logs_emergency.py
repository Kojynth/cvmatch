#!/usr/bin/env python3
"""
EMERGENCY PII LOG CLEANER
========================

Script d'urgence pour nettoyer tous les logs contenant des données PII visibles.
À exécuter IMMÉDIATEMENT après la correction du système PII.
"""

import os
import shutil
from pathlib import Path
import re
from datetime import datetime

def find_logs_with_pii():
    """Trouve tous les fichiers de logs contenant potentiellement du PII."""
    log_dirs = [
        Path("logs"),
        Path("runtime/logs") if Path("runtime/logs").exists() else None,
    ]
    
    log_files = []
    for log_dir in filter(None, log_dirs):
        if log_dir.exists():
            # Tous les logs d'extraction
            log_files.extend(log_dir.glob("extraction/*.log"))
            log_files.extend(log_dir.glob("extraction/*.pii_backup*"))
            
            # Logs principaux potentiellement compromis
            for pattern in ["*.log", "*.pii_backup*"]:
                log_files.extend(log_dir.glob(pattern))
    
    return log_files

def contains_visible_pii(file_path):
    """Vérifie si un fichier contient du PII visible (non redacté)."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read(10000)  # Premier 10KB suffisent
        
        # Patterns de détection PII visible
        patterns = [
            r'\b[A-Z][a-z]{2,}\s+[A-Z][a-z]{2,}\b',  # Noms complets "Prénom Nom"
            r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b',  # Emails complets
            r'\b(?:\+33|0)[1-9][\s.-]?\d{2}[\s.-]?\d{2}[\s.-]?\d{2}[\s.-]?\d{2}\b',  # Téléphones français
            r'\b\d{1,5}\s+(?:rue|avenue|boulevard|place|chemin)\s+[A-Za-z\s]+\b',  # Adresses
            r'né le|born on|\d{1,2}/\d{1,2}/\d{4}',  # Dates de naissance
        ]
        
        for pattern in patterns:
            if re.search(pattern, content, re.IGNORECASE):
                # Vérifier que ce n'est pas déjà redacté
                matches = re.findall(pattern, content, re.IGNORECASE)
                for match in matches[:3]:  # Vérifier les 3 premières occurrences
                    if '[PII-' not in str(match) and not match.lower().startswith('extraction'):
                        return True, f"Pattern trouvé: {pattern} -> {match}"
        
        return False, ""
        
    except Exception as e:
        print(f"Erreur lecture {file_path}: {e}")
        return False, f"Erreur: {e}"

def backup_and_clean_logs():
    """Sauvegarde et nettoie les logs compromis."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = Path(f"logs_backup_pii_cleanup_{timestamp}")
    backup_dir.mkdir(exist_ok=True)
    
    log_files = find_logs_with_pii()
    compromised_files = []
    clean_files = []
    
    print(f"[SCAN] Analyse de {len(log_files)} fichiers de logs...")
    
    for log_file in log_files:
        if not log_file.exists():
            continue
            
        has_pii, details = contains_visible_pii(log_file)
        
        if has_pii:
            print(f"[WARNING] PII detecte dans {log_file}")
            print(f"   Details: {details}")
            
            # Sauvegarder avant suppression
            backup_file = backup_dir / log_file.name
            try:
                shutil.copy2(log_file, backup_file)
                print(f"   [OK] Sauvegarde vers {backup_file}")
                
                # Supprimer le fichier compromis
                log_file.unlink()
                print(f"   [DELETE] Fichier supprime: {log_file}")
                
                compromised_files.append(str(log_file))
                
            except Exception as e:
                print(f"   [ERROR] Erreur sauvegarde/suppression: {e}")
        else:
            clean_files.append(str(log_file))
    
    # Rapport final
    print("\n" + "="*60)
    print("RAPPORT DE NETTOYAGE PII")
    print("="*60)
    print(f"[OK] Fichiers propres: {len(clean_files)}")
    print(f"[WARNING] Fichiers compromis supprimes: {len(compromised_files)}")
    print(f"[BACKUP] Sauvegarde dans: {backup_dir}")
    
    if compromised_files:
        print("\n[DELETE] Fichiers supprimes:")
        for f in compromised_files:
            print(f"   - {f}")
    
    print(f"\n[COMPLETE] Nettoyage termine a {datetime.now()}")

if __name__ == "__main__":
    print("NETTOYAGE D'URGENCE DES LOGS PII")
    print("="*50)
    print("ATTENTION: Ce script va supprimer tous les logs contenant du PII visible")
    print("INFO: Les fichiers seront sauvegardes avant suppression")
    
    response = input("\n> Continuer? (oui/non): ").lower()
    if response in ['oui', 'o', 'yes', 'y']:
        backup_and_clean_logs()
        print("\n[SUCCESS] Nettoyage termine avec succes!")
    else:
        print("[CANCEL] Nettoyage annule.")
