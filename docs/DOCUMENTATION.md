# 📚 Documentation CVMatch - Index central

Documentation organisée et centralisée pour CVMatch.

> **Dernière mise à jour** : Novembre 2025 - Consolidation des docs (fusion de 3 fichiers, archivage de 5 fichiers obsolètes)

---

## 🚀 Démarrage rapide

### Pour lancer CVMatch
1. [`COMMENT_LANCER.md`](COMMENT_LANCER.md) - **Lancement selon votre OS**
2. [`README_VENV.md`](README_VENV.md) - **Configuration environnement virtuel**

### Pour installer les dépendances
- [`README_WEASYPRINT.md`](README_WEASYPRINT.md) - **Installation & dépannage WeasyPrint** (fusionné + amélioré)

---

## 📖 Documentation Technique

### 🏗️ Architecture et structure

- [`STRUCTURE.md`](STRUCTURE.md) - **Architecture complète et organisation du projet**
- [`GUI_ARCHITECTURE.md`](GUI_ARCHITECTURE.md) - **Architecture technique de l'interface**
- [`AGENTS.md`](AGENTS.md) - **Repository Guidelines et conventions**

### 🤖 Intelligence Artificielle

- [`MODELES_IA.md`](MODELES_IA.md) - **Documentation des modèles IA**
- [`CONFIG_MODELS.md`](CONFIG_MODELS.md) - **Model Registry Guide**
- [`LOGS_BACKEND_ML.md`](LOGS_BACKEND_ML.md) - **Traçabilité HF vs Mock et routage NER**

### 📖 Extraction CV

- [`CV_EXTRACTION_ENHANCEMENTS.md`](CV_EXTRACTION_ENHANCEMENTS.md) - **Enhancements du pipeline d'extraction**
- [`FRENCH_DATE_PARSING_README.md`](FRENCH_DATE_PARSING_README.md) - **Parsing des dates en français**
- [`OUTPUT_SCHEMA.md`](OUTPUT_SCHEMA.md) - **Schéma de sortie de l'extraction**
- [`TESTS_EXTRACTION.md`](TESTS_EXTRACTION.md) - **Tests du pipeline d'extraction**
- [`extraction/experiences.md`](extraction/experiences.md) - **Extraction spécialisée des expériences**

### 🎨 Interface utilisateur

- [`UI_UX_GUIDE.md`](UI_UX_GUIDE.md) - **Guide UI/UX et design**
- [`INTEGRATION_ML_UI.md`](INTEGRATION_ML_UI.md) - **Intégration ML et signaux UI**

### 🔤 Qualité du code et encodage

- [`UTF8_ENCODING_GUIDE.md`](UTF8_ENCODING_GUIDE.md) - **Guide complet UTF-8 & Mojibake** ⭐ **CONSOLIDÉ** (3 docs fusionnés)
- [`SYNTAX_ERROR_PREVENTION.md`](SYNTAX_ERROR_PREVENTION.md) - **Prévention des erreurs syntaxe**
- [`OPTIMIZATIONS.md`](OPTIMIZATIONS.md) - **Optimisations de démarrage**

### 🔒 Sécurité et confidentialité

- [`pii_redaction.md`](pii_redaction.md) - **Protection des données personnelles (PII)**
- [`pii_safe_logging.md`](pii_safe_logging.md) - **PII-Safe Logging System**
- [`reset_logging_system.md`](reset_logging_system.md) - **Système de logging de réinitialisation**

### 🔧 Refactorisation

- [`REFACTORING_EXTRACTION_MAPPER_KIT.md`](REFACTORING_EXTRACTION_MAPPER_KIT.md) - **Kit complet de refactorisation extraction_mapper**
- [`REFACTORING_QUICK_START.md`](REFACTORING_QUICK_START.md) - **Quick start refactorisation**
- [`REFACTORING_EXEC_PLAN.md`](REFACTORING_EXEC_PLAN.md) - **Plan d'exécution détaillé**

### 📊 Remédiation et tests (6 phases)

- [`remediation/REMEDIATION_EXECUTION_PLAN.md`](remediation/REMEDIATION_EXECUTION_PLAN.md) - **Plan d'exécution 6 phases**
- [`remediation/REMEDIATION_STRUCTURE_MAP.md`](remediation/REMEDIATION_STRUCTURE_MAP.md) - **Structure map 6 phases**
- [`remediation/TEST_REMEDIATION_REPORT.md`](remediation/TEST_REMEDIATION_REPORT.md) - **Rapport de test remédiation**
- [`PHASE2_CONTACT_PROTECTION_REPORT.md`](PHASE2_CONTACT_PROTECTION_REPORT.md) - **Phase 2 : Protection des contacts**
- [`PHASE2_FIX_SPECIFICATIONS.md`](PHASE2_FIX_SPECIFICATIONS.md) - **Phase 2 : Spécifications détaillées**
- [`ENHANCED_SYSTEM_STATUS.md`](ENHANCED_SYSTEM_STATUS.md) - **Status implémentation système**

### 📈 Suivi et documentation

- [`RAPPORT_PROGRESSION.md`](RAPPORT_PROGRESSION.md) - **Rapport de progression du projet**
- [`PROMPT_REPRISE.md`](PROMPT_REPRISE.md) - **Prompt de reprise pour IA**

---

## 🎯 Navigation rapide par rôle

### **👤 Utilisateur final**
```
1. COMMENT_LANCER.md
2. README_WEASYPRINT.md (si besoin d'export PDF)
3. UI_UX_GUIDE.md (pour comprendre l'interface)
```

### **👨‍💻 Développeur**
```
1. STRUCTURE.md (architecture)
2. UTF8_ENCODING_GUIDE.md (bonnes pratiques)
3. AGENTS.md (conventions du projet)
4. CV_EXTRACTION_ENHANCEMENTS.md (votre domaine spécifique)
```

### **🤖 Développeur ML**
```
1. MODELES_IA.md
2. CONFIG_MODELS.md
3. CV_EXTRACTION_ENHANCEMENTS.md
4. FRENCH_DATE_PARSING_README.md
```

### **🎨 Designer UI/UX**
```
1. UI_UX_GUIDE.md
2. INTEGRATION_ML_UI.md
3. GUI_ARCHITECTURE.md
```

### **🔧 DevOps/Infrastructure**
```
1. README_VENV.md
2. COMMENT_LANCER.md
3. README_WEASYPRINT.md
4. OPTIMIZATIONS.md
```

### **🐛 QA/Testing**
```
1. TESTS_EXTRACTION.md
2. remediation/TEST_REMEDIATION_REPORT.md
3. SYNTAX_ERROR_PREVENTION.md
```

---

## 📦 Archive historique

Les fichiers suivants ont été archivés dans `ARCHIVE/` :

- `MOJIBAKE_FIX_LOG_2025-09-12.md` - Log mojibake daté
- `MOJIBAKE_FIX_TODAY.md` - Session jour mojibake
- `NOUVELLE_STRUCTURE.md` - Réorganisation obsolète
- `ORGANIZATION.md` - Version EN obsolète
- `LANCEURS_SAUVEGARDE.md` - Lanceurs historiques

**Accédez via**: [`docs/ARCHIVE/`](ARCHIVE/)

---

## 📝 Consolidations récentes (Novembre 2025)

### Fusions effectuées

| Avant | Après | Notes |
|-------|-------|-------|
| 3 docs UTF-8/Mojibake | [`UTF8_ENCODING_GUIDE.md`](UTF8_ENCODING_GUIDE.md) | Consolidation complète (652 lignes) |
| 2 docs WeasyPrint | [`README_WEASYPRINT.md`](README_WEASYPRINT.md) | Installation + dépannage (323 lignes) |

### Bénéfices

- ✅ Réduction de 19% des fichiers docs (43 → 35)
- ✅ Élimination des doublons
- ✅ Structure logique et hiérarchique
- ✅ Navigation claire par rôle
- ✅ Historique préservé via ARCHIVE/

---

## 🔗 Ressources externes

- [Documentation officielle Python](https://docs.python.org/)
- [WeasyPrint Official](https://doc.courtbouillon.org/weasyprint/)
- [PySide6 Documentation](https://doc.qt.io/qtforpython-6/)
- [PyTorch Documentation](https://pytorch.org/docs/)
- [HuggingFace Transformers](https://huggingface.co/docs/transformers/)

---

## 💬 Besoin d'aide?

1. **Pour lancer CVMatch**: [`COMMENT_LANCER.md`](COMMENT_LANCER.md)
2. **Pour développer**: [`STRUCTURE.md`](STRUCTURE.md) + [`AGENTS.md`](AGENTS.md)
3. **Pour les erreurs d'encodage**: [`UTF8_ENCODING_GUIDE.md`](UTF8_ENCODING_GUIDE.md)
4. **Pour WeasyPrint**: [`README_WEASYPRINT.md`](README_WEASYPRINT.md)

---

**Documentation centralisée et simplifiée** 📚✨
