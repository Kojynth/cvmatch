"""
Script de correction WeasyPrint pour Windows
============================================

Corrige les problèmes d'installation de WeasyPrint sur Windows
en installant les dépendances GTK nécessaires.
"""

import os
import sys
import subprocess
import tempfile
import urllib.request
from pathlib import Path
from loguru import logger

def check_weasyprint_status():
    """Vérifie le statut actuel de WeasyPrint."""
    try:
        import weasyprint
        logger.info("✅ WeasyPrint déjà installé et fonctionnel")
        return True
    except ImportError:
        logger.warning("❌ WeasyPrint pas installé")
        return False
    except Exception as e:
        logger.error(f"❌ WeasyPrint installé mais dysfonctionnel: {e}")
        return False

def install_gtk_runtime():
    """Installe GTK Runtime pour Windows."""
    logger.info("🔧 Installation de GTK Runtime...")
    
    # URL de GTK pour Windows
    gtk_url = "https://github.com/tschoonj/GTK-for-Windows-Runtime-Environment-Installer/releases/download/2022-01-04/gtk3-runtime-3.24.31-2022-01-04-ts-win64.exe"
    
    try:
        # Télécharger l'installateur GTK
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as tmp:
            logger.info("📥 Téléchargement de GTK Runtime...")
            urllib.request.urlretrieve(gtk_url, tmp.name)
            gtk_installer = tmp.name
        
        # Lancer l'installation silencieuse
        logger.info("🚀 Installation de GTK Runtime...")
        result = subprocess.run([gtk_installer, "/S"], capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("✅ GTK Runtime installé avec succès")
            
            # Nettoyer
            os.unlink(gtk_installer)
            return True
        else:
            logger.error(f"❌ Échec installation GTK: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Erreur téléchargement/installation GTK: {e}")
        return False

def install_weasyprint_pip():
    """Installe WeasyPrint via pip."""
    logger.info("📦 Installation de WeasyPrint via pip...")
    
    try:
        # Installer WeasyPrint
        result = subprocess.run([
            sys.executable, "-m", "pip", "install", 
            "--upgrade", "weasyprint"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("✅ WeasyPrint installé via pip")
            return True
        else:
            logger.error(f"❌ Échec installation pip: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Erreur installation pip: {e}")
        return False

def install_weasyprint_alternative():
    """Installe WeasyPrint avec méthode alternative."""
    logger.info("🔧 Tentative d'installation alternative...")
    
    try:
        # Installation avec contraintes relâchées
        result = subprocess.run([
            sys.executable, "-m", "pip", "install", 
            "--find-links", "https://github.com/Kozea/WeasyPrint/releases",
            "weasyprint"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("✅ WeasyPrint installé (méthode alternative)")
            return True
        else:
            logger.warning(f"⚠️ Méthode alternative échouée: {result.stderr}")
            return False
            
    except Exception as e:
        logger.error(f"❌ Erreur méthode alternative: {e}")
        return False

def configure_fallback_export():
    """Configure l'export en mode fallback si WeasyPrint échoue."""
    logger.info("🔄 Configuration du mode fallback...")
    
    try:
        # Créer un fichier de configuration
        config_dir = Path.home() / ".cvmatch"
        config_dir.mkdir(exist_ok=True)
        
        config_file = config_dir / "export_config.json"
        
        import json
        config = {
            "pdf_export_enabled": False,
            "fallback_to_html": True,
            "weasyprint_status": "disabled",
            "alternative_pdf_methods": [
                "Utiliser un convertisseur en ligne HTML -> PDF",
                "Imprimer la page HTML en PDF depuis le navigateur",
                "Utiliser un service comme Puppeteer ou Playwright"
            ]
        }
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        logger.info(f"✅ Configuration fallback sauvée: {config_file}")
        return True
        
    except Exception as e:
        logger.error(f"❌ Erreur configuration fallback: {e}")
        return False

def main():
    """Point d'entrée principal."""
    logger.info("🚀 CVMatch - Correction WeasyPrint pour Windows")
    logger.info("=" * 50)
    
    # Étape 1: Vérifier le statut actuel
    if check_weasyprint_status():
        logger.info("🎉 WeasyPrint fonctionne déjà - Aucune action nécessaire")
        return
    
    # Étape 2: Installer GTK Runtime
    logger.info("\n📋 Étape 1/4: Installation GTK Runtime")
    gtk_success = install_gtk_runtime()
    
    # Étape 3: Installer WeasyPrint
    logger.info("\n📋 Étape 2/4: Installation WeasyPrint")
    wp_success = install_weasyprint_pip()
    
    if not wp_success:
        logger.info("\n📋 Étape 2bis/4: Méthode alternative")
        wp_success = install_weasyprint_alternative()
    
    # Étape 4: Tester l'installation
    logger.info("\n📋 Étape 3/4: Test de l'installation")
    final_status = check_weasyprint_status()
    
    # Étape 5: Configuration fallback si nécessaire
    if not final_status:
        logger.info("\n📋 Étape 4/4: Configuration fallback")
        configure_fallback_export()
        
        logger.warning("\n⚠️ RÉSUMÉ:")
        logger.warning("- WeasyPrint n'a pas pu être installé correctement")
        logger.warning("- L'export PDF est désactivé")
        logger.warning("- L'application utilisera l'export HTML comme alternative")
        logger.warning("- Vous pouvez convertir manuellement HTML -> PDF")
    else:
        logger.info("\n🎉 RÉSUMÉ:")
        logger.info("✅ WeasyPrint installé et fonctionnel")
        logger.info("✅ Export PDF activé")
        logger.info("✅ CVMatch entièrement opérationnel")
    
    logger.info("\n" + "=" * 50)
    logger.info("🏁 Correction terminée - Vous pouvez relancer CVMatch")

if __name__ == "__main__":
    main()
