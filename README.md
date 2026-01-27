# CVMatch générateur de CV

CVMatch est une application desktop destinée à générer des CV et des lettres de motivation adaptées à votre profil. Les informations saisies sont conservés en local sur votre ordinateur uniquement. Aucune information n'est envoyé sur internet ou sur un cloud. 
Le seul moment où une connexion internet est requise est au moment de l'installation des dépendances python et les modèles IA. Autrement toutes les opérations se dérouleront sur l'application

# Warning
Je n'ai pour le moment réalisé aucun test sur la version Linux donc je ne peux pas garantir son bon fonctionnement.
Je n'ai même pas encore lancé l'application sur Linux et pour le moment je n'ai pas eu le temps de le faire.
La doc est obsolète faut que je pense à la màj un jour.


# Prérequis

## Prérequis techniques (avant de lancer quoi que ce soit)

- **Système d’exploitation** : Windows 10/11 **64-bit** (testé). Linux (non testé → peut nécessiter des ajustements).
- **Interface graphique** : environnement desktop requis.
- **CPU** : x86_64 (recommandé 4 cœurs+).
- **RAM** :
  - **IA CPU (LLM)** : 16–32 GB recommandés (selon le modèle).
- **Espace disque** :
  - **Base** : prévoir quelques GB (données runtime, logs, exports).
  - **IA** : prévoir **10–50+ GB** selon les modèles téléchargés (cache Hugging Face en `.hf_cache/`).

## Logiciels à préinstaller

- **Python** : **3.10+** (idéalement 3.10 à 3.13) installé et accessible via `python` dans le PATH.
  - Requis aussi : `pip` + module `venv` (en général inclus avec Python).

## Prérequis IA (optionnel, mais recommandé si tu veux de la génération LLM)

- **GPU** : NVIDIA compatible CUDA. (je n'ai pas testé avec des GPU hors Nvidia faute de matériel)
  - GPU minimum la série 40xx.
- **Pilotes NVIDIA** : à jour (pour que PyTorch puisse détecter CUDA).
  - Le projet référence des builds PyTorch **CUDA 12.1 (cu121)** : avoir ses driver à jours NVIDIA c'est important.

> Note : CVMatch peut fonctionner **sans GPU** (mode CPU), mais ce sera plus lent et certains modèles seront inadaptés et surtout vous risquez d'user plus vite votre CPU.

## Prérequis “fonctionnels” selon les features (optionnels)

- **Export PDF avancé (WeasyPrint)** :
  - Sur Windows, WeasyPrint peut nécessiter des **bibliothèques natives** (Cairo/Pango/Harfbuzz, etc.).
  - Sur Linux, j'ai pas testé sur un PC Linux pour le moment.

# Guide d'utilisation

Pour **Windows**, utilisez les fichiers en `.bat`. Pour **Linux**, utilisez les fichiers en `.sh`.

## Premier démarrage (recommandé)

1) **Installer les dépendances (minimum)**
- **Windows** : lancez `installation_cvmatch_windows.bat`
- **Linux/macOS** : lancez `installation_cvmatch_linux.sh`

2) **Installer l’IA**
- **Windows** : lancez `installation_cvmatch_ai_windows.bat`
- **Linux/macOS** : lancez `installation_cvmatch_ai_linux.sh`

Notes IA :
- Les modèles sont téléchargés dans le cache Hugging Face (par défaut `./.hf_cache/`).
- Le **modèle LLM par défaut** configuré par l’installateur est **`Qwen/Qwen2.5-0.5B-Instruct`** (léger).
- D’autres LLM peuvent être utilisés (ex : `mistralai/Mistral-7B-Instruct-v0.3`, `Qwen/Qwen2.5-7B-Instruct`) selon votre machine et vos réglages.

3) **Lancer l’application**
- **Windows** : `cvmatch.bat`
- **Linux** : `cvmatch.sh`

Un terminal s’ouvre : il affiche les étapes (création/activation du venv, vérifications, etc.) et écrit des logs dans `./logs/sessionlog/`.

> Astuce : même sans lancer les installateurs manuellement, `cvmatch.bat` / `cvmatch.sh` tentent de gérer le venv et peuvent lancer l’installation des dépendances si nécessaire.

Utilisez l'installateur adapté à votre système d'exploitation
Vous pouvez lancer directement `cvmatch.bat` / `cvmatch.sh` :
- le venv est créé si nécessaire,
- les dépendances sont vérifiées (et l’installateur peut être lancé automatiquement),
- si les modèles IA sont absents, l’installation peut vous être proposée.

N'hésitez pas à installer l'IA.

- Les 2 modèles préentraîné installé sont :  Qwen2.5-0.5B-Instruct et Mistral 7B
- Utilisez le fichier CVmatch.bat ou cvmatch.sh  pour lancer l'application
- Un terminal s'ouvrira sur lequel vous pourrez suivre chaque étape de lancement de 
l'application.
  - Le bouton "Activer l'apprentissage automatique" ne fait rien vous pouvez l'activer ou le 
   désactiver il ne fait actuellement rien du tout pour le moment, l'idée derrière ce bouton 
   était d'améliorer l'IA et ses outputs en comparant les précédents résultats pour mieux 
   générer le suivant. Pour le moment cette idée restera sur le côté.
- Une fois l'application lancé renseignez les informations minimales demandés.
- Le format de fichier acceptés est le format PDF.
- Une fois les premières étapes d'initialisations terminées l'application se lancera normalement.


## Dans l’application (après lancement)
### Premier Lancement 
- **Renseignez les informations minimales** demandées lors de l’initialisation (profil).
- **Import (optionnel)** : CV / LinkedIn au **format PDF uniquement**.
- Le bouton apprentissage automatique ne sert aujourd'hui à rien, je vais réfléchir à le retirer ou à le garder en fonction de comment je fais évoluer le projet
### Page d'arriver pour tout futur lancement  post-Premier Lancement
- Après import, allez dans **"Visualiser le détail"** pour **vérifier/corriger** les informations extraites, puis complétez votre profil. Relancez l'extraction avec le bouton "Extraire le CV" et "Extraire Linkedin".

## Générer un CV pour une offre

1) Une fois votre profil complété, allez sur **Nouvelle candidature**.
2) Utilisez **"Générer le CV"** pour produire une version adaptée à l’offre.
3) Vous pouvez ensuite **prévisualiser** le CV et **l’éditer**.
   - L’éditeur est une zone de texte **HTML** : vous pouvez modifier le contenu librement.
   - Ne modifiez les **balises** que si vous savez ce que vous faites.
4) Sélectionnez un **modèle** puis exportez en **PDF**.

## Historique
1) Une fois le CV généré vous retrouverez une liste des CV sur la page historique sur laquelle normalement vous devriez pouvoir indiquer des scores et des indications pour dire si ce CV vous a permis d'obtenir un entretien ou non. (La fonctionnalité n'est pas encore implémenté, elle le fut pendant un temps pour l'apprentissage automatisé mais j'ai laissé tomber cette partie)

## Remarques (fonctionnalités en cours)

- Le bouton **"Activer l'apprentissage automatique"** est présent mais **n’a pas d’effet** pour le moment (fonctionnalité prévue plus tard).
- Le bouton **"Lettre de motivation"** n’est **pas encore fonctionnel** : privilégiez **"Générer le CV" qui va générer les 2**.
- Rajouter des vannes pendant la génération de CV pour rendre l'attente moins monotones.

## Différence entre Qwen et Mistral
Qwen a tendance à générer un CV bullet point avec une très bonne lettre de motivation.
Mistral va présenter dans un court texte votre profil au début puis lister les points importants de votre CV mais la lettre de motivation peut être plus hasardeux des tests que j'ai réalisé.
  

# Développement de l'application : 
- Moi, en développement assisté par de l'IA (à 90%+) et principal testeur
- GPT 5.2 Codex (et les versions précédentes j'ai oublié les noms)
- Claude Code Sonnet puis Opus 4.5
- Cursor et son mode agent
  
