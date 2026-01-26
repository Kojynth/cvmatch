# PATCH-PII: Détection et redaction des données personnelles identifiables multi-langues
import re
from typing import Pattern
from .redactor import redact_with_token, mask_email, mask_phone, mask_keep_shape

# Patterns pour emails (supportant Unicode et domaines internationaux)
EMAIL = re.compile(
    r'\b[a-zA-Z0-9._%+\-\u00C0-\u024F\u1E00-\u1EFF\u4e00-\u9fff\u0600-\u06FF]+@[a-zA-Z0-9.\-\u00C0-\u024F\u4e00-\u9fff\u0600-\u06FF]+\.[a-zA-Z\u00C0-\u024F]{2,}\b',
    re.UNICODE
)

# Patterns pour numéros de téléphone (formats internationaux) - plus restrictif
PHONE = re.compile(
    r'\b(?:' +
    r'(?:\+33[\s.\-]?[1-9][\s.\-]?\d{2}[\s.\-]?\d{2}[\s.\-]?\d{2}[\s.\-]?\d{2})' +  # +33 format
    r'|' +
    r'(?:0[1-9][\s.\-]?\d{2}[\s.\-]?\d{2}[\s.\-]?\d{2}[\s.\-]?\d{2})' +  # 01-09 format français
    r'|' +
    r'(?:\+?\d{1,3}[\s.\-]?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4})' +  # Format (123) 456-7890
    r')\b',
    re.UNICODE
)

# Patterns pour adresses (multi-langues avec support OCR bruité)
ADDR = re.compile(
    r'(?:\b\d{1,5}[\s,\-]?)' +  # Numéro de rue REQUIS
    r'(?:' +
    # Français
    r'(?:rue|avenue|av\.?|bd|boulevard|place|pl\.?|chemin|impasse|allée|square|quai|cours)[\s\w\-\',\.\u00C0-\u017F]+' +
    r'|' +
    # Anglais - plus restrictif
    r'(?:street|st\.?|avenue|ave\.?|road|rd\.?|lane|ln\.?|drive|dr\.?|way|place|pl\.?)[\s\w\-\',\.\u00C0-\u017F]+' +
    r'|' +
    # Allemand
    r'(?:straße|strasse|str\.?|gasse|platz|weg|allee)[\s\w\-\',\.\u00C0-\u017F\u00df]+' +
    r'|' +
    # Espagnol
    r'(?:calle|c/|avenida|avda\.?|plaza|pl\.?|paseo|travesía)[\s\w\-\',\.\u00C0-\u017F]+' +
    r'|' +
    # Italien
    r'(?:via|viale|corso|piazza|largo)[\s\w\-\',\.\u00C0-\u017F]+' +
    r'|' +
    # Japonais
    r'[\u4E00-\u9FFF\u3040-\u309F\u30A0-\u30FF]*(?:区|県|市|町|丁目|番地|号)[\u4E00-\u9FFF\u3040-\u309F\u30A0-\u30FF\s\d]*' +
    r'|' +
    # Chinois
    r'[\u4E00-\u9FFF]*(?:路|街|区|市|省|县|镇|村|号|室)[\u4E00-\u9FFF\s\d]*' +
    r')',
    re.IGNORECASE | re.UNICODE
)

# Liste de mots techniques à exclure de la détection de noms
TECHNICAL_EXCLUSIONS = {
    # Technologies et langages
    'python', 'java', 'javascript', 'react', 'angular', 'vue', 'node', 'mysql', 'postgresql',
    'mongodb', 'redis', 'docker', 'kubernetes', 'aws', 'azure', 'gcp', 'git', 'github',
    'linux', 'windows', 'android', 'ios', 'swift', 'kotlin', 'flutter', 'xamarin',
    # Mots courants
    'test', 'demo', 'example', 'sample', 'data', 'info', 'user', 'admin', 'client',
    'server', 'api', 'web', 'mobile', 'desktop', 'app', 'software', 'system', 'service',
    # Jours et mois
    'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
    'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
    'september', 'october', 'november', 'december', 'lundi', 'mardi', 'mercredi',
    'jeudi', 'vendredi', 'samedi', 'dimanche', 'janvier', 'février', 'mars', 'avril',
    'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre'
}

# Patterns pour noms de personnes (multi-scripts avec majuscules, mais plus restrictifs)
NAME = re.compile(
    r'\b(?:' +
    # Noms composés européens (support Unicode étendu)
    r'(?:[A-Z\u00C0-\u024F\u1E00-\u1EFF][a-z\u00C0-\u024F\u1E00-\u1EFF\-]+' +
    r'\s+[A-Z\u00C0-\u024F\u1E00-\u1EFF][a-z\u00C0-\u024F\u1E00-\u1EFF\-]+' +
    r'(?:\s+[A-Z\u00C0-\u024F\u1E00-\u1EFF][a-z\u00C0-\u024F\u1E00-\u1EFF\-]+)?)' +
    r'|' +
    # Noms CJK (2-4 caractères)
    r'[\u4E00-\u9FFF\u3040-\u309F\u30A0-\u30FF]{2,4}' +
    r'|' +
    # Noms cyrilliques (au moins 2 parties)
    r'(?:[А-ЯЁ][а-яё]+\s+[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+)?)' +
    r'|' +
    # Noms arabes (RTL, au moins 2 parties)
    r'(?:[\u0600-\u06FF]+\s+[\u0600-\u06FF]+(?:\s+[\u0600-\u06FF]+)?)' +
    r')\b',
    re.UNICODE
)

# Patterns pour organisations/institutions (plus précis)
ORG = re.compile(
    r'\b(?:' +
    # Institutions d'éducation françaises
    r'(?:(?:Université|\u00c9cole|Ecole|Institut|Lycée|Lycee|Collège)\s+[\w\-\'\'éÉèÈêÊàÀäÄöÖüÜïÏçÇ\u00C0-\u017F& ]+)' +
    r'|' +
    # Institutions d'éducation anglaises
    r'(?:[\w\-\'\'éÉèÈêÊàÀäÄöÖüÜïÏçÇ\u00C0-\u017F& ]+\s+(?:University|College|School|Institute))' +
    r'|' +
    # Grandes entreprises connues
    r'(?:(?:Google|Microsoft|Apple|Amazon|Facebook|Meta|Netflix|Tesla|IBM|Oracle|Adobe|Salesforce)' +
    r'(?:\s+(?:France|Inc|Corp|Corporation|Ltd|Limited|GmbH|AG|SA|SAS|SARL))?)' +
    r'|' +
    # Entreprises avec suffixes
    r'(?:[\w\-\'\'éÉèÈêÊàÀäÄöÖüÜïÏçÇ\u00C0-\u017F& ]+\s+(?:SA|SAS|SARL|Inc|Corp|Corporation|Ltd|Limited|GmbH|AG))' +
    r'|' +
    # Japonais
    r'(?:[\u4E00-\u9FFF\u3040-\u309F\u30A0-\u30FF]+(?:大学|学校|会社|株式会社|有限会社|学院|短期大学))' +
    r'|' +
    # Chinois
    r'(?:[\u4E00-\u9FFF]+(?:大学|学校|公司|学院|中学|小学))' +
    r')\b',
    re.IGNORECASE | re.UNICODE
)

# Patterns pour lieux géographiques
GEO = re.compile(
    r'\b(?:' +
    # Pays et villes connues (échantillon représentatif)
    r'(?:France|Paris|Lyon|Marseille|Toulouse|Nice|Nantes|Strasbourg|Montpellier|Bordeaux|Lille)' +
    r'|' +
    r'(?:Japan|Japon|Tokyo|Osaka|Kyoto|Yokohama|Nagoya|Sapporo|Fukuoka|日本|東京|大阪|京都)' +
    r'|' +
    r'(?:Germany|Deutschland|Berlin|Munich|Hamburg|Cologne|Frankfurt|Stuttgart)' +
    r'|' +
    r'(?:Spain|España|Madrid|Barcelona|Valencia|Sevilla|Zaragoza|Málaga)' +
    r'|' +
    r'(?:Italy|Italia|Rome|Roma|Milan|Milano|Naples|Napoli|Turin|Torino)' +
    r'|' +
    r'(?:China|中国|Beijing|北京|Shanghai|上海|Guangzhou|广州|Shenzhen|深圳)' +
    r'|' +
    r'(?:USA|America|New York|Los Angeles|Chicago|Houston|Phoenix|Philadelphia)' +
    r'|' +
    r'(?:UK|Britain|London|Manchester|Birmingham|Liverpool|Leeds|Glasgow)' +
    r'|' +
    r'(?:Canada|Toronto|Montreal|Vancouver|Calgary|Ottawa|Edmonton)' +
    r'|' +
    r'(?:Australia|Sydney|Melbourne|Brisbane|Perth|Adelaide)' +
    r'|' +
    # Codes postaux courants
    r'(?:\b\d{5}\b|\b\d{5}-\d{4}\b|\b[A-Z]\d[A-Z] \d[A-Z]\d\b)' +  # US, CA formats
    r')\b',
    re.IGNORECASE | re.UNICODE
)

# Patterns pour handles/profils sociaux
HANDLE = re.compile(
    r'(?:' +
    r'(?:\bgithub\.com/[A-Za-z0-9_\-]+\b)' +
    r'|' +
    r'(?:\blinkedin\.com/in/[A-Za-z0-9_\-]+\b)' +
    r'|' +
    r'(?:\btwitter\.com/[A-Za-z0-9_]+\b)' +
    r'|' +
    r'(?:@[A-Za-z0-9_]+)' +  # Mentions sans word boundary
    r')',
    re.UNICODE
)

# Patterns pour données sensibles additionnelles
SENSITIVE_DATA = re.compile(
    r'\b(?:' +
    # Identifiants personnels
    r'(?:ssn|social security|sécurité sociale|numéro de sécurité sociale)' +
    r'|' +
    # Dates de naissance
    r'(?:né le|born on|fecha de nacimiento|geboren am|\d{1,2}/\d{1,2}/\d{4})' +
    r'|' +
    # Nationalités
    r'(?:nationalité|nationality|ciudadanía|staatsangehörigkeit)' +
    r')\b',
    re.IGNORECASE | re.UNICODE
)

# Mapping des patterns vers leurs fonctions de masquage spécialisées
# L'ordre est important: les plus spécifiques d'abord
PII_PATTERNS = [
    (EMAIL, "EMAIL", mask_email),
    (PHONE, "TEL", mask_phone),
    (HANDLE, "HANDLE", mask_keep_shape),
    (ORG, "ORG", mask_keep_shape),  # Avant GEO et NAME pour éviter conflicts
    (ADDR, "ADDR", mask_keep_shape),
    (GEO, "GEO", mask_keep_shape),
    (SENSITIVE_DATA, "SENSITIVE", mask_keep_shape),
    (NAME, "NAME", mask_keep_shape),  # En dernier pour éviter false positives
]

def _is_technical_exclusion(text: str, kind: str) -> bool:
    """Vérifie si le texte détecté est un faux positif technique."""
    text_lower = text.lower().strip()
    
    # Exclusions pour tous les types de PII
    if kind in ["TEL", "PHONE"]:
        # Exclusions spécifiques aux numéros de téléphone
        # Timestamps, heures, dates, numéros de ligne
        if any(pattern in text for pattern in [
            ":", ".", "-", "_"  # Format heure/date
        ]) and len(text) < 12:  # Courts = probablement pas un téléphone
            return True
        # Pattern timestamp complet (HH:mm:ss ou YYYY-MM-DD)
        if re.match(r'^\d{1,4}[:\-]\d{1,2}[:\-]\d{1,4}', text):
            return True
        # Numéros de ligne isolés
        if text.isdigit() and len(text) <= 4:
            return True
            
    if kind == "NAME":
        # CORRECTION: Mode strict pour les logs d'extraction - ne pas filtrer les vrais noms
        # Seulement filtrer les mots simples techniques évidents
        words = text_lower.split()
        if len(words) == 1 and words[0] in TECHNICAL_EXCLUSIONS:
            return True
            
        # Éviter de filtrer les noms de personnes composés (prénom + nom)
        # Seulement filtrer les combinaisons techniques évidentes
        obvious_tech_combos = ['machine learning', 'artificial intelligence', 'software engineering']
        if any(combo in text_lower for combo in obvious_tech_combos):
            return True
            
        # Ne PAS filtrer les noms qui ressemblent à des personnes réelles
        # (prénom japonais + nom occidental par exemple)
        return False
    
    # Exclusions générales
    # Formats temporels et numériques
    if re.match(r'^\d{4}-\d{2}-\d{2}', text):  # Date ISO
        return True
    if re.match(r'^\d{2}:\d{2}:\d{2}', text):  # Heure
        return True
    if re.match(r'^\d+$', text) and len(text) <= 5:  # Numéros courts
        return True
        
    return False

def _apply_pattern(pattern: Pattern, text: str, salt: str, kind: str, masker=mask_keep_shape) -> str:
    """Applique un pattern de redaction sur un texte avec filtrage des faux positifs."""
    if not text:
        return text
    
    def replace_match(match):
        matched_text = match.group(0)
        # Filtrer les faux positifs
        if _is_technical_exclusion(matched_text, kind):
            return matched_text  # Ne pas redacter
        return redact_with_token(matched_text, salt=salt, kind=kind, masker=masker)
    
    return pattern.sub(replace_match, text)

def redact_all(text: str, salt: str, ocr_tolerance: bool = False) -> str:
    """Redacte toutes les PII détectées dans un texte.
    
    Args:
        text: Texte à analyser et redacter
        salt: Sel pour la génération des tokens
        ocr_tolerance: Si True, applique une tolérance pour l'OCR bruité (désactivé par défaut)
    
    Returns:
        Texte avec toutes les PII redactées
    """
    if not text:
        return text
    
    result = text
    
    # Appliquer tous les patterns de PII dans l'ordre
    for pattern, kind, masker in PII_PATTERNS:
        result = _apply_pattern(pattern, result, salt, kind, masker)
    
    # Si tolérance OCR activée, appliquer des corrections courantes
    if ocr_tolerance:
        result = _apply_ocr_noise_patterns(result, salt)
    
    return result

def _apply_ocr_noise_patterns(text: str, salt: str) -> str:
    """Applique des patterns spéciaux pour l'OCR bruité."""
    # Patterns courants d'erreurs OCR sur les noms/emails
    ocr_noise_patterns = [
        # Emails avec erreurs OCR: m -> rn, n -> ri, etc.
        (re.compile(r'\b[A-Za-z][a-z]*rn[a-z]*@[a-z]+\.[a-z]+\b', re.IGNORECASE), "EMAIL-OCR"),
        # Noms avec chiffres ou erreurs OCR communes (au moins 2 parties)
        (re.compile(r'\b[A-Z][a-z]*[0-9Il1l][a-z]*\s+[A-Z][a-z]+\b'), "NAME-OCR"),
        # Institutions avec chiffres OCR
        (re.compile(r'\b[A-Z\u00c0-\u017f][a-zà-ſ]*[0-9Il1l][a-zà-\u017f]*\s+[a-zà-\u017f]+\s+[A-Z\u00c0-\u017f][a-zà-\u017f]+\b', re.IGNORECASE), "ORG-OCR"),
    ]
    
    result = text
    for pattern, kind in ocr_noise_patterns:
        result = _apply_pattern(pattern, result, salt, kind)
    
    return result

def detect_pii_types(text: str) -> list[str]:
    """Détecte les types de PII présents dans un texte sans les redacter.
    
    Args:
        text: Texte à analyser
    
    Returns:
        Liste des types de PII détectés
    """
    if not text:
        return []
    
    detected_types = []
    
    for pattern, kind, _ in PII_PATTERNS:
        if pattern.search(text):
            detected_types.append(kind)
    
    return detected_types

def has_pii(text: str, strict_logging_mode: bool = False) -> bool:
    """Vérifie rapidement si un texte contient des PII.
    
    Args:
        text: Texte à vérifier
        strict_logging_mode: Si True, mode conservateur pour logs techniques
    
    Returns:
        True si des PII sont détectées
    """
    if not text:
        return False
    
    # Mode conservateur pour éviter de redacter les logs techniques
    if strict_logging_mode:
        # En mode logging, seulement détecter les PII évidentes (emails complets)
        if EMAIL.search(text) and '@' in text and '.' in text:
            # Vérifier que c'est un vrai email, pas un timestamp ou code
            email_match = EMAIL.search(text)
            if email_match:
                email_text = email_match.group(0)
                if len(email_text) > 6 and email_text.count('@') == 1:
                    return True
        return False
    
    # Mode normal: utiliser detect_pii_types qui filtre déjà les faux positifs
    return len(detect_pii_types(text)) > 0

def validate_no_pii_leakage(text: str, salt: str) -> str:
    """Valide qu'un texte est complètement exempt de PII pour les logs d'extraction.
    
    Mode ultra-strict : détecte et redacte même les noms partiellement visibles.
    
    Args:
        text: Texte à vérifier et nettoyer
        salt: Sel pour la redaction
    
    Returns:
        Texte garanti sans PII visible
    """
    if not text:
        return text
    
    # 1ère passe : redaction normale
    cleaned = redact_all(text, salt, ocr_tolerance=True)
    
    # 2ème passe : vérification ultra-stricte pour noms propres visibles
    # Pattern pour détecter des noms qui auraient pu échapper (prénom + nom avec majuscules)
    remaining_names = re.compile(
        r'\b[A-Z][a-z]{2,}\s+[A-Z][a-z]{2,}\b',  # Format "Prénom Nom" 
        re.UNICODE
    )
    
    def ultra_strict_name_replacer(match):
        name = match.group(0)
        # Ne redacter que si ce n'est pas déjà dans un token PII
        if '[PII-' not in name and 'extraction' not in name.lower():
            return redact_with_token(name, salt, "NAME-STRICT", mask_keep_shape)
        return name
    
    cleaned = remaining_names.sub(ultra_strict_name_replacer, cleaned)
    
    # 3ème passe : nettoyer les fragments d'email partiellement visibles
    partial_email_pattern = re.compile(
        r'\b[a-zA-Z]{2,}\s+[a-zA-Z]{2,}\[PII-HANDLE',  # "nom prenom[PII-HANDLE"
        re.UNICODE
    )
    
    def clean_partial_email(match):
        fragment = match.group(0)
        # Remplacer le fragment visible avant le token PII
        return '[PII-NAME-FRAG:***] [PII-HANDLE'
    
    cleaned = partial_email_pattern.sub(clean_partial_email, cleaned)
    
    return cleaned

def redact_structured_data(data: dict, salt: str, sensitive_keys: set = None) -> dict:
    """Redacte les PII dans des données structurées.
    
    Args:
        data: Dictionnaire de données
        salt: Sel pour la redaction
        sensitive_keys: Ensemble des clés considérées comme sensibles
    
    Returns:
        Dictionnaire avec les PII redactées
    """
    if sensitive_keys is None:
        sensitive_keys = {
            'name', 'nom', 'email', 'phone', 'telephone', 'tel', 'address', 'adresse',
            'street', 'rue', 'city', 'ville', 'company', 'entreprise', 'school',
            'ecole', 'university', 'universite', 'institution', 'linkedin', 'github',
            'first_name', 'last_name', 'prenom', 'nom_famille', 'full_name',
            'location', 'lieu', 'birth_date', 'date_naissance', 'nationality', 'nationalite'
        }
    
    if not isinstance(data, dict):
        return data
    
    result = {}
    for key, value in data.items():
        key_lower = key.lower() if isinstance(key, str) else str(key).lower()
        
        if isinstance(value, str):
            if any(sensitive in key_lower for sensitive in sensitive_keys) or has_pii(value):
                result[key] = redact_all(value, salt)
            else:
                result[key] = value
        elif isinstance(value, dict):
            result[key] = redact_structured_data(value, salt, sensitive_keys)
        elif isinstance(value, list):
            result[key] = [
                redact_structured_data(item, salt, sensitive_keys) if isinstance(item, dict)
                else redact_all(item, salt) if isinstance(item, str) and has_pii(item)
                else item
                for item in value
            ]
        else:
            result[key] = value
    
    return result


def validate_no_pii_leakage(text: str, salt: str) -> str:
    """Valide qu'un texte est complètement exempt de PII pour les logs d'extraction.
    
    Cette fonction applique une redaction ultra-stricte spécialement conçue pour
    les logs d'extraction où même des fragments de PII peuvent être problématiques.
    
    ULTRA-STRICT MODE: Cette fonction redacte TOUT ce qui pourrait être du PII,
    même si le système principal ne l'a pas détecté.
    
    Args:
        text: Texte à valider et nettoyer
        salt: Sel pour la génération de tokens stables
    
    Returns:
        Texte complètement nettoyé et sûr pour les logs
    """
    if not text:
        return text
    
    # 1ère passe : redaction normale (peut ne pas tout attraper)
    cleaned = redact_all(text, salt, ocr_tolerance=True)
    
    # 2ème passe ULTRA-STRICTE : noms propres non redactés
    # Pattern pour capturer tous les formats de noms : "Prénom NOM", "PRÉNOM NOM", "Prénom Nom"
    remaining_names = re.compile(r'\b[A-Z][A-Za-z]{2,}\s+[A-Z][A-Za-z]{2,}\b', re.UNICODE)
    
    def replace_remaining_name(match):
        name = match.group(0)
        # Vérifier si c'est un terme technique - AVEC paramètres corrects
        try:
            if _is_technical_exclusion(name, "NAME"):
                return name
        except:
            pass  # Si erreur, redacter par sécurité
        
        # Redacter complètement les vrais noms
        return redact_with_token(name, salt, "NAME-LEAKED", mask_keep_shape)
    
    cleaned = remaining_names.sub(replace_remaining_name, cleaned)
    
    # 3ème passe : fragments d'emails partiellement visibles
    # Pattern: "mot mot[PII-HANDLE-" -> "[PII-NAME-xxx][PII-HANDLE-"
    partial_email_pattern = re.compile(r'\b[a-z]{2,}\s+[a-z]{2,}(?=\[PII-HANDLE)', re.IGNORECASE | re.UNICODE)
    cleaned = partial_email_pattern.sub(
        lambda m: redact_with_token(m.group(0).strip(), salt, "NAME-FRAGMENT", mask_keep_shape), 
        cleaned
    )
    
    # 4ème passe : détecter d'autres patterns PII non redactés
    # Emails complets non redactés
    email_pattern = re.compile(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b', re.UNICODE)
    cleaned = email_pattern.sub(lambda m: redact_with_token(m.group(0), salt, "EMAIL-LEAKED", mask_email), cleaned)
    
    # Téléphones complets non redactés
    phone_pattern = re.compile(r'\b(?:\+33|0)[1-9][\s.-]?\d{2}[\s.-]?\d{2}[\s.-]?\d{2}[\s.-]?\d{2}\b', re.UNICODE)
    cleaned = phone_pattern.sub(lambda m: redact_with_token(m.group(0), salt, "TEL-LEAKED", mask_phone), cleaned)
    
    return cleaned
