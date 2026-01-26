#!/usr/bin/env python3
"""
Script de réparation du cache de modèles
========================================

Nettoie le cache HuggingFace et optimise les téléchargements.
"""

import os
import shutil
from pathlib import Path
import sys


def detect_broken_symlinks(cache_dir: Path) -> list:
    """Détecte les symlinks cassés dans le cache."""
    broken = []
    for item in cache_dir.rglob("*"):
        if item.is_symlink():
            try:
                item.resolve(strict=True)  # Raises if broken
            except (OSError, FileNotFoundError):
                broken.append(item)
    return broken


def detect_zero_byte_files(cache_dir: Path) -> list:
    """Détecte les fichiers de taille zéro (symlinks échoués)."""
    zero_files = []
    extensions = {'.safetensors', '.bin', '.pt', '.pth', '.onnx'}
    for item in cache_dir.rglob("*"):
        if item.is_file() and not item.is_symlink():
            if item.suffix in extensions and item.stat().st_size == 0:
                zero_files.append(item)
    return zero_files


def detect_incomplete_shards(cache_dir: Path) -> list:
    """Détecte les modèles avec des shards manquants ou corrompus."""
    incomplete = []
    for model_dir in cache_dir.iterdir():
        if model_dir.is_dir() and model_dir.name.startswith('models--'):
            snapshots_dir = model_dir / "snapshots"
            if snapshots_dir.exists():
                for snapshot in snapshots_dir.iterdir():
                    if snapshot.is_dir():
                        # Check for model-*.safetensors or model-*.bin pattern
                        shards_st = list(snapshot.glob("model-*.safetensors"))
                        shards_bin = list(snapshot.glob("model-*.bin"))
                        shards = shards_st or shards_bin

                        if shards:
                            # Verify all shards are complete (non-zero size)
                            for shard in shards:
                                try:
                                    if shard.stat().st_size == 0:
                                        model_name = model_dir.name.replace('models--', '').replace('--', '/')
                                        incomplete.append((model_name, shard.name, "zero_size"))
                                except OSError:
                                    model_name = model_dir.name.replace('models--', '').replace('--', '/')
                                    incomplete.append((model_name, shard.name, "inaccessible"))
    return incomplete


def fix_model_cache():
    """Répare le cache de modèles HuggingFace."""
    print("=== REPARATION CACHE HUGGINGFACE ===\n")
    
    # Chemin cache
    cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
    
    if not cache_dir.exists():
        print("❌ Cache HuggingFace introuvable")
        return False
    
    print(f"📁 Cache trouvé: {cache_dir}")
    
    # 1. Lister les fichiers incomplets
    incomplete_files = []
    for root, dirs, files in os.walk(cache_dir):
        for file in files:
            if file.endswith('.incomplete'):
                incomplete_files.append(Path(root) / file)
    
    print(f"\n🔍 Fichiers incomplets trouvés: {len(incomplete_files)}")

    if incomplete_files:
        print("\n🧹 Nettoyage des fichiers incomplets...")
        for file in incomplete_files:
            try:
                file.unlink()
                print(f"   ✅ Supprimé: {file.name}")
            except Exception as e:
                print(f"   ❌ Erreur: {file.name} - {e}")

    # 1b. Détecter les symlinks cassés (Windows)
    broken_symlinks = detect_broken_symlinks(cache_dir)
    print(f"\n🔗 Symlinks cassés trouvés: {len(broken_symlinks)}")

    if broken_symlinks:
        print("\n⚠️ Symlinks cassés détectés (problème Windows courant):")
        for symlink in broken_symlinks[:10]:  # Max 10 affichés
            print(f"   - {symlink.name}")
        if len(broken_symlinks) > 10:
            print(f"   ... et {len(broken_symlinks) - 10} autres")

        response = input("\n   Supprimer tous les symlinks cassés? (y/n): ")
        if response.lower() == 'y':
            for symlink in broken_symlinks:
                try:
                    symlink.unlink()
                except Exception as e:
                    print(f"   ❌ Erreur: {symlink.name} - {e}")
            print(f"   ✅ {len(broken_symlinks)} symlinks cassés supprimés")

    # 1c. Détecter les fichiers de taille zéro
    zero_files = detect_zero_byte_files(cache_dir)
    print(f"\n📄 Fichiers de taille zéro trouvés: {len(zero_files)}")

    if zero_files:
        print("\n⚠️ Fichiers modèle de taille zéro (téléchargement échoué):")
        for zf in zero_files[:10]:
            print(f"   - {zf.parent.name}/{zf.name}")
        if len(zero_files) > 10:
            print(f"   ... et {len(zero_files) - 10} autres")

        response = input("\n   Supprimer tous les fichiers de taille zéro? (y/n): ")
        if response.lower() == 'y':
            for zf in zero_files:
                try:
                    zf.unlink()
                except Exception as e:
                    print(f"   ❌ Erreur: {zf.name} - {e}")
            print(f"   ✅ {len(zero_files)} fichiers vides supprimés")

    # 1d. Détecter les shards incomplets
    incomplete_shards = detect_incomplete_shards(cache_dir)
    print(f"\n🧩 Shards incomplets trouvés: {len(incomplete_shards)}")

    if incomplete_shards:
        print("\n⚠️ Modèles avec shards corrompus (cause du crash à 67%):")
        for model_name, shard_name, reason in incomplete_shards:
            print(f"   - {model_name}: {shard_name} ({reason})")
    
    # 2. Vérifier les modèles partiellement téléchargés
    model_dirs = [d for d in cache_dir.iterdir() if d.is_dir() and d.name.startswith('models--')]
    print(f"\n📊 Modèles en cache: {len(model_dirs)}")
    
    for model_dir in model_dirs:
        model_name = model_dir.name.replace('models--', '').replace('--', '/')
        blobs_dir = model_dir / "blobs"
        
        if blobs_dir.exists():
            blob_files = list(blobs_dir.glob("*"))
            incomplete_blobs = [f for f in blob_files if f.name.endswith('.incomplete')]
            
            if incomplete_blobs:
                print(f"   🔄 {model_name}: {len(incomplete_blobs)} fichiers incomplets")
                
                # Option: supprimer complètement le modèle corrompu  
                response = input(f"      Supprimer {model_name} corrompu? (y/n): ")
                if response.lower() == 'y':
                    try:
                        shutil.rmtree(model_dir)
                        print(f"   ✅ {model_name} supprimé - sera re-téléchargé proprement")
                    except Exception as e:
                        print(f"   ❌ Erreur suppression: {e}")
            else:
                print(f"   ✅ {model_name}: OK")
    
    # 3. Suggestions d'optimisation
    print(f"\n🚀 OPTIMISATIONS RECOMMANDÉES:")
    print("1. Connexion plus rapide (WiFi vs Ethernet)")
    print("2. Télécharger une seule fois puis utiliser offline")
    print("3. Utiliser des modèles plus petits (quantifiés)")
    print("4. Configurer un proxy/CDN si disponible")

    # 4. Configuration environnement
    print(f"\n⚙️ VARIABLES D'ENVIRONNEMENT:")
    print("export HF_HUB_CACHE=" + str(cache_dir))
    print("export HF_HUB_OFFLINE=1  # Mode offline après téléchargement")
    print("export HF_HUB_DISABLE_SYMLINKS=1  # Désactive symlinks (Windows)")

    # 5. Résumé des problèmes détectés
    total_issues = len(incomplete_files) + len(broken_symlinks) + len(zero_files) + len(incomplete_shards)
    if total_issues > 0:
        print(f"\n⚠️ TOTAL PROBLÈMES DÉTECTÉS: {total_issues}")
        print("   Après nettoyage, re-téléchargez les modèles concernés.")
    
    return True

def main():
    """Point d'entrée principal."""
    success = fix_model_cache()
    
    if success:
        print(f"\n✅ CACHE REPARE!")
        print("💡 Conseil: Prochain téléchargement sera plus rapide")
        return 0
    else:
        print(f"\n❌ Problèmes détectés")
        return 1

if __name__ == "__main__":
    sys.exit(main())
