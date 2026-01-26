"""
Utilitaires de validation réutilisables pour toute l'application
==============================================================

Ce module centralise toutes les validations pour garantir la cohérence.
"""

import re
from typing import Optional, Tuple


class ValidationUtils:
    """Utilitaires de validation pour différents types de données."""
    
    # Expressions régulières
    EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
    PHONE_REGEX = re.compile(r'^[\+]?[1-9][\d]{0,15}$')
    URL_REGEX = re.compile(
        r'^https?://'  # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|'  # domain...
        r'localhost|'  # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})'  # ...or ip
        r'(?::\d+)?'  # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)
    
    @staticmethod
    def validate_email(email: str) -> Tuple[bool, str]:
        """
        Valide une adresse email.
        
        Args:
            email: Adresse email à valider
            
        Returns:
            Tuple (is_valid, error_message)
        """
        if not email:
            return False, "L'adresse email est requise"
        
        email = email.strip()
        
        if len(email) > 254:
            return False, "L'adresse email est trop longue (max 254 caractères)"
        
        if not ValidationUtils.EMAIL_REGEX.match(email):
            return False, "Format d'adresse email invalide"
        
        return True, ""
    
    @staticmethod
    def validate_phone(phone: str) -> Tuple[bool, str]:
        """
        Valide un numéro de téléphone.
        
        Args:
            phone: Numéro de téléphone à valider
            
        Returns:
            Tuple (is_valid, error_message)
        """
        if not phone:
            return False, "Le numéro de téléphone est requis"
        
        # Nettoyer le numéro
        cleaned_phone = re.sub(r'[\s\-\(\)\.]+', '', phone.strip())
        
        if len(cleaned_phone) < 8:
            return False, "Le numéro de téléphone est trop court (min 8 chiffres)"
        
        if len(cleaned_phone) > 17:  # +XX XXXXXXXXX (format international max)
            return False, "Le numéro de téléphone est trop long (max 17 caractères)"
        
        if not ValidationUtils.PHONE_REGEX.match(cleaned_phone):
            return False, "Format de numéro de téléphone invalide"
        
        return True, ""
    
    @staticmethod
    def validate_url(url: str) -> Tuple[bool, str]:
        """
        Valide une URL.
        
        Args:
            url: URL à valider
            
        Returns:
            Tuple (is_valid, error_message)
        """
        if not url:
            return False, "L'URL est requise"
        
        url = url.strip()
        
        if len(url) > 2048:
            return False, "L'URL est trop longue (max 2048 caractères)"
        
        if not ValidationUtils.URL_REGEX.match(url):
            return False, "Format d'URL invalide (doit commencer par http:// ou https://)"
        
        return True, ""
    
    @staticmethod
    def validate_name(name: str) -> Tuple[bool, str]:
        """
        Valide un nom (prénom/nom de famille).
        
        Args:
            name: Nom à valider
            
        Returns:
            Tuple (is_valid, error_message)
        """
        if not name:
            return False, "Le nom est requis"
        
        name = name.strip()
        
        if len(name) < 2:
            return False, "Le nom doit contenir au moins 2 caractères"
        
        if len(name) > 50:
            return False, "Le nom est trop long (max 50 caractères)"
        
        # Vérifier que le nom ne contient que des lettres, espaces, tirets et apostrophes
        if not re.match(r"^[a-zA-ZÀ-ÿ\s\-']+$", name):
            return False, "Le nom ne peut contenir que des lettres, espaces, tirets et apostrophes"
        
        return True, ""
    
    @staticmethod
    def validate_required_field(value: str, field_name: str) -> Tuple[bool, str]:
        """
        Valide qu'un champ requis n'est pas vide.
        
        Args:
            value: Valeur à valider
            field_name: Nom du champ pour le message d'erreur
            
        Returns:
            Tuple (is_valid, error_message)
        """
        if not value or not value.strip():
            return False, f"Le champ '{field_name}' est requis"
        
        return True, ""
    
    @staticmethod
    def validate_text_length(text: str, min_length: int = 0, max_length: int = 1000, field_name: str = "texte") -> Tuple[bool, str]:
        """
        Valide la longueur d'un texte.
        
        Args:
            text: Texte à valider
            min_length: Longueur minimale
            max_length: Longueur maximale
            field_name: Nom du champ pour le message d'erreur
            
        Returns:
            Tuple (is_valid, error_message)
        """
        if not text:
            text = ""
        
        text = text.strip()
        length = len(text)
        
        if length < min_length:
            return False, f"Le {field_name} doit contenir au moins {min_length} caractères"
        
        if length > max_length:
            return False, f"Le {field_name} ne peut pas dépasser {max_length} caractères"
        
        return True, ""
    
    @staticmethod
    def format_phone_display(phone: str) -> str:
        """
        Formate un numéro de téléphone pour l'affichage.
        
        Args:
            phone: Numéro de téléphone brut
            
        Returns:
            Numéro formaté pour l'affichage
        """
        if not phone:
            return ""
        
        # Nettoyer le numéro
        cleaned = re.sub(r'[\s\-\(\)\.]+', '', phone.strip())
        
        # Format français (+33 X XX XX XX XX)
        if cleaned.startswith('+33') and len(cleaned) == 12:
            return f"+33 {cleaned[3]} {cleaned[4:6]} {cleaned[6:8]} {cleaned[8:10]} {cleaned[10:12]}"
        
        # Format US/Canada (+1 XXX XXX XXXX)
        elif cleaned.startswith('+1') and len(cleaned) == 12:
            return f"+1 {cleaned[2:5]} {cleaned[5:8]} {cleaned[8:12]}"
        
        # Autres formats internationaux - grouper par 2-3 chiffres
        elif cleaned.startswith('+') and len(cleaned) > 8:
            country_code = cleaned[:3] if len(cleaned) > 10 else cleaned[:2]
            number = cleaned[len(country_code):]
            
            # Grouper le numéro par paires
            formatted_number = ' '.join([number[i:i+2] for i in range(0, len(number), 2)])
            return f"{country_code} {formatted_number}"
        
        # Si pas de format reconnu, retourner tel quel
        return phone
    
    @staticmethod
    def normalize_url(url: str) -> str:
        """
        Normalise une URL (ajoute https:// si nécessaire).
        
        Args:
            url: URL à normaliser
            
        Returns:
            URL normalisée
        """
        if not url:
            return ""
        
        url = url.strip()
        
        # Ajouter https:// si pas de protocole
        if not url.startswith(('http://', 'https://')):
            url = f"https://{url}"
        
        return url


# Fonctions utilitaires pour usage rapide
def is_valid_email(email: str) -> bool:
    """Vérifie rapidement si un email est valide."""
    valid, _ = ValidationUtils.validate_email(email)
    return valid


def is_valid_phone(phone: str) -> bool:
    """Vérifie rapidement si un téléphone est valide."""
    valid, _ = ValidationUtils.validate_phone(phone)
    return valid


def is_valid_url(url: str) -> bool:
    """Vérifie rapidement si une URL est valide."""
    valid, _ = ValidationUtils.validate_url(url)
    return valid


def format_phone(phone: str) -> str:
    """Raccourci pour formater un numéro de téléphone."""
    return ValidationUtils.format_phone_display(phone)


def normalize_url(url: str) -> str:
    """Raccourci pour normaliser une URL."""
    return ValidationUtils.normalize_url(url)
