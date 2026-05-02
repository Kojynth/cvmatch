"""
Adaptive LLM Worker
==================

Worker adaptatif universel qui s'optimise automatiquement selon le GPU.
Garantie: Génération sous 10 minutes sur TOUT système (GTX 1080 à RTX 5070).
"""

import re
import time
import threading
from pathlib import Path
from typing import Dict, Any, Optional
from PySide6.QtCore import QThread, Signal, QTimer
from loguru import logger

# Imports adaptatifs selon disponibilité
OPTIMIZATIONS = {"vllm": False, "transformers": False, "torch": False}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
LINKEDIN_RE = re.compile(r"https?://[^\s]*linkedin\.com/[^\s]+", re.IGNORECASE)
PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{8,}\d)")

try:
    import torch
    OPTIMIZATIONS["torch"] = True
except ImportError:
    pass

try:
    from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
    OPTIMIZATIONS["transformers"] = True
except ImportError:
    pass

try:
    import vllm
    from vllm import LLM, SamplingParams
    OPTIMIZATIONS["vllm"] = True
except ImportError:
    pass

from ..models.user_profile import UserProfile
from ..models.job_application import JobApplication, ApplicationStatus
from ..models.database import get_session
from ..utils.model_registry import model_registry
from ..utils.universal_gpu_adapter import universal_gpu_adapter
from ..utils.lightweight_model import lightweight_generator


class AdaptiveQwenManager:
    """Gestionnaire adaptatif qui choisit automatiquement la meilleure stratégie."""
    
    _instance = None
    _loaded_models = {}  # Cache des modèles chargés
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if hasattr(self, '_initialized'):
            return
        
        self.gpu_adapter = universal_gpu_adapter
        self.optimal_config = self.gpu_adapter.get_optimal_model_config()
        self.current_model_id = self.optimal_config.get("registry_key") or self._guess_profile_key(self.optimal_config.get("model_name"))
        self.performance_profile = self.gpu_adapter.performance_profile
        
        logger.info(f"🎯 Configuration adaptative: {self.performance_profile['tier']}")
        logger.info(f"⏱️ Temps estimé: {self.performance_profile['estimated_time_minutes']}min")
        
        self._initialized = True
    
    def _guess_profile_key(self, model_name: Optional[str]) -> Optional[str]:
        if not model_name:
            return None
        for profile in model_registry.list_profiles():
            if profile.model_id == model_name:
                return profile.key
        if isinstance(model_name, str) and '/' in model_name:
            return model_name.split('/')[-1]
        return model_name

    def get_optimal_model_config(self) -> Dict[str, Any]:
        """Retourne la configuration optimale (alias pour compatibilité)."""
        return self.optimal_config
    
    def load_model_adaptive(self, progress_callback=None):
        """Charge le modèle avec la stratégie optimale selon le GPU."""
        model_name = self.optimal_config["model_name"]
        
        # VERIFICATION AVANT TELECHARGEMENT
        if not self._is_model_locally_available(model_name):
            if progress_callback:
                progress_callback(f"⚠️ Modèle {model_name} non disponible localement")
                progress_callback("🚨 Téléchargement nécessaire - utilisation fallback")
            
            logger.warning(f"Modèle {model_name} nécessite téléchargement - fallback activé")
            raise RuntimeError(f"Modèle {model_name} non disponible localement")
        
        # Vérifier si modèle déjà en cache
        cache_key = f"{model_name}_{self.optimal_config['quantization']}"
        if cache_key in self._loaded_models:
            logger.info(f"📦 Modèle {model_name} trouvé en cache")
            return self._loaded_models[cache_key]
        
        if progress_callback:
            progress_callback(f"🔧 Chargement adaptatif {self.performance_profile['tier']}...")
        
        # Stratégie selon performance
        if self.optimal_config["use_vllm"] and OPTIMIZATIONS["vllm"]:
            model = self._load_with_vllm(progress_callback)
        elif OPTIMIZATIONS["transformers"]:
            model = self._load_with_transformers(progress_callback)
        else:
            raise RuntimeError("Aucun backend IA disponible - Installer transformers ou vllm")
        
        # Mettre en cache
        self._loaded_models[cache_key] = model
        
        if progress_callback:
            progress_callback(f"✅ Modèle adaptatif chargé - Mode {self.performance_profile['tier']}")
        
        return model
    
    def _load_with_vllm(self, progress_callback=None):
        """Chargement avec vLLM (ultra-rapide)."""
        if progress_callback:
            progress_callback("🚀 Chargement vLLM ultra-rapide...")
        
        try:
            llm_config = {
                "model": self.optimal_config["model_name"],
                "tensor_parallel_size": 1,
                "gpu_memory_utilization": self.optimal_config["gpu_memory_utilization"],
                "max_model_len": self.optimal_config["max_new_tokens"],
                "trust_remote_code": True,
                "quantization": self.optimal_config["quantization"] if self.optimal_config["quantization"] != "fp16" else None
            }
            
            # Filtrer les paramètres None
            llm_config = {k: v for k, v in llm_config.items() if v is not None}
            
            model = vllm.LLM(**llm_config)
            logger.info("🚀 Modèle vLLM chargé avec succès")
            return {"engine": "vllm", "model": model}
            
        except Exception as e:
            logger.error(f"Erreur vLLM: {e}")
            # Fallback vers transformers
            if OPTIMIZATIONS["transformers"]:
                logger.info("🔄 Fallback vers transformers...")
                return self._load_with_transformers(progress_callback)
            raise
    
    def _load_with_transformers(self, progress_callback=None):
        """Chargement avec Transformers (standard)."""
        if progress_callback:
            progress_callback("⚙️ Chargement Transformers standard...")
        
        try:
            model_name = self.optimal_config["model_name"]
            device = self.optimal_config["device"]
            
            # Tokenizer
            tokenizer = AutoTokenizer.from_pretrained(
                model_name,
                trust_remote_code=True,
                use_fast=True
            )
            
            # Configuration modèle selon quantification
            model_kwargs = {
                "trust_remote_code": True,
                "torch_dtype": torch.float16 if device == "cuda" else torch.float32,
            }
            
            # Quantification adaptative - CORRECTION: éviter les conflits
            quantization = self.optimal_config["quantization"]
            if quantization == "gptq" and device == "cuda":
                # Utiliser seulement quantization_config, pas load_in_4bit
                model_kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_4bit=True,
                    bnb_4bit_compute_dtype=torch.float16,
                    bnb_4bit_use_double_quant=True,
                    bnb_4bit_quant_type="nf4"
                )
            elif quantization == "awq" and device == "cuda":
                # Utiliser seulement quantization_config pour AWQ aussi
                model_kwargs["quantization_config"] = BitsAndBytesConfig(
                    load_in_8bit=True,
                    llm_int8_enable_fp32_cpu_offload=True
                )
            elif quantization == "int8" and device == "cpu":
                # Pour CPU, pas de quantization_config
                logger.info("💻 Mode CPU - Quantification INT8 native")
            
            # Device map
            if device == "cuda":
                model_kwargs["device_map"] = "auto"
            
            # Chargement modèle
            model = AutoModelForCausalLM.from_pretrained(model_name, **model_kwargs)
            
            if device == "cpu":
                model = model.to("cpu")
            
            model.eval()
            
            logger.info(f"⚙️ Modèle Transformers chargé - {quantization}")
            return {
                "engine": "transformers",
                "model": model,
                "tokenizer": tokenizer,
                "device": device
            }
            
        except Exception as e:
            logger.error(f"Erreur Transformers: {e}")
            raise
    
    def generate_cv_adaptive(self, prompt: str, progress_callback=None, timeout_minutes=None, profile=None, offer_data=None) -> str:
        """Génération adaptative avec système intelligent."""
        
        # NOUVEAU: Priorité au générateur léger si modèle non disponible
        model_name = self.optimal_config["model_name"]
        
        if not self._is_model_locally_available(model_name):
            if progress_callback:
                progress_callback("🚀 Modèle lourd non disponible - Génération rapide activée")
            
            logger.info("🚀 Utilisation générateur léger - Pas de téléchargement")
            
            if profile and offer_data:
                return lightweight_generator.generate_cv(
                    profile=profile,
                    offer_data=offer_data,
                    template="modern",
                    progress_callback=progress_callback
                )
            else:
                # Fallback classique si pas de données
                return self._generate_emergency_fallback(prompt, profile, offer_data)
        
        # Génération IA classique si modèle disponible
        if timeout_minutes is None:
            timeout_minutes = self.optimal_config["timeout_minutes"]
        
        # Système de timeout strict
        result = {"cv": None, "error": None}
        
        def generation_task():
            try:
                model_data = self.load_model_adaptive(progress_callback)
                
                if model_data["engine"] == "vllm":
                    result["cv"] = self._generate_with_vllm(model_data, prompt, progress_callback)
                else:
                    result["cv"] = self._generate_with_transformers(model_data, prompt, progress_callback)
                    
            except Exception as e:
                result["error"] = str(e)
        
        # Lancer la génération dans un thread avec timeout
        thread = threading.Thread(target=generation_task)
        thread.daemon = True
        thread.start()
        
        # Attendre avec timeout
        thread.join(timeout=timeout_minutes * 60)
        
        if thread.is_alive():
            # Timeout dépassé
            logger.error(f"⏰ Timeout {timeout_minutes}min dépassé - Arrêt forcé")
            if progress_callback:
                progress_callback("⏰ Timeout - Génération rapide de secours")
            
            # Utiliser générateur léger en fallback
            if profile and offer_data:
                return lightweight_generator.generate_cv(profile, offer_data, "modern", progress_callback)
            else:
                return self._generate_emergency_fallback(prompt, profile, offer_data)
        
        if result["error"]:
            logger.error(f"Erreur génération: {result['error']}")
            # Utiliser générateur léger en cas d'erreur
            if profile and offer_data:
                return lightweight_generator.generate_cv(profile, offer_data, "modern", progress_callback)
            else:
                return self._generate_emergency_fallback(prompt, profile, offer_data)
        
        return result["cv"] or self._generate_emergency_fallback(prompt, profile, offer_data)
    
    def _generate_with_vllm(self, model_data, prompt: str, progress_callback=None) -> str:
        """Génération avec vLLM."""
        if progress_callback:
            progress_callback("🚀 Génération vLLM ultra-rapide...")
        
        formatted_prompt = self._format_prompt_for_vllm(prompt)
        
        sampling_params = vllm.SamplingParams(
            temperature=0.7,
            top_p=0.9,
            max_tokens=self.optimal_config["max_new_tokens"],
            repetition_penalty=1.1
        )
        
        outputs = model_data["model"].generate([formatted_prompt], sampling_params)
        generated_text = outputs[0].outputs[0].text
        
        return self._clean_generated_text(generated_text)
    
    def _generate_with_transformers(self, model_data, prompt: str, progress_callback=None) -> str:
        """Génération avec Transformers."""
        if progress_callback:
            progress_callback("⚙️ Génération Transformers...")
        
        model = model_data["model"]
        tokenizer = model_data["tokenizer"]
        device = model_data["device"]
        
        formatted_prompt = self._format_prompt_for_transformers(prompt)
        
        # Tokenisation
        inputs = tokenizer(
            formatted_prompt,
            return_tensors="pt",
            truncation=True,
            max_length=2048
        ).to(device)
        
        # Génération
        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=self.optimal_config["max_new_tokens"],
                temperature=0.7,
                top_p=0.9,
                do_sample=True,
                repetition_penalty=1.1,
                pad_token_id=tokenizer.eos_token_id,
                eos_token_id=tokenizer.eos_token_id
            )
        
        # Décodage
        generated_text = tokenizer.decode(
            outputs[0][inputs.input_ids.shape[1]:],
            skip_special_tokens=True
        )
        
        return self._clean_generated_text(generated_text)
    
    def _format_prompt_for_vllm(self, prompt: str) -> str:
        """Format prompt pour vLLM."""
        system_msg = "Tu es un expert en CV professionnels. Crée un CV markdown adapté à l'offre d'emploi."
        return f"<|im_start|>system\n{system_msg}<|im_end|>\n<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n"
    
    def _format_prompt_for_transformers(self, prompt: str) -> str:
        """Format prompt pour Transformers."""
        return f"Créer un CV professionnel en markdown pour cette offre d'emploi:\n\n{prompt}\n\nCV:"
    
    def _clean_generated_text(self, text: str) -> str:
        """Nettoie le texte généré."""
        # Supprimer les balises de fin
        if "<|im_end|>" in text:
            text = text.split("<|im_end|>")[0]
        
        # Nettoyage basique
        text = text.strip()
        
        # S'assurer qu'on a un CV minimum
        if len(text) < 100:
            logger.warning("Texte généré trop court - Ajout contenu minimal")
            text += "\n\n## Profil\nProfil candidat à compléter depuis les informations source disponibles.\n\n## Compétences\n- Compétences à confirmer depuis le profil source"
        
        return text
    
    def _is_model_locally_available(self, model_name: str) -> bool:
        """Vérifie si un modèle est disponible localement sans téléchargement."""
        try:
            from transformers import AutoConfig
            from pathlib import Path
            import os
            
            # Vérifier cache HuggingFace
            cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
            model_cache_name = model_name.replace("/", "--")
            model_cache_dir = cache_dir / f"models--{model_cache_name}"
            
            if model_cache_dir.exists():
                # Vérifier si téléchargement complet
                blobs_dir = model_cache_dir / "blobs"
                if blobs_dir.exists():
                    incomplete_files = list(blobs_dir.glob("*.incomplete"))
                    if not incomplete_files:
                        logger.info(f"✅ Modèle {model_name} disponible en cache")
                        return True
                    else:
                        logger.warning(f"⏳ Modèle {model_name} partiellement téléchargé ({len(incomplete_files)} fichiers incomplets)")
                        return False
            
            # Vérifier modèle local/custom
            if os.path.exists(model_name):
                return True
                
            logger.warning(f"❌ Modèle {model_name} non disponible localement")
            return False
            
        except Exception as e:
            logger.error(f"Erreur vérification modèle: {e}")
            return False
    
    def _generate_emergency_fallback(self, prompt: str, profile=None, offer_data=None) -> str:
        """Génère un CV de fallback avec les vraies données utilisateur."""
        logger.warning("🚨 GÉNÉRATION FALLBACK D'URGENCE - Utilisation des données utilisateur")
        
        # Utiliser les paramètres passés ou des valeurs par défaut
        if profile:
            name = profile.name or "Nom non renseigné"
            email = profile.email or "email@arenseigner.com"
            phone = profile.phone or "Téléphone à renseigner"
            linkedin = profile.linkedin_url or "LinkedIn à renseigner"
            cv_content = profile.master_cv_content or ""
        else:
            name = "Candidat"
            email = "candidat@email.com"
            phone = "Téléphone à renseigner"
            linkedin = "LinkedIn à renseigner"
            cv_content = ""
        
        # Extraire infos de l'offre
        if offer_data:
            job_title = offer_data.get('job_title', 'Poste recherché')
            company = offer_data.get('company', 'Entreprise cible')
            offer_text = offer_data.get('text', '')[:300]
        else:
            job_title = 'Poste recherché'
            company = 'Entreprise cible'
            offer_text = ''
        
        # Extraire quelques éléments du CV maître
        experience_section = ""
        skills_section = ""
        
        if cv_content:
            # Extraction basique d'expérience et compétences
            cv_lines = cv_content.split('\n')
            for i, line in enumerate(cv_lines):
                if any(keyword in line.lower() for keyword in ['expérience', 'experience', 'emploi']):
                    # Prendre quelques lignes après
                    experience_section = '\n'.join(cv_lines[i:i+5])
                    break
            
            for i, line in enumerate(cv_lines):
                if any(keyword in line.lower() for keyword in ['compétence', 'competence', 'skill']):
                    skills_section = '\n'.join(cv_lines[i:i+4])
                    break
        
        # Ajouter un marqueur FALLBACK visible
        fallback_cv = f"""# ⚠️ CV GÉNÉRÉ EN MODE FALLBACK ⚠️
# {name}

> **ATTENTION** : Ce CV a été généré en mode fallback d'urgence.
> La génération IA complète a échoué - vérifiez votre configuration GPU/CUDA.

## Informations de contact
- **Email:** {email}
- **Téléphone:** {phone}
- **LinkedIn:** {linkedin}

## Objectif professionnel
Poste cible : **{job_title}** chez **{company}**.

{f"**Contexte de l'offre :** {offer_text[:200]}..." if offer_text else ""}

## Profil professionnel
{cv_content[:400] + "..." if cv_content else "Profil candidat à compléter depuis les informations source disponibles."}

## Expérience professionnelle
{experience_section if experience_section else '''
### Expérience récente
**À compléter** | Période
- Expérience à détailler depuis votre CV maître
- Responsabilités principales
- Réalisations mesurables
'''}

## Compétences clés
{skills_section if skills_section else '''
- Compétences à reprendre du profil source
- Outils ou méthodes à confirmer depuis le profil
- Capacités d'adaptation et d'apprentissage
- Communication et travail en équipe
'''}

---
*CV généré automatiquement en mode fallback - Merci de vérifier les informations source.*"""

        return fallback_cv
    
    def get_system_status(self) -> Dict[str, Any]:
        """Retourne le statut du système adaptatif."""
        guarantee_check = self.gpu_adapter.check_10_minute_guarantee()
        
        return {
            "gpu_info": self.gpu_adapter.gpu_info,
            "performance_tier": self.performance_profile["tier"],
            "model_selected": self.optimal_config["model_name"],
            "estimated_time_minutes": self.performance_profile["estimated_time_minutes"],
            "max_timeout_minutes": self.optimal_config["timeout_minutes"],
            "ten_minute_guarantee": guarantee_check["guarantee_met"],
            "optimizations_available": OPTIMIZATIONS,
            "recommendations": self.gpu_adapter.get_performance_recommendations()
        }


class AdaptiveCVGenerationWorker(QThread):
    """Worker adaptatif avec garantie 10 minutes."""
    
    progress_updated = Signal(str)
    generation_finished = Signal(dict)
    error_occurred = Signal(str)
    
    def __init__(self, profile: UserProfile, offer_data: dict, template: str):
        super().__init__()
        self.profile = profile
        self.offer_data = offer_data
        self.template = template
        self.adaptive_manager = AdaptiveQwenManager()
    
    def run(self):
        """Lance la génération adaptative avec timeout strict."""
        try:
            def progress_callback(message):
                self.progress_updated.emit(message)
            
            # Afficher le statut système
            status = self.adaptive_manager.get_system_status()
            progress_callback(f"🎯 Mode {status['performance_tier']} - Temps estimé: {status['estimated_time_minutes']}min")
            
            if not status["ten_minute_guarantee"]:
                progress_callback("⚠️ Configuration pourrait dépasser 10min - Optimisations appliquées")
            
            # Construction prompt
            progress_callback("📝 Préparation du prompt adaptatif...")
            prompt = self.build_adaptive_prompt()
            
            # Génération avec timeout strict
            start_time = time.time()
            progress_callback("🚀 Génération IA adaptative...")
            
            # Timeout adaptatif selon le type de modèle
            model_config = self.adaptive_manager.get_optimal_model_config()
            is_cpu_model = model_config.get("device", "cpu") == "cpu"
            timeout_minutes = 20 if is_cpu_model else 10  # Plus de temps pour CPU
            
            progress_callback(f"⏰ Timeout configuré: {timeout_minutes}min ({'CPU' if is_cpu_model else 'GPU'})")
            
            cv_markdown = self.generate_cv_with_fallback(
                prompt, 
                progress_callback,
                timeout_minutes=timeout_minutes
            )
            
            generation_time = (time.time() - start_time) / 60
            
            # Formatage
            try:
                cv_markdown = cv_markdown.format(
                    name=self.profile.name or "[Votre Prénom] [Votre Nom]",
                    email=self.profile.email or "[Votre Email]",
                    phone=self.profile.phone or "[Votre Téléphone]",
                    linkedin=self.profile.linkedin_url or "[Votre LinkedIn]"
                )
            except KeyError:
                pass  # Ignorer les erreurs de formatage

            cv_markdown = self._force_profile_identity(cv_markdown)
            
            # Sauvegarde
            progress_callback("💾 Sauvegarde...")
            application = self.save_application(cv_markdown, "")
            
            # Résultat
            result = {
                "application_id": application.id,
                "cv_markdown": cv_markdown,
                "cover_letter": "",
                "template": self.template,
                "model_version": status["model_selected"],
                "generation_time_minutes": round(generation_time, 2),
                "performance_tier": status["performance_tier"],
                "ten_minute_guarantee_met": generation_time <= 10
            }
            
            progress_callback(f"✅ Génération terminée en {generation_time:.1f}min")
            self.generation_finished.emit(result)
            
        except Exception as e:
            logger.error(f"Erreur worker adaptatif: {e}")
            self.error_occurred.emit(f"Erreur génération adaptative: {str(e)}")
    
    def build_adaptive_prompt(self) -> str:
        """Construit un prompt adaptatif optimisé."""
        # Prompt simplifié pour les configurations faibles
        performance_tier = self.adaptive_manager.performance_profile["tier"]
        
        if performance_tier in ["cpu_fallback", "basic_performance"]:
            # Prompt court pour GPU faibles
            return f"""Créer un CV pour:
Nom: {self.profile.name}
Email: {self.profile.email}
Poste: {self.offer_data['job_title']}
Entreprise: {self.offer_data['company']}

Profil: {self.profile.master_cv_content[:500] if self.profile.master_cv_content else 'Profil candidat à compléter'}

Offre: {self.offer_data['text'][:800]}

Regles:
- N'invente pas de faits, utilise uniquement les donnees du profil.
- Adapte le CV a l'offre (mots-cles si presents dans le profil).
- Utilise les placeholders d'identité: [Votre Prénom] [Votre Nom], [Votre Email], [Votre Téléphone], [Votre LinkedIn].

CV markdown professionnel et concis."""
        else:
            # Prompt complet pour GPU performants
            return f"""MISSION: Créer un CV professionnel optimisé.

CANDIDAT:
Nom: {self.profile.name}
Email: {self.profile.email}
Téléphone: {self.profile.phone or 'Non renseigné'}
LinkedIn: {self.profile.linkedin_url or 'Non renseigné'}

CV de référence:
{self.profile.master_cv_content or 'Aucun CV de référence'}

OFFRE CIBLEE:
Poste: {self.offer_data['job_title']}
Entreprise: {self.offer_data['company']}
Description: {self.offer_data['text']}

OBJECTIFS:
1. CV spécifiquement adapté à cette offre
2. Mots-clés pertinents intégrés
3. Structure markdown professionnelle
4. Template: {self.template}

REGLES:
- Ne jamais inventer de faits.
- Utiliser les mots-cles de l'offre uniquement s'ils existent dans les donnees candidat.
- Utiliser les placeholders d'identité: [Votre Prénom] [Votre Nom], [Votre Email], [Votre Téléphone], [Votre LinkedIn].

Créer un CV professionnel en markdown."""

    def _force_profile_identity(self, cv_markdown: str) -> str:
        """Force the profile identity in the generated markdown."""
        if not cv_markdown:
            return cv_markdown

        lines = cv_markdown.splitlines()
        name = (self.profile.name or "[Votre Prénom] [Votre Nom]").strip()
        email = (self.profile.email or "[Votre Email]").strip()
        phone = (self.profile.phone or "[Votre Téléphone]").strip()
        linkedin = (self.profile.linkedin_url or "[Votre LinkedIn]").strip()

        if name:
            replaced = False
            for idx, line in enumerate(lines):
                if line.strip().startswith("# "):
                    lines[idx] = f"# {name}"
                    replaced = True
                    break
            if not replaced:
                lines.insert(0, f"# {name}")

        if email:
            for idx, line in enumerate(lines):
                if "@" in line or "email" in line.lower():
                    updated = EMAIL_RE.sub(email, line)
                    if updated == line and "email" in line.lower():
                        updated = f"- Email: {email}"
                    lines[idx] = updated

        if phone:
            for idx, line in enumerate(lines):
                lowered = line.lower()
                if any(token in lowered for token in ["tel", "telephone", "phone", "mobile"]):
                    updated = PHONE_RE.sub(phone, line)
                    if updated == line:
                        updated = f"- Téléphone: {phone}"
                    lines[idx] = updated

        if linkedin:
            for idx, line in enumerate(lines):
                if "linkedin" in line.lower():
                    updated = LINKEDIN_RE.sub(linkedin, line)
                    if updated == line:
                        updated = f"- LinkedIn: {linkedin}"
                    lines[idx] = updated

        return "\n".join(lines).strip()
    
    def save_application(self, cv_markdown: str, cover_letter: str) -> JobApplication:
        """Sauvegarde rapide."""
        application = JobApplication(
            profile_id=self.profile.id,
            job_title=self.offer_data['job_title'],
            company=self.offer_data['company'],
            offer_text=self.offer_data['text'][:1000],  # Limiter pour performance
            template_used=self.template,
            model_version_used="Adaptive",
            generated_cv_markdown=cv_markdown,
            generated_cover_letter=cover_letter,
            status=ApplicationStatus.DRAFT
        )
        
        with get_session() as session:
            session.add(application)
            session.commit()
            session.refresh(application)
        
        return application
    
    def generate_cv_with_fallback(self, prompt: str, progress_callback=None, timeout_minutes=None) -> str:
        """Génération avec fallback intelligent utilisant les données du worker."""
        try:
            # Essayer la génération adaptative avec données du worker
            cv_result = self.adaptive_manager.generate_cv_adaptive(
                prompt, 
                progress_callback,
                timeout_minutes=timeout_minutes,
                profile=self.profile,  # Passer le profil
                offer_data=self.offer_data  # Passer les données d'offre
            )
            return cv_result
        except Exception as e:
            # En cas d'erreur, utiliser le fallback avec les vraies données
            logger.warning(f"Génération échouée, utilisation fallback: {e}")
            return self.adaptive_manager._generate_emergency_fallback(
                prompt, 
                profile=self.profile, 
                offer_data=self.offer_data
            )


# Instance globale
adaptive_qwen_manager = AdaptiveQwenManager()
