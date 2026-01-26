#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Setup automatique WeasyPrint + GTK3 Runtime
==========================================

Installation automatique et silencieuse de GTK3 Runtime et WeasyPrint.
"""

import subprocess
import sys
import os
import tempfile
import urllib.request
import zipfile
import shutil
from pathlib import Path
import platform
import json

# Configuration encodage pour Windows
if platform.system().lower() == "windows":
    import locale
    try:
        # Forcer UTF-8 pour éviter les problèmes d'emojis
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass


def is_windows():
    """Vérifie si on est sur Windows."""
    return platform.system().lower() == "windows"


def check_admin_rights():
    """Vérifie les droits administrateur sur Windows."""
    if not is_windows():
        return True
    
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False


def download_file(url: str, dest_path: Path, description: str = "fichier"):
    """Télécharge un fichier avec barre de progression."""
    print(f"📥 Téléchargement {description}...")
    
    try:
        def progress_hook(block_num, block_size, total_size):
            if total_size > 0:
                percent = min(100, (block_num * block_size * 100) // total_size)
                bar_length = 40
                filled_length = (percent * bar_length) // 100
                bar = '█' * filled_length + '░' * (bar_length - filled_length)
                print(f"\r📥 [{bar}] {percent}%", end='', flush=True)
        
        urllib.request.urlretrieve(url, dest_path, progress_hook)
        print(f"\n✅ {description} téléchargé : {dest_path}")
        return True
        
    except Exception as e:
        print(f"\n❌ Erreur téléchargement {description} : {e}")
        return False


def install_gtk3_runtime_portable():
    """Installe GTK3 Runtime avec l'installeur en mode portable."""
    print("🔧 Installation GTK3 Runtime (mode portable via installeur)...")
    
    # Utiliser l'installeur standard mais extraire manuellement
    installer_url = "https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases/download/2022-01-04/gtk3-runtime-3.24.31-2022-01-04-ts-win64.exe"
    
    # Dossier d'installation portable
    install_dir = Path.home() / ".cvmatch" / "gtk3-runtime"
    install_dir.mkdir(parents=True, exist_ok=True)
    
    # Télécharger l'installeur
    temp_dir = Path(tempfile.gettempdir())
    installer_path = temp_dir / "gtk3-installer.exe"
    
    if not download_file(installer_url, installer_path, "installeur GTK3"):
        # Fallback : télécharger WeasyPrint via pip seulement
        print("⚠️ Téléchargement GTK3 échoué, tentative installation WeasyPrint seul...")
        return install_weasyprint_without_gtk()
    
    # Tenter extraction directe avec 7zip si disponible
    print("📦 Tentative d'extraction portable...")
    try:
        # Méthode 1: Installer en mode silencieux vers dossier utilisateur
        result = subprocess.run([
            str(installer_path), 
            "/S",  # Silent
            f"/D={install_dir}"  # Destination
        ], check=False, capture_output=True)
        
        if result.returncode == 0 and (install_dir / "bin").exists():
            print(f"✅ GTK3 installé vers : {install_dir}")
            
            # Configuration PATH
            gtk_bin_path = install_dir / "bin"
            current_path = os.environ.get('PATH', '')
            if str(gtk_bin_path) not in current_path:
                os.environ['PATH'] = f"{gtk_bin_path}{os.pathsep}{current_path}"
                print(f"✅ GTK3 ajouté au PATH : {gtk_bin_path}")
            
            # Sauvegarder config
            config = {
                "gtk_path": str(install_dir),
                "bin_path": str(gtk_bin_path),
                "version": "3.24.31",
                "installed_at": "portable"
            }
            config_file = Path.home() / ".cvmatch" / "gtk_config.json"
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)
            
            return True
        else:
            print("⚠️ Installation portable échouée, utilisation fallback")
            return install_weasyprint_without_gtk()
        
    except Exception as e:
        print(f"❌ Erreur installation portable : {e}")
        return install_weasyprint_without_gtk()
    finally:
        if installer_path.exists():
            installer_path.unlink()


def install_weasyprint_without_gtk():
    """Installe WeasyPrint sans GTK (mode dégradé)."""
    print("🔄 Installation WeasyPrint sans GTK (mode dégradé)...")
    try:
        subprocess.run([
            sys.executable, "-m", "pip", "install", 
            "weasyprint", "--no-deps", "--force-reinstall"
        ], check=True)
        
        print("⚠️ WeasyPrint installé sans GTK - PDF peut ne pas fonctionner")
        print("💡 L'application fonctionnera en mode HTML uniquement")
        return True
    except:
        print("❌ Échec installation WeasyPrint")
        return False


def install_gtk3_runtime_installer():
    """Installe GTK3 Runtime avec l'installeur officiel."""
    print("🔧 Installation GTK3 Runtime (installeur officiel)...")
    
    # URL de l'installeur
    installer_url = "https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases/download/2022-01-04/gtk3-runtime-3.24.31-2022-01-04-ts-win64.exe"
    
    # Télécharger l'installeur
    temp_dir = Path(tempfile.gettempdir())
    installer_path = temp_dir / "gtk3-runtime-installer.exe"
    
    if not download_file(installer_url, installer_path, "installeur GTK3"):
        return False
    
    # Lancer l'installeur en mode silencieux
    print("🚀 Installation GTK3 Runtime...")
    try:
        # Tentative d'installation silencieuse
        result = subprocess.run([
            str(installer_path), 
            "/S",  # Silent install
            "/D=C:\\GTK3-Runtime"  # Destination directory
        ], check=False, capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✅ GTK3 Runtime installé avec succès !")
            return True
        else:
            print("⚠️  Installation silencieuse échouée, lancement interactif...")
            # Fallback vers installation interactive
            subprocess.run([str(installer_path)], check=False)
            
            # Demander confirmation à l'utilisateur
            choice = input("✅ GTK3 installé manuellement ? (o/n) : ").lower().strip()
            return choice in ['o', 'oui', 'y', 'yes']
        
    except Exception as e:
        print(f"❌ Erreur installation : {e}")
        return False
    finally:
        # Nettoyer
        if installer_path.exists():
            installer_path.unlink()


def setup_gtk_environment():
    """Configure l'environnement GTK."""
    print("⚙️  Configuration environnement GTK...")
    
    # Chemins possibles de GTK
    possible_paths = [
        Path("C:/GTK3-Runtime"),
        Path.home() / ".cvmatch" / "gtk3-runtime",
        Path("C:/msys64/mingw64"),
        Path("C:/Program Files/GTK3-Runtime"),
    ]
    
    gtk_path = None
    for path in possible_paths:
        if (path / "bin").exists():
            gtk_path = path
            break
    
    if not gtk_path:
        print("❌ GTK3 Runtime non trouvé dans les chemins standards")
        return False
    
    print(f"✅ GTK3 trouvé : {gtk_path}")
    
    # Configuration variables d'environnement
    bin_path = gtk_path / "bin"
    lib_path = gtk_path / "lib"
    
    # Ajouter au PATH de manière persistante (pour cette session)
    current_path = os.environ.get('PATH', '')
    if str(bin_path) not in current_path:
        os.environ['PATH'] = f"{bin_path}{os.pathsep}{current_path}"
    
    # Variables GTK spécifiques
    os.environ['GTK_BASEPATH'] = str(gtk_path)
    os.environ['GDK_PIXBUF_MODULE_FILE'] = str(lib_path / "gdk-pixbuf-2.0" / "2.10.0" / "loaders.cache")
    
    return True


def install_weasyprint():
    """Installe WeasyPrint après GTK."""
    print("📦 Installation WeasyPrint...")
    
    commands = [
        # Mise à jour pip
        [sys.executable, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"],
        # Installation WeasyPrint
        [sys.executable, "-m", "pip", "install", "weasyprint", "--no-cache-dir"]
    ]
    
    for cmd in commands:
        print(f"🔧 Exécution : {' '.join(cmd[3:])}")
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            print("✅ Succès")
        except subprocess.CalledProcessError as e:
            print(f"❌ Erreur : {e.stderr}")
            
            # Tentative avec version spécifique si échec
            if "weasyprint" in cmd:
                print("🔄 Tentative avec version spécifique...")
                try:
                    alt_cmd = [sys.executable, "-m", "pip", "install", "weasyprint==60.2", "--no-cache-dir"]
                    subprocess.run(alt_cmd, check=True)
                    print("✅ WeasyPrint installé avec version spécifique")
                    return True
                except:
                    return False
            return False
    
    return True


def test_weasyprint_complete():
    """Test complet de WeasyPrint."""
    print("🧪 Test complet WeasyPrint...")
    
    try:
        # Test 1 : Import
        from weasyprint import HTML, CSS
        print("✅ Import WeasyPrint réussi")
        
        # Test 2 : Génération HTML simple
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <title>Test CVMatch</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 40px; }
                h1 { color: #0078d4; }
                .success { color: green; font-weight: bold; }
            </style>
        </head>
        <body>
            <h1>🎉 CVMatch - Test WeasyPrint</h1>
            <p class="success">✅ WeasyPrint fonctionne correctement !</p>
            <p>Ce PDF a été généré automatiquement lors de l'installation.</p>
            <ul>
                <li>Import des bibliothèques : OK</li>
                <li>Génération HTML : OK</li>
                <li>Export PDF : OK</li>
            </ul>
        </body>
        </html>
        """
        
        html_doc = HTML(string=html_content)
        print("✅ Document HTML créé")
        
        # Test 3 : Génération PDF
        test_dir = Path.home() / ".cvmatch" / "tests"
        test_dir.mkdir(parents=True, exist_ok=True)
        
        pdf_path = test_dir / "weasyprint_test.pdf"
        html_doc.write_pdf(str(pdf_path))
        
        if pdf_path.exists() and pdf_path.stat().st_size > 1000:  # PDF > 1KB
            print(f"✅ PDF généré avec succès : {pdf_path}")
            print(f"📊 Taille : {pdf_path.stat().st_size} bytes")
            return True
        else:
            print("❌ PDF généré mais vide ou trop petit")
            return False
            
    except ImportError as e:
        print(f"❌ Erreur import : {e}")
        return False
    except Exception as e:
        print(f"❌ Erreur génération : {e}")
        return False


def create_startup_script():
    """Crée un script de démarrage pour configurer GTK."""
    print("📝 Création script de démarrage...")
    
    script_content = '''@echo off
REM Script de configuration GTK3 pour CVMatch
REM Ajoute GTK3 au PATH avant de lancer Python

set GTK_PATH=C:\\GTK3-Runtime
set GTK_BIN=%GTK_PATH%\\bin
set GTK_LIB=%GTK_PATH%\\lib

REM Ajouter GTK au PATH
set PATH=%GTK_BIN%;%PATH%

REM Variables GTK
set GTK_BASEPATH=%GTK_PATH%
set GDK_PIXBUF_MODULE_FILE=%GTK_LIB%\\gdk-pixbuf-2.0\\2.10.0\\loaders.cache

REM Lancer CVMatch
python "%~dp0..\\main.py" %*
'''
    
    script_path = Path("scripts") / "cvmatch_with_gtk.bat"
    script_path.parent.mkdir(exist_ok=True)
    
    with open(script_path, 'w') as f:
        f.write(script_content)
    
    print(f"✅ Script créé : {script_path}")
    return script_path


def main():
    """Fonction principale d'installation."""
    print("🔧 Setup automatique WeasyPrint + GTK3 Runtime")
    print("=" * 60)
    print(f"🖥️  Système : {platform.system()} {platform.release()}")
    print(f"🐍 Python : {sys.version}")
    
    if not is_windows():
        print("⚠️  Ce script est conçu pour Windows. Sur Linux/macOS :")
        print("   sudo apt-get install libpango-1.0-0 libharfbuzz0b libpangoft2-1.0-0  # Ubuntu")
        print("   brew install pango  # macOS")
        print("   pip install weasyprint")
        return
    
    print("\n🎯 Plan d'installation :")
    print("1. Installation GTK3 Runtime")
    print("2. Configuration environnement")
    print("3. Installation WeasyPrint")
    print("4. Tests de validation")
    print("5. Configuration finale")
    
    # Étape 1 : GTK3 Runtime
    print("\n" + "="*50)
    print("📦 ÉTAPE 1 : Installation GTK3 Runtime")
    
    has_admin = check_admin_rights()
    print(f"🔐 Droits administrateur : {'✅ Oui' if has_admin else '❌ Non'}")
    
    if has_admin:
        print("🔧 Mode administrateur - Installation standard...")
        gtk_success = install_gtk3_runtime_installer()
    else:
        print("🔧 Mode utilisateur - Installation portable...")
        gtk_success = install_gtk3_runtime_portable()
    
    if not gtk_success:
        print("❌ Échec installation GTK3")
        return False
    
    # Étape 2 : Configuration environnement
    print("\n" + "="*50)
    print("⚙️  ÉTAPE 2 : Configuration environnement")
    
    if not setup_gtk_environment():
        print("❌ Échec configuration GTK")
        return False
    
    # Étape 3 : WeasyPrint
    print("\n" + "="*50)
    print("📦 ÉTAPE 3 : Installation WeasyPrint")
    
    if not install_weasyprint():
        print("❌ Échec installation WeasyPrint")
        return False
    
    # Étape 4 : Tests
    print("\n" + "="*50)
    print("🧪 ÉTAPE 4 : Tests de validation")
    
    if not test_weasyprint_complete():
        print("❌ Tests WeasyPrint échoués")
        return False
    
    # Étape 5 : Configuration finale
    print("\n" + "="*50)
    print("⚙️  ÉTAPE 5 : Configuration finale")
    
    script_path = create_startup_script()
    
    # Résumé final
    print("\n" + "="*60)
    print("🎉 INSTALLATION TERMINÉE AVEC SUCCÈS !")
    print("="*60)
    print("✅ GTK3 Runtime installé")
    print("✅ WeasyPrint fonctionnel")
    print("✅ Tests passés")
    print("✅ Configuration sauvée")
    
    print(f"\n🚀 Pour lancer CVMatch :")
    print(f"   Option 1 : python main.py")
    print(f"   Option 2 : {script_path}")
    
    print(f"\n📁 Fichiers créés :")
    print(f"   - Test PDF : ~/.cvmatch/tests/weasyprint_test.pdf")
    print(f"   - Configuration : ~/.cvmatch/gtk_config.json")
    print(f"   - Script : {script_path}")
    
    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⏹️  Installation interrompue par l'utilisateur")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Erreur inattendue : {e}")
        sys.exit(1)
