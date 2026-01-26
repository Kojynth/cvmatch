# Documentation des Modèles IA - CVMatch

## 📊 Évaluation de votre configuration




---

## 🤖 Modèles IA Supportés

### Modèles GPU (CUDA requis)

#### 🏆 **Qwen2.5-32B** (Premium)
- **HuggingFace :** https://huggingface.co/Qwen/Qwen2.5-32B-Instruct
- **VRAM :** 24GB+ requis
- **Qualité :** ⭐⭐⭐⭐⭐ (5/5)
- **Vitesse :** ⚡ (1/3)
- **Usage :** Candidatures critiques, qualité ultime
- **Quantification :** AWQ

#### 🥈 **Qwen2.5-14B** (Équilibré)
- **HuggingFace :** https://huggingface.co/Qwen/Qwen2.5-14B-Instruct
- **VRAM :** 8GB+ requis
- **Qualité :** ⭐⭐⭐⭐⭐ (5/5)
- **Vitesse :** ⚡⚡ (2/3)
- **Usage :** CV professionnels, excellente qualité
- **Quantification :** GPTQ

#### 🥉 **Qwen2.5-7B** (Rapide)
- **HuggingFace :** https://huggingface.co/Qwen/Qwen2.5-7B-Instruct
- **VRAM :** 4GB+ requis
- **Qualité :** ⭐⭐⭐⭐ (4/5)
- **Vitesse :** ⚡⚡ (2/3)
- **Usage :** Excellent équilibre qualité/vitesse
- **Quantification :** GPTQ
- **🎮 Compatible RTX 4050**

#### **Mistral-7B** (Léger)
- **HuggingFace :** https://huggingface.co/mistralai/Mistral-7B-Instruct-v0.2
- **VRAM :** 4GB+ requis
- **Qualité :** ⭐⭐⭐ (3/5)
- **Vitesse :** ⚡⚡⚡ (3/3)
- **Usage :** Génération CV standard, rapide
- **Quantification :** GPTQ
- **🎮 Compatible RTX 4050**

### Modèles CPU (Sans GPU)

#### 🏆 **Phi-3-Mini** (CPU Premium)
- **HuggingFace :** https://huggingface.co/microsoft/Phi-3-mini-4k-instruct
- **GitHub :** https://github.com/microsoft/Phi-3
- **RAM :** Optimisé pour toute config
- **Qualité :** ⭐⭐⭐⭐ (4/5)
- **Vitesse :** ⚡⚡⚡ (3/3)
- **Usage :** Modèle Microsoft optimisé CPU
- **Quantification :** INT8

#### **Qwen2.5-1.5B** (CPU Équilibré)
- **HuggingFace :** https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct
- **RAM :** 8GB+ recommandé
- **Qualité :** ⭐⭐⭐⭐ (4/5)
- **Vitesse :** ⚡⚡ (2/3)
- **Usage :** Version légère de Qwen
- **Quantification :** INT8

#### **TinyLlama** (CPU Ultra-rapide)
- **HuggingFace :** https://huggingface.co/TinyLlama/TinyLlama-1.1B-Chat-v1.0
- **GitHub :** https://github.com/jzhang38/TinyLlama
- **RAM :** 4GB+ suffisant
- **Qualité :** ⭐⭐⭐ (3/5)
- **Vitesse :** ⚡⚡⚡ (3/3)
- **Usage :** Modèle 1B ultra-léger
- **Quantification :** INT8

---

## 🎯 Recommandations pour votreConfiguration 

### Configuration Optimale
1. **Modèle recommandé :** Qwen2.5-7B ou Mistral-7B
2. **Quantification :** GPTQ 4-bit ou AWQ
3. **Moteur :** vLLM avec optimisations RTX 4050
4. **GPU Memory Utilization :** 85% max

### Optimisations Spéciales RTX 4050
- ✅ GGML Q4 quantization (recommandé pour 32B)
- ✅ AWQ quantization (équilibre vitesse/qualité)
- ✅ FlashAttention-2 si disponible
- ✅ Cache CUDA vidé régulièrement
- ✅ Surveillance température GPU

---

## 🔧 Technologies d'Optimisation

### Quantification
- **GPTQ :** https://github.com/IST-DASLab/gptq
- **AWQ :** https://github.com/mit-han-lab/llm-awq
- **GGML :** https://github.com/ggerganov/ggml

### Moteurs d'Inférence
- **vLLM :** https://github.com/vllm-project/vllm
- **ExLlamaV2 :** https://github.com/turboderp/exllamav2
- **ctranslate2 :** https://github.com/OpenNMT/CTranslate2

### Optimisations
- **FlashAttention :** https://github.com/Dao-AILab/flash-attention
- **xFormers :** https://github.com/facebookresearch/xformers

---

## 🚀 Mode d'Emploi

1. **Installation automatique :** `installer_windows.bat`
2. **Diagnostic CUDA :** `diagnostic_cuda.py`
3. **Test génération :** `debug_quick.py`
4. **Interface complète :** `main.py`

Le système détecte automatiquement votre hardware et sélectionne le modèle optimal !
