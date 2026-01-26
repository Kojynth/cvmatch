"""
Constantes centralisées pour l'extraction CV avec seuils configurables.

Ces constantes contrôlent le comportement de l'extracteur et peuvent être
ajustées via flags CLI pour audit et tuning.
"""

# === ASSOCIATION DATE-FIRST ===
DATE_ASSOC_MIN_SCORE = 0.60  # Score composite minimal pour association date-rôle-entreprise
HEADER_LOCKOUT_DIST = 1       # Distance minimale d'un header pour autoriser ancrage date
WINDOW_BASE = 12              # Taille de fenêtre de base pour association
WINDOW_MAX = 16               # Taille maximale de fenêtre si pas d'association

# === PONDÉRATIONS SCORE COMPOSITE ===
WEIGHT_HAS_ORG = 0.30         # Poids pour présence organisation
WEIGHT_HAS_ROLE = 0.35        # Poids pour présence rôle  
WEIGHT_EMPLOYMENT_KW = 0.20   # Poids pour mots-clés emploi
WEIGHT_HEADER_DISTANCE = 0.15 # Poids pour distance des headers

# === TIE-BREAKER EDUCATION VS EXPERIENCE ===
EDU_OVERRIDE_THRESHOLD = 0.80      # Seuil classification éducation pour override
EXP_EMPLOYMENT_SIGNALS_MIN = 2     # Nombre minimal signaux emploi pour downgrade

# === FENÊTRE ET DENSITÉ ===
WINDOW_DENSITY_MIN = 0.15          # Densité minimale pour fenêtre expérience
WINDOW_EXPAND_STEP = 2             # Pas d'élargissement de fenêtre

# === HEADERS BLACKLIST (multi-langues) ===
HEADER_BLACKLIST = {
    # Français
    'compétences', 'formations', 'éducation', 'langues', 'centres d\'intérêt',
    'hobbies', 'loisirs', 'références', 'certifications', 'projets',
    
    # Anglais
    'skills', 'education', 'languages', 'interests', 'hobbies',
    'references', 'certifications', 'projects', 'achievements',
    
    # Espagnol
    'habilidades', 'educación', 'idiomas', 'intereses', 'referencias',
    
    # Allemand
    'fähigkeiten', 'bildung', 'sprachen', 'interessen', 'referenzen',
    
    # Chinois simplifié
    '技能', '教育', '语言', '兴趣', '项目', '资格',
    
    # Arabe
    'المهارات', 'التعليم', 'اللغات', 'الاهتمامات', 'المراجع'
}

# === MOTS-CLÉS NON-EMPLOI (SPORTS/LOISIRS) ===
NON_EMPLOYMENT_KEYWORDS = {
    # Sports
    'football', 'soccer', 'basketball', 'tennis', 'volleyball', 'rugby',
    'natation', 'swimming', 'cyclisme', 'cycling', 'running', 'course',
    'escalade', 'climbing', 'ski', 'skiing', 'snowboard',
    
    # Loisirs/Arts
    'photographie', 'photography', 'musique', 'music', 'piano', 'guitare',
    'guitar', 'dessin', 'drawing', 'peinture', 'painting', 'lecture',
    'reading', 'voyage', 'travel', 'cinéma', 'cinema', 'théâtre', 'theater',
    
    # Activités sociales
    'bénévolat', 'volunteer', 'association', 'club', 'scouts', 'charity',
    'charité', 'église', 'church', 'communauté', 'community',
    
    # Multi-langues
    '足球', '篮球', '游泳', '摄影', '音乐', '旅行',  # Chinois
    'كرة القدم', 'السباحة', 'التصوير', 'الموسيقى'   # Arabe
}

# === NORMALISATION DATES RELATIVES ===
DATE_PRESENT_TOKENS = {
    'fr': ['à ce jour', 'présent', 'actuel', 'actuellement', 'en cours'],
    'en': ['present', 'current', 'currently', 'ongoing', 'to date', 'now'],
    'es': ['presente', 'actual', 'actualmente', 'en curso'],
    'de': ['heute', 'aktuell', 'derzeit', 'gegenwärtig'],
    'zh': ['至今', '现在', '目前', '当前'],
    'ar': ['حتى الآن', 'الآن', 'حاليا', 'حالياً']
}

# === PATTERNS EMPLOI ===
EMPLOYMENT_PATTERNS = [
    # Verbes d'action professionnels
    r'\b(développer?|concevoir|gérer|diriger|coordonner|superviser)\b',
    r'\b(manage|develop|design|lead|coordinate|supervise|implement)\b',
    r'\b(crear|gestionar|desarrollar|dirigir|coordinar)\b',  # Espagnol
    r'\b(entwickeln|verwalten|leiten|koordinieren)\b',       # Allemand
    
    # Indicateurs d'emploi
    r'\b(employé|salarié|consultant|freelance|contractor)\b',
    r'\b(employee|staff|consultant|contractor|worker)\b',
    r'\b(empleado|consultor|trabajador)\b',                   # Espagnol
    r'\b(angestellt|berater|mitarbeiter)\b',                 # Allemand
    
    # Lieux de travail
    r'\b(bureau|office|société|entreprise|company|firm)\b',
    r'\b(empresa|oficina|firma)\b',                          # Espagnol
    r'\b(büro|unternehmen|firma)\b',                         # Allemand
]

# === CONFIGURATION LOGGING ===
PII_MASK_ENABLED = True
LOG_EXTRACTION_DETAILS = True
LOG_SCORE_BREAKDOWN = True

# === ANTI-CONTAMINATION THRESHOLDS ===
NON_EMPLOYMENT_KEYWORD_THRESHOLD = 2  # Max mots-clés non-emploi avant rejet
MINIMUM_EMPLOYMENT_SCORE = 0.6        # Score minimal expérience vs autres sections
CONTEXT_WINDOW_RADIUS = 4             # Rayon fenêtre pour analyse contextuelle

# === FENETRE EXPANSION PARAMETERS ===
MIN_EXPANSION_DENSITY = 0.25          # Densité minimale pour expansion fenêtre
MAX_WINDOW_SIZE = 40                   # Taille maximale fenêtre en lignes
