# PATCH-PII: Utilitaires de masquage et redaction des données sensibles
import hashlib
import re
import os
from pathlib import Path
from typing import Callable, Any

def stable_token(text: str, salt: str, prefix: str = "PII", kind: str = "GEN") -> str:
    """Génère un token stable et non ré-identifiant pour une donnée PII.
    
    Args:
        text: Texte à tokeniser
        salt: Sel pour le hachage
        prefix: Préfixe du token
        kind: Type de PII (NAME, EMAIL, TEL, etc.)
    
    Returns:
        Token stable du format PII-KIND-HASH10
    """
    if not text:
        return f"{prefix}-{kind}-EMPTY"
    
    # Normaliser le texte pour éviter les variations mineures
    normalized = text.strip().lower()
    
    # Générer hash stable
    h = hashlib.sha256((salt + "|" + kind + "|" + normalized).encode("utf-8")).hexdigest()[:10]
    return f"{prefix}-{kind}-{h}"

def mask_keep_shape(text: str, keep: int = 2) -> str:
    """Masque un texte en préservant partiellement sa forme.
    
    Args:
        text: Texte à masquer
        keep: Nombre de caractères à conserver au début
    
    Returns:
        Texte masqué avec forme préservée
    """
    if not text:
        return text
    
    t = text.strip()
    if len(t) <= keep:
        return "*" * len(t)
    
    # Conserver la forme (espaces, ponctuation) mais masquer les lettres/chiffres
    masked = t[:keep] + "…"
    
    # Ajouter des * pour représenter la longueur sans révéler le contenu exact
    remaining_length = max(0, len(t) - keep - 1)
    if remaining_length > 0:
        # Limiter la longueur visible pour éviter la ré-identification
        visible_length = min(remaining_length, 8)
        masked += "*" * visible_length
        if remaining_length > visible_length:
            masked += "+"  # Indique qu'il y a plus de contenu
    
    return masked

def mask_email(email: str) -> str:
    """Masquage spécialisé pour emails."""
    if not email or "@" not in email:
        return mask_keep_shape(email)
    
    local, domain = email.split("@", 1)
    masked_local = local[:1] + "…" if local else "…"
    
    # Masquer le domaine mais garder le TLD
    if "." in domain:
        domain_parts = domain.split(".")
        masked_domain = domain_parts[0][:1] + "…." + domain_parts[-1]
    else:
        masked_domain = domain[:1] + "…"
    
    return f"{masked_local}@{masked_domain}"

def mask_phone(phone: str) -> str:
    """Masquage spécialisé pour numéros de téléphone."""
    if not phone:
        return phone
    
    # Nettoyer le numéro des caractères non-numériques pour compter les chiffres
    digits_only = re.sub(r'[^\d]', '', phone)
    
    if len(digits_only) <= 4:
        return "*" * len(phone)
    
    # Conserver les premiers et derniers caractères de format
    if len(phone) > 6:
        return phone[:2] + "…" + phone[-2:]
    else:
        return mask_keep_shape(phone, 1)

def redact_with_token(text: str, salt: str, kind: str, masker: Callable[[str], str] = mask_keep_shape) -> str:
    """Redacte un texte avec un token stable et un masquage.
    
    Args:
        text: Texte à redacter
        salt: Sel pour génération du token
        kind: Type de PII
        masker: Fonction de masquage à appliquer
    
    Returns:
        Texte redacté au format [TOKEN:masqué]
    """
    if not text:
        return text
    
    token = stable_token(text, salt=salt, kind=kind)
    masked = masker(text)
    return f"[{token}:{masked}]"

def truncate_for_log(s: str, max_chars: int) -> str:
    """Tronque une chaîne pour les logs en préservant la lisibilité.
    
    Args:
        s: Chaîne à tronquer
        max_chars: Nombre maximum de caractères
    
    Returns:
        Chaîne tronquée avec indicateur si nécessaire
    """
    if s is None:
        return s
    
    # Remplacer les sauts de ligne par un symbole visible
    s = s.replace("\n", "⏎").replace("\r", "")
    
    if len(s) <= max_chars:
        return s
    
    # Tronquer en essayant de couper à un espace si possible
    truncated = s[:max_chars]
    if max_chars > 10 and s[max_chars:max_chars+10]:  # Si il y a du contenu après
        last_space = truncated.rfind(' ')
        if last_space > max_chars * 0.8:  # Si l'espace n'est pas trop proche du début
            truncated = truncated[:last_space]
    
    return truncated + "…"

def safe_repr(obj: Any, max_chars: int = 100) -> str:
    """Représentation sûre d'un objet pour les logs.
    
    Évite l'exposition accidentelle de PII dans les repr d'objets.
    """
    if obj is None:
        return "None"
    
    if isinstance(obj, (str, int, float, bool)):
        return truncate_for_log(repr(obj), max_chars)
    
    if isinstance(obj, (list, tuple)):
        if len(obj) == 0:
            return repr(obj)
        return f"{type(obj).__name__}[{len(obj)} items]"
    
    if isinstance(obj, dict):
        if len(obj) == 0:
            return "{}"
        keys_sample = list(obj.keys())[:3]
        return f"dict[{len(obj)} keys: {keys_sample}...]"
    
    return f"{type(obj).__name__}(...)"

def sanitize_dict_for_log(d: dict, salt: str, sensitive_keys: set[str] = None) -> dict:
    """Assainit un dictionnaire pour les logs en redactant les clés sensibles.
    
    Args:
        d: Dictionnaire à assainir
        salt: Sel pour la redaction
        sensitive_keys: Ensemble des clés considérées comme sensibles
    
    Returns:
        Dictionnaire avec les valeurs sensibles redactées
    """
    if sensitive_keys is None:
        sensitive_keys = {
            'name', 'nom', 'email', 'phone', 'telephone', 'tel', 'address', 'adresse',
            'street', 'rue', 'city', 'ville', 'company', 'entreprise', 'school',
            'ecole', 'university', 'universite', 'institution', 'linkedin', 'github',
            'first_name', 'last_name', 'prenom', 'nom_famille', 'full_name'
        }
    
    sanitized = {}
    for key, value in d.items():
        key_lower = key.lower()
        
        if any(sensitive in key_lower for sensitive in sensitive_keys):
            if isinstance(value, str) and value:
                sanitized[key] = redact_with_token(value, salt, "FIELD")
            else:
                sanitized[key] = safe_repr(value)
        else:
            sanitized[key] = safe_repr(value) if isinstance(value, str) else value
    
    return sanitized


def safe_path_for_log(file_path: str, salt: str = "cvmatch_path_salt_2025") -> str:
    """Anonymise un chemin de fichier pour les logs en préservant structure utile.
    
    Transforme: C:/Users/username/Downloads/CV_Test_User.pdf
    En: C:/Users/[USER-abc123]/Downloads/CV_[FILENAME-def456].pdf
    
    Args:
        file_path: Chemin complet à anonymiser
        salt: Sel pour la génération de tokens
        
    Returns:
        Chemin anonymisé préservant la structure
    """
    if not file_path or not isinstance(file_path, str):
        return str(file_path)
    
    try:
        path = Path(file_path)
        parts = path.parts
        
        anonymized_parts = []
        for i, part in enumerate(parts):
            if i == 0:  # Drive letter / root
                anonymized_parts.append(part)
            elif 'Users' in part or 'user' in part.lower():
                anonymized_parts.append('Users')  # Préserver structure
            elif i > 0 and 'Users' in parts[i-1]:  # Username après Users/
                user_token = stable_token(part, salt, prefix="USER", kind="NAME")[:8]
                anonymized_parts.append(f"[{user_token}]")
            elif path.suffix and part == path.name:  # Nom de fichier final
                filename_no_ext = path.stem
                extension = path.suffix
                filename_token = stable_token(filename_no_ext, salt, prefix="FILE", kind="NAME")[:8] 
                anonymized_parts.append(f"[{filename_token}]{extension}")
            else:  # Dossiers intermédiaires
                anonymized_parts.append(part)
        
        return str(Path(*anonymized_parts))
        
    except Exception:
        # En cas d'erreur, anonymisation basique
        return f"[PATH-{stable_token(file_path, salt, kind='PATH')[:8]}]"


def safe_database_path_for_log(db_path: str) -> str:
    """Anonymise spécifiquement les chemins de base de données.
    
    Transforme: C:/Users/username/.cvmatch/cvmatch.db  
    En: C:/Users/[USER-abc123]/.cvmatch/cvmatch.db
    """
    return safe_path_for_log(db_path, salt="cvmatch_db_salt_2025")
