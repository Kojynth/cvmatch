#!/usr/bin/env python3
"""
Interface en ligne de commande pour CVExtractor
Usage: python -m cvextractor.cli extract <fichier> [options]
"""

import argparse
import json
import sys
import time
from pathlib import Path
import logging

from .core.extractor import CVExtractor
from .core.config import ExtractionConfig


def setup_logging(verbose: bool = False):
    """Configure le logging"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        format="%(asctime)s | %(levelname)s | %(name)s:%(funcName)s:%(lineno)d - %(message)s",
        level=level,
    )


def extract_command(args):
    """Commande d'extraction"""

    # Configuration
    config = ExtractionConfig()
    if args.no_ocr:
        config.enable_ocr = False
    if args.languages:
        config.ocr_languages = args.languages.split(",")

    # Extraction
    extractor = CVExtractor(config)

    try:
        print(f"🚀 Extraction de: {args.input}")
        start_time = time.time()

        result = extractor.extract(args.input)

        processing_time = time.time() - start_time
        print(f"✅ Extraction terminée en {processing_time:.2f}s")
        print(f"📊 {result.metrics.fields_extracted} champs extraits")
        print(f"🎯 Taux de complétude: {result.metrics.completion_rate:.1%}")

        # Sortie
        if args.output:
            output_path = Path(args.output)

            if args.format == "json":
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(result.to_json(include_provenance=not args.no_provenance))
                print(f"💾 Résultat sauvé: {output_path}")

            elif args.format == "yaml":
                import yaml

                data = result.to_dict(include_provenance=not args.no_provenance)
                with open(output_path, "w", encoding="utf-8") as f:
                    yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
                print(f"💾 Résultat sauvé: {output_path}")
        else:
            # Affichage sur stdout
            if args.format == "json":
                print(result.to_json(include_provenance=not args.no_provenance))
            elif args.format == "yaml":
                import yaml

                data = result.to_dict(include_provenance=not args.no_provenance)
                print(yaml.dump(data, default_flow_style=False, allow_unicode=True))

        if result.metrics.warnings:
            print("⚠️ Avertissements:")
            for warning in result.metrics.warnings:
                print(f"  - {warning}")

        return 0

    except Exception as e:
        print(f"❌ Erreur: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


def info_command(args):
    """Commande d'informations système"""

    from .loaders import LOADERS
    from .preprocessing.ocr_processor import OCRProcessor
    from .preprocessing.language_detector import LanguageDetector

    print("📋 CVExtractor - Informations système")
    print("=" * 40)

    # Formats supportés
    print("📄 Formats supportés:")
    for ext, loader_class in LOADERS.items():
        print(f"  {ext} -> {loader_class.__name__}")

    # OCR
    ocr = OCRProcessor(ExtractionConfig())
    print(
        f"\n👁️ OCR Tesseract: {'✅ Disponible' if ocr.is_available() else '❌ Non disponible'}"
    )
    if ocr.is_available():
        langs = ocr.get_available_languages()
        print(f"   Langues: {', '.join(langs[:10])}{' ...' if len(langs) > 10 else ''}")

    # Détection de langue
    detector = LanguageDetector()
    supported_langs = detector.get_supported_languages()
    print(f"\n🌍 Langues détectables: {', '.join(supported_langs)}")

    return 0


def benchmark_command(args):
    """Commande de benchmark"""

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"❌ Fichier non trouvé: {input_path}")
        return 1

    if input_path.is_file():
        files = [input_path]
    elif input_path.is_dir():
        # Tous les fichiers supportés du dossier
        files = []
        for ext in [".pdf", ".docx", ".odt", ".jpg", ".jpeg", ".png"]:
            files.extend(input_path.glob(f"*{ext}"))
        files.extend(input_path.glob(f"*{ext.upper()}"))
    else:
        print(f"❌ Chemin invalide: {input_path}")
        return 1

    if not files:
        print("❌ Aucun fichier CV trouvé")
        return 1

    print(f"🏃 Benchmark sur {len(files)} fichier(s)")
    print("=" * 50)

    config = ExtractionConfig()
    if args.no_ocr:
        config.enable_ocr = False

    extractor = CVExtractor(config)

    results = []
    total_time = 0

    for i, file_path in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {file_path.name}...")

        try:
            start_time = time.time()
            result = extractor.extract(str(file_path))
            processing_time = time.time() - start_time
            total_time += processing_time

            results.append(
                {
                    "file": file_path.name,
                    "time": processing_time,
                    "fields": result.metrics.fields_extracted,
                    "completion": result.metrics.completion_rate,
                    "ocr_pages": result.metrics.ocr_pages,
                    "success": True,
                    "warnings": len(result.metrics.warnings),
                }
            )

            print(
                f"  ✅ {processing_time:.2f}s - {result.metrics.fields_extracted} champs"
            )

        except Exception as e:
            results.append(
                {
                    "file": file_path.name,
                    "time": 0,
                    "fields": 0,
                    "completion": 0,
                    "ocr_pages": 0,
                    "success": False,
                    "error": str(e),
                    "warnings": 0,
                }
            )
            print(f"  ❌ Erreur: {e}")

    # Résumé
    print("\n📊 Résumé du benchmark")
    print("=" * 30)

    successful = [r for r in results if r["success"]]
    if successful:
        avg_time = sum(r["time"] for r in successful) / len(successful)
        avg_fields = sum(r["fields"] for r in successful) / len(successful)
        avg_completion = sum(r["completion"] for r in successful) / len(successful)

        print(f"✅ Succès: {len(successful)}/{len(results)}")
        print(f"⏱️ Temps moyen: {avg_time:.2f}s")
        print(f"📋 Champs moyens: {avg_fields:.1f}")
        print(f"🎯 Complétude moyenne: {avg_completion:.1%}")
        print(f"🕐 Temps total: {total_time:.2f}s")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        print(f"\n💾 Résultats détaillés: {args.output}")

    return 0


def main():
    """Point d'entrée principal"""

    parser = argparse.ArgumentParser(
        prog="cvextractor", description="Extracteur de CV hors-ligne"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Mode verbeux")

    subparsers = parser.add_subparsers(dest="command", help="Commandes")

    # Commande extract
    extract_parser = subparsers.add_parser("extract", help="Extraire un CV")
    extract_parser.add_argument("input", help="Fichier CV à traiter")
    extract_parser.add_argument("-o", "--output", help="Fichier de sortie")
    extract_parser.add_argument(
        "-f",
        "--format",
        choices=["json", "yaml"],
        default="json",
        help="Format de sortie",
    )
    extract_parser.add_argument("--no-ocr", action="store_true", help="Désactiver OCR")
    extract_parser.add_argument(
        "--no-provenance", action="store_true", help="Exclure les données de provenance"
    )
    extract_parser.add_argument(
        "--languages", help="Langues OCR (séparées par virgule)"
    )
    extract_parser.set_defaults(func=extract_command)

    # Commande info
    info_parser = subparsers.add_parser("info", help="Informations système")
    info_parser.set_defaults(func=info_command)

    # Commande benchmark
    bench_parser = subparsers.add_parser("benchmark", help="Benchmark de performance")
    bench_parser.add_argument("input", help="Fichier ou dossier à tester")
    bench_parser.add_argument("-o", "--output", help="Fichier résultats JSON")
    bench_parser.add_argument("--no-ocr", action="store_true", help="Désactiver OCR")
    bench_parser.set_defaults(func=benchmark_command)

    # Parse arguments
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Setup logging
    setup_logging(args.verbose)

    # Exécuter commande
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
