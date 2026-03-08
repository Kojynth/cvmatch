#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de correction automatisée des problèmes mojibake détectés par l'audit.
"""

import json
import shutil
from pathlib import Path
from typing import Dict, List

class MojibakeFixer:
    """Correcteur automatisé pour les problèmes mojibake."""
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        
        # Mapping des corrections mojibake (UTF-8 décodé comme Latin-1)
        self.fixes = {
            # Accents français
            'Ã©': 'é',  'Ã¨': 'è',  'Ã ': 'à',  'Ãª': 'ê',  'Ã«': 'ë',
            'Ã¢': 'â',  'Ã¹': 'ù',  'Ã¼': 'ü',  'Ã´': 'ô',  'Ã§': 'ç',
            'Ã®': 'î',  'Ã¯': 'ï',  'Ã»': 'û',
            # Majuscules avec accents
            'Ã‰': 'É',  'Ã€': 'À',  'ÃŠ': 'Ê',  'ÃŽ': 'Î',  'Ã"': 'Ô',
            'Ã™': 'Ù',  'Ãœ': 'Ü',  'Ã‡': 'Ç',  'Ã‹': 'Ë',  'Ã\u008f': 'Ï',
            # Caractères spéciaux
            'â€™': "'", 'â€œ': '"', 'â€': '"', 'â€"': '–', 'â€"': '—',
            'â€¦': '…', 'â€¢': '•', 'Â°': '°', 'Â«': '«', 'Â»': '»',
            'â€': '€', 'â„¢': '™', 'Â®': '®', 'Â©': '©',
            # Emojis corrompus - Profils et interface
            'ðŸ'¤': '\U0001F464',  # 👤 Profil utilisateur
            'ðŸ"‹': '\U0001F4CB',  # 📋 Presse-papier
            'ðŸ"§': '\U0001F527',  # 🔧 Outils
            'ðŸ'¼': '\U0001F4BC',  # 💼 Mallette professionnelle
            'ðŸŽ"': '\U0001F393',  # 🎓 Chapeau diplômé
            'ðŸ"ž': '\U0001F4DE',  # 📞 Téléphone
            'ðŸ"§': '\U0001F4E7',  # 📧 Email
            'ðŸ"—': '\U0001F517',  # 🔗 Lien
            # Emojis corrompus - Productivité
            'ðŸ'¡': '\U0001F4A1',  # 💡 Ampoule
            'ðŸ"Š': '\U0001F4CA',  # 📊 Graphique barres
            'ðŸŽ¯': '\U0001F3AF',  # 🎯 Cible
            'ðŸ"ˆ': '\U0001F4C8',  # 📈 Graphique croissant
            'ðŸ ': '\U0001F3E0',   # 🏠 Maison
            'ðŸ"': '\U0001F4C1',   # 📁 Dossier
            'ðŸ"‚': '\U0001F4C2',  # 📂 Dossier ouvert
            'ðŸ"™': '\U0001F4D9',  # 📙 Livre orange
            # Emojis corrompus - Sécurité
            'ðŸ"'': '\U0001F512',  # 🔒 Verrou
            'ðŸ›¡ï¸': '\U0001F6E1\uFE0F',  # 🛡️ Bouclier
            'ðŸš«': '\U0001F6AB',  # 🚫 Interdit
            # Caractères de contrôle emoji corrompus
            'âš™ï¸': '\u2699\uFE0F',  # ⚙️ Engrenage
            'âœ…': '\u2705',         # ✅ Case cochée
            'âŒ': '\u274C',          # ❌ Croix
            'âš ï¸': '\u26A0\uFE0F', # ⚠️ Attention
            'ðŸ–¥ï¸': '\U0001F5A5\uFE0F',  # 🖥️ Ordinateur de bureau
            'ðŸ"': '\U0001F50D',     # 🔍 Loupe
            'âš–ï¸': '\u2696\uFE0F', # ⚖️ Balance
            # Variations d'emoji avec sélecteurs
            'ðŸ"±': '\U0001F4F1',    # 📱 Téléphone mobile
            'ðŸ"²': '\U0001F4F2',    # 📲 Mobile avec flèche
            'ðŸŒ': '\U0001F30D',     # 🌍 Globe terrestre
            'ðŸŒŸ': '\U0001F31F',    # 🌟 Étoile brillante
            'ðŸŽ‰': '\U0001F389',    # 🎉 Confettis
            'ðŸ"Œ': '\U0001F4CC',    # 📌 Épingle
            'ðŸ"': '\U0001F4C4',     # 📄 Page
            'ðŸ"ƒ': '\U0001F4C3',    # 📃 Page avec coin replié
            'ðŸ—‚ï¸': '\U0001F5C2\uFE0F',  # 🗂️ Index de fichiers
            'ðŸ—ƒï¸': '\U0001F5C3\uFE0F',  # 🗃️ Boîte de fichiers
            # Autres patterns courants
            'Â ': ' ',  # Espace non-sécable
            'Â': '',    # Caractère seul souvent indésirable
        }
    
    def fix_file(self, file_path: Path, backup: bool = True) -> Dict:
        """Corrige un fichier et retourne les statistiques."""
        result = {
            'file': str(file_path.relative_to(self.project_root)),
            'corrections_made': 0,
            'bom_removed': False,
            'encoding_fixed': False,
            'error': None
        }
        
        try:
            # Backup si demandé
            if backup:
                backup_path = file_path.with_suffix(file_path.suffix + '.bak')
                shutil.copy2(file_path, backup_path)
            
            # Lire le fichier
            try:
                with open(file_path, 'rb') as f:
                    raw_content = f.read()
                
                # Détecter et supprimer BOM
                if raw_content.startswith(b'\xef\xbb\xbf'):
                    raw_content = raw_content[3:]
                    result['bom_removed'] = True
                
                # Décoder
                content = raw_content.decode('utf-8')
                
            except UnicodeDecodeError:
                # Essayer avec d'autres encodages
                for encoding in ['latin-1', 'cp1252', 'iso-8859-1']:
                    try:
                        content = raw_content.decode(encoding)
                        result['encoding_fixed'] = True
                        break
                    except:
                        continue
                else:
                    result['error'] = "Impossible de décoder le fichier"
                    return result
            
            # Appliquer les corrections
            original_content = content
            for mojibake, correct in self.fixes.items():
                if mojibake in content:
                    count_before = content.count(mojibake)
                    content = content.replace(mojibake, correct)
                    result['corrections_made'] += count_before
            
            # Sauvegarder seulement si des changements ont été faits
            if (content != original_content or 
                result['bom_removed'] or 
                result['encoding_fixed']):
                
                with open(file_path, 'w', encoding='utf-8', newline='\n') as f:
                    f.write(content)
                
                print(f"[FIX] {result['file']}: {result['corrections_made']} corrections")
                if result['bom_removed']:
                    print(f"      BOM supprimé")
                if result['encoding_fixed']:
                    print(f"      Encodage corrigé")
        
        except Exception as e:
            result['error'] = str(e)
            print(f"[ERROR] {result['file']}: {e}")
        
        return result
    
    def fix_files_from_audit(self, audit_results_path: Path, file_patterns: List[str] = None) -> Dict:
        """Corrige les fichiers identifiés par l'audit."""
        with open(audit_results_path, 'r', encoding='utf-8') as f:
            audit_data = json.load(f)
        
        results = {
            'summary': {
                'files_processed': 0,
                'files_fixed': 0,
                'total_corrections': 0,
                'errors': 0
            },
            'files': []
        }
        
        # Filtrer les fichiers si patterns spécifiés
        files_to_fix = audit_data['files']
        if file_patterns:
            files_to_fix = [
                f for f in files_to_fix 
                if any(pattern in f['file'] for pattern in file_patterns)
            ]
        
        # Trier par nombre de problèmes (traiter les plus impactés en premier)
        files_to_fix.sort(key=lambda x: len(x.get('mojibake_issues', [])), reverse=True)
        
        for file_info in files_to_fix:
            if (file_info.get('mojibake_issues') or 
                file_info.get('bom_detected') or 
                file_info.get('encoding_issues')):
                
                file_path = self.project_root / file_info['file']
                if file_path.exists():
                    result = self.fix_file(file_path)
                    results['files'].append(result)
                    results['summary']['files_processed'] += 1
                    
                    if result['corrections_made'] > 0 or result['bom_removed'] or result['encoding_fixed']:
                        results['summary']['files_fixed'] += 1
                        results['summary']['total_corrections'] += result['corrections_made']
                    
                    if result['error']:
                        results['summary']['errors'] += 1
        
        return results

def main():
    """Point d'entrée principal."""
    project_root = Path(__file__).parent.parent
    fixer = MojibakeFixer(str(project_root))
    
    # Charger les résultats de l'audit
    audit_file = project_root / "scripts" / "mojibake_audit_results.json"
    if not audit_file.exists():
        print("[ERROR] Fichier d'audit non trouvé. Exécutez d'abord mojibake_audit.py")
        return 1
    
    print("[FIX] Début de la correction automatisée des problèmes mojibake...")
    
    # Corriger d'abord les fichiers Python critiques (utiliser \\ pour Windows)
    python_patterns = [
        'app\\views\\main_window.py',
        'app\\workers\\cv_extractor.py', 
        'app\\utils\\',
        'app\\views\\'
    ]
    
    results = fixer.fix_files_from_audit(audit_file, python_patterns)
    
    print(f"\n[RESULTS] Correction terminée:")
    print(f"  Fichiers traités: {results['summary']['files_processed']}")
    print(f"  Fichiers corrigés: {results['summary']['files_fixed']}")  
    print(f"  Corrections totales: {results['summary']['total_corrections']}")
    print(f"  Erreurs: {results['summary']['errors']}")
    
    # Sauvegarder les résultats
    results_file = project_root / "scripts" / "mojibake_fix_results.json"
    with open(results_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"\n[SAVE] Résultats sauvegardés: {results_file}")
    
    if results['summary']['errors'] > 0:
        print(f"[WARN] {results['summary']['errors']} erreurs rencontrées")
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)