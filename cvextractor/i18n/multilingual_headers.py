"""
Multilingual Header Recognition
==============================

Recognition system for CV section headers across multiple languages and scripts.
Supports Latin, Arabic, Hebrew, CJK, Cyrillic, and other writing systems with
fuzzy matching and transliteration capabilities.
"""

import re
import logging
from typing import Dict, List, Any, Optional, Tuple, Set
from dataclasses import dataclass
from enum import Enum
import unicodedata

from .text_direction_detector import detect_text_direction, ScriptType, TextDirection
from ..utils.log_safety import create_safe_logger_wrapper
from ..metrics.instrumentation import get_metrics_collector


class SectionType(Enum):
    """CV section types."""

    PERSONAL_INFO = "personal_info"
    SUMMARY = "summary"
    EXPERIENCE = "experience"
    EDUCATION = "education"
    SKILLS = "skills"
    LANGUAGES = "languages"
    PROJECTS = "projects"
    CERTIFICATIONS = "certifications"
    AWARDS = "awards"
    PUBLICATIONS = "publications"
    REFERENCES = "references"
    INTERESTS = "interests"
    VOLUNTEERING = "volunteering"
    CONTACT = "contact"
    UNKNOWN = "unknown"


@dataclass
class HeaderMatch:
    """Header recognition result."""

    text: str
    section_type: SectionType
    confidence: float
    language_detected: str
    script_type: ScriptType
    normalized_form: str
    match_method: str  # exact, fuzzy, transliteration, pattern


class MultilingualHeaderRecognizer:
    """Recognizes CV section headers across multiple languages and scripts."""

    def __init__(self, debug_mode: bool = False):
        self.debug_mode = debug_mode

        # Logger
        base_logger = logging.getLogger(__name__)
        self.logger = create_safe_logger_wrapper(base_logger)

        # Setup multilingual headers
        self._setup_header_patterns()
        self._setup_fuzzy_matching()

    def _setup_header_patterns(self):
        """Setup multilingual header patterns."""

        # Comprehensive multilingual header mappings
        self.header_patterns = {
            SectionType.PERSONAL_INFO: {
                "latin": [
                    "personal information",
                    "personal details",
                    "personal data",
                    "about me",
                    "informations personnelles",
                    "données personnelles",
                    "sobre mi",
                    "informazioni personali",
                    "persönliche daten",
                    "dados pessoais",
                    "personlige oplysninger",
                    "persoonlijke gegevens",
                ],
                "cyrillic": [
                    "личная информация",
                    "персональные данные",
                    "обо мне",
                    "особисті дані",
                    "лична информация",
                ],
                "arabic": [
                    "معلومات شخصية",
                    "البيانات الشخصية",
                    "عني",
                    "معطيات شخصية",
                    "تفاصيل شخصية",
                ],
                "hebrew": ["מידע אישי", "פרטים אישיים", "עלי", "נתונים אישיים"],
                "cjk": [
                    "個人情報",
                    "个人信息",
                    "個人資料",
                    "基本信息",
                    "개인정보",
                    "개인 정보",
                    "プロフィール",
                ],
            },
            SectionType.EXPERIENCE: {
                "latin": [
                    "experience",
                    "work experience",
                    "employment",
                    "career",
                    "professional experience",
                    "expérience",
                    "expérience professionnelle",
                    "emploi",
                    "carrière",
                    "experiencia",
                    "experiencia laboral",
                    "carrera",
                    "empleo",
                    "esperienza",
                    "esperienza lavorativa",
                    "carriera",
                    "lavoro",
                    "erfahrung",
                    "berufserfahrung",
                    "karriere",
                    "arbeit",
                    "experiência",
                    "experiência profissional",
                    "carreira",
                    "trabalho",
                    "erfaring",
                    "arbeidserfaring",
                    "karriere",
                ],
                "cyrillic": [
                    "опыт работы",
                    "опыт",
                    "карьера",
                    "работа",
                    "професійний досвід",
                    "досвід роботи",
                    "кар'єра",
                    "професионален опит",
                    "опит",
                    "кариера",
                ],
                "arabic": [
                    "الخبرة",
                    "خبرة العمل",
                    "الخبرة المهنية",
                    "المسيرة المهنية",
                    "التوظيف",
                    "العمل",
                    "الوظائف",
                ],
                "hebrew": [
                    "ניסיון",
                    "ניסיון מקצועי",
                    "ניסיון עבודה",
                    "קריירה",
                    "תעסוקה",
                    "עבודה",
                ],
                "cjk": [
                    "経験",
                    "職歴",
                    "勤務経験",
                    "キャリア",
                    "仕事の経験",
                    "工作经验",
                    "职业经历",
                    "工作经历",
                    "职场经验",
                    "工作經驗",
                    "職業經歷",
                    "職場經驗",
                    "경력",
                    "업무경험",
                    "직장경험",
                    "근무경력",
                ],
            },
            SectionType.EDUCATION: {
                "latin": [
                    "education",
                    "academic background",
                    "qualifications",
                    "studies",
                    "éducation",
                    "formation",
                    "études",
                    "diplômes",
                    "cursus",
                    "educación",
                    "formación",
                    "estudios",
                    "titulación",
                    "educazione",
                    "formazione",
                    "studi",
                    "qualificazioni",
                    "ausbildung",
                    "bildung",
                    "studium",
                    "qualifikationen",
                    "educação",
                    "formação",
                    "estudos",
                    "qualificações",
                    "uddannelse",
                    "studier",
                    "kvalifikationer",
                ],
                "cyrillic": [
                    "образование",
                    "обучение",
                    "учеба",
                    "квалификация",
                    "освіта",
                    "навчання",
                    "кваліфікація",
                    "образование",
                    "обучение",
                    "квалификация",
                ],
                "arabic": [
                    "التعليم",
                    "الخلفية الأكاديمية",
                    "المؤهلات",
                    "الدراسة",
                    "التحصيل الدراسي",
                    "الشهادات",
                ],
                "hebrew": [
                    "השכלה",
                    "רקע אקדמי",
                    "כישורים",
                    "לימודים",
                    "הכשרה",
                    "תארים",
                ],
                "cjk": [
                    "学歴",
                    "教育",
                    "教育背景",
                    "学習歴",
                    "資格",
                    "学历",
                    "教育背景",
                    "学习经历",
                    "教育经历",
                    "學歷",
                    "教育背景",
                    "學習經歷",
                    "학력",
                    "교육",
                    "교육배경",
                    "학습경력",
                ],
            },
            SectionType.SKILLS: {
                "latin": [
                    "skills",
                    "competencies",
                    "abilities",
                    "expertise",
                    "technical skills",
                    "compétences",
                    "aptitudes",
                    "savoir-faire",
                    "expertise",
                    "habilidades",
                    "competencias",
                    "destrezas",
                    "capacidades",
                    "competenze",
                    "abilità",
                    "capacità",
                    "expertise",
                    "fähigkeiten",
                    "kompetenzen",
                    "fertigkeiten",
                    "expertise",
                    "habilidades",
                    "competências",
                    "capacidades",
                    "perícias",
                    "færdigheder",
                    "kompetencer",
                    "evner",
                ],
                "cyrillic": [
                    "навыки",
                    "умения",
                    "компетенции",
                    "способности",
                    "навички",
                    "вміння",
                    "компетенції",
                    "умения",
                    "способности",
                    "компетенции",
                ],
                "arabic": [
                    "المهارات",
                    "القدرات",
                    "الكفاءات",
                    "الخبرات",
                    "المهارات التقنية",
                    "القدرات المهنية",
                ],
                "hebrew": [
                    "כישורים",
                    "יכולות",
                    "מיומנויות",
                    "מומחיות",
                    "כישורים טכניים",
                    "יכולות מקצועיות",
                ],
                "cjk": [
                    "スキル",
                    "技能",
                    "能力",
                    "専門知識",
                    "技術",
                    "技能",
                    "能力",
                    "专业技能",
                    "技术能力",
                    "技能",
                    "能力",
                    "專業技能",
                    "기술",
                    "능력",
                    "역량",
                    "전문지식",
                ],
            },
            SectionType.LANGUAGES: {
                "latin": [
                    "languages",
                    "language skills",
                    "linguistic abilities",
                    "langues",
                    "compétences linguistiques",
                    "idiomes",
                    "idiomas",
                    "competencias lingüísticas",
                    "lenguas",
                    "lingue",
                    "competenze linguistiche",
                    "idiomi",
                    "sprachen",
                    "sprachkenntnisse",
                    "sprachfähigkeiten",
                    "idiomas",
                    "competências linguísticas",
                    "línguas",
                    "sprog",
                    "sprogfærdigheder",
                ],
                "cyrillic": [
                    "языки",
                    "знание языков",
                    "языковые навыки",
                    "мови",
                    "знання мов",
                    "мовні навички",
                    "езици",
                    "езикови умения",
                ],
                "arabic": [
                    "اللغات",
                    "المهارات اللغوية",
                    "إتقان اللغات",
                    "القدرات اللغوية",
                ],
                "hebrew": ["שפות", "כישורי שפה", "יכולות לשוניות", "מיומנויות לשוניות"],
                "cjk": [
                    "言語",
                    "語学",
                    "言語能力",
                    "外国語",
                    "语言",
                    "语言能力",
                    "外语能力",
                    "語言",
                    "語言能力",
                    "外語能力",
                    "언어",
                    "어학",
                    "언어능력",
                    "외국어",
                ],
            },
            SectionType.PROJECTS: {
                "latin": [
                    "projects",
                    "portfolio",
                    "work samples",
                    "achievements",
                    "projets",
                    "réalisations",
                    "portfolio",
                    "travaux",
                    "proyectos",
                    "realizaciones",
                    "portafolio",
                    "trabajos",
                    "progetti",
                    "realizzazioni",
                    "portfolio",
                    "lavori",
                    "projekte",
                    "arbeiten",
                    "portfolio",
                    "leistungen",
                    "projetos",
                    "realizações",
                    "portfólio",
                    "trabalhos",
                ],
                "cyrillic": [
                    "проекты",
                    "портфолио",
                    "работы",
                    "достижения",
                    "проекти",
                    "портфоліо",
                    "роботи",
                    "проекти",
                    "портфолио",
                    "работи",
                ],
                "arabic": [
                    "المشاريع",
                    "الأعمال",
                    "الإنجازات",
                    "نماذج العمل",
                    "المحفظة",
                ],
                "hebrew": [
                    "פרויקטים",
                    "עבודות",
                    "הישגים",
                    "תיק עבודות",
                    "דוגמאות עבודה",
                ],
                "cjk": [
                    "プロジェクト",
                    "作品",
                    "実績",
                    "ポートフォリオ",
                    "项目",
                    "作品",
                    "项目经验",
                    "作品集",
                    "項目",
                    "作品",
                    "項目經驗",
                    "프로젝트",
                    "작품",
                    "포트폴리오",
                    "실적",
                ],
            },
            SectionType.CERTIFICATIONS: {
                "latin": [
                    "certifications",
                    "certificates",
                    "credentials",
                    "licenses",
                    "certifications",
                    "certificats",
                    "diplômes",
                    "licences",
                    "certificaciones",
                    "certificados",
                    "credenciales",
                    "licencias",
                    "certificazioni",
                    "certificati",
                    "credenziali",
                    "licenze",
                    "zertifizierungen",
                    "zertifikate",
                    "bescheinigungen",
                    "lizenzen",
                    "certificações",
                    "certificados",
                    "credenciais",
                    "licenças",
                ],
                "cyrillic": [
                    "сертификаты",
                    "сертификация",
                    "дипломы",
                    "лицензии",
                    "сертифікати",
                    "сертифікація",
                    "ліцензії",
                    "сертификати",
                    "лицензи",
                ],
                "arabic": [
                    "الشهادات",
                    "التصديقات",
                    "التراخيص",
                    "الاعتمادات",
                    "شهادات التقدير",
                ],
                "hebrew": ["תעודות", "הסמכות", "רישיונות", "אישורים", "תעודות הכרה"],
                "cjk": [
                    "資格",
                    "認定",
                    "証明書",
                    "免許",
                    "ライセンス",
                    "资格",
                    "认证",
                    "证书",
                    "执照",
                    "資格",
                    "認證",
                    "證書",
                    "자격증",
                    "인증",
                    "면허",
                    "증명서",
                ],
            },
            SectionType.AWARDS: {
                "latin": [
                    "awards",
                    "honors",
                    "achievements",
                    "recognitions",
                    "distinctions",
                    "prix",
                    "récompenses",
                    "distinctions",
                    "honneurs",
                    "reconnaissances",
                    "premios",
                    "reconocimientos",
                    "distinciones",
                    "honores",
                    "logros",
                    "premi",
                    "riconoscimenti",
                    "distinzioni",
                    "onori",
                    "risultati",
                    "auszeichnungen",
                    "preise",
                    "ehrungen",
                    "anerkennungen",
                    "prêmios",
                    "reconhecimentos",
                    "distinções",
                    "honrarias",
                ],
                "cyrillic": [
                    "награды",
                    "достижения",
                    "признания",
                    "отличия",
                    "нагороди",
                    "досягнення",
                    "відзнаки",
                    "награди",
                    "постижения",
                    "признания",
                ],
                "arabic": [
                    "الجوائز",
                    "التكريمات",
                    "الإنجازات",
                    "التقديرات",
                    "الأوسمة",
                    "الشهادات التقديرية",
                ],
                "hebrew": [
                    "פרסים",
                    "הכרה",
                    "הישגים",
                    "אותות הוקרה",
                    "ציונים",
                    "תעודות הוקרה",
                ],
                "cjk": [
                    "受賞",
                    "表彰",
                    "栄誉",
                    "功績",
                    "賞",
                    "奖项",
                    "荣誉",
                    "表彰",
                    "成就",
                    "獎項",
                    "榮譽",
                    "表彰",
                    "상",
                    "수상",
                    "포상",
                    "영예",
                ],
            },
            SectionType.REFERENCES: {
                "latin": [
                    "references",
                    "recommendations",
                    "testimonials",
                    "referees",
                    "références",
                    "recommandations",
                    "témoignages",
                    "répondants",
                    "referencias",
                    "recomendaciones",
                    "testimonios",
                    "avalistas",
                    "referenze",
                    "raccomandazioni",
                    "testimonianze",
                    "garanti",
                    "referenzen",
                    "empfehlungen",
                    "zeugnisse",
                    "bürgen",
                    "referências",
                    "recomendações",
                    "testemunhos",
                    "avalistas",
                ],
                "cyrillic": [
                    "рекомендации",
                    "отзывы",
                    "референсы",
                    "поручители",
                    "рекомендації",
                    "відгуки",
                    "поручителі",
                    "препоръки",
                    "отзиви",
                    "референси",
                ],
                "arabic": [
                    "المراجع",
                    "التوصيات",
                    "الشهادات",
                    "المزكين",
                    "رسائل التوصية",
                ],
                "hebrew": ["המלצות", "מליצים", "עדויות", "ערבים", "מכתבי המלצה"],
                "cjk": [
                    "推薦状",
                    "紹介状",
                    "推薦者",
                    "身元保証人",
                    "推荐信",
                    "推荐人",
                    "介绍人",
                    "证明人",
                    "推薦信",
                    "推薦人",
                    "介紹人",
                    "추천서",
                    "추천인",
                    "보증인",
                    "참고인",
                ],
            },
            SectionType.INTERESTS: {
                "latin": [
                    "interests",
                    "hobbies",
                    "activities",
                    "personal interests",
                    "centres d'intérêt",
                    "intérêts",
                    "loisirs",
                    "activités",
                    "intereses",
                    "aficiones",
                    "actividades",
                    "pasatiempos",
                    "interessi",
                    "hobby",
                    "attività",
                    "passatempi",
                    "interessen",
                    "hobbys",
                    "aktivitäten",
                    "freizeitaktivitäten",
                    "interesses",
                    "hobbies",
                    "atividades",
                    "passatempos",
                ],
                "cyrillic": [
                    "интересы",
                    "хобби",
                    "увлечения",
                    "деятельность",
                    "інтереси",
                    "захоплення",
                    "діяльність",
                    "интереси",
                    "хобита",
                    "дейности",
                ],
                "arabic": [
                    "الاهتمامات",
                    "الهوايات",
                    "الأنشطة",
                    "الاهتمامات الشخصية",
                    "النشاطات",
                ],
                "hebrew": [
                    "תחומי עניין",
                    "תחביבים",
                    "פעילויות",
                    "עניינים אישיים",
                    "נושאים מעניינים",
                ],
                "cjk": [
                    "趣味",
                    "興味",
                    "アクティビティ",
                    "個人的な関心",
                    "兴趣",
                    "爱好",
                    "个人兴趣",
                    "活动",
                    "興趣",
                    "愛好",
                    "個人興趣",
                    "관심사",
                    "취미",
                    "활동",
                    "개인적 관심",
                ],
            },
        }

        # Compile regex patterns for each header type
        self.compiled_patterns = {}
        for section_type, script_patterns in self.header_patterns.items():
            self.compiled_patterns[section_type] = {}
            for script, patterns in script_patterns.items():
                # Create case-insensitive patterns with word boundaries
                regex_patterns = []
                for pattern in patterns:
                    # Escape special regex characters but allow for partial matches
                    escaped_pattern = re.escape(pattern).replace(r"\ ", r"\s+")
                    regex_patterns.append(rf"\b{escaped_pattern}\b")

                self.compiled_patterns[section_type][script] = re.compile(
                    "|".join(regex_patterns), re.IGNORECASE | re.UNICODE
                )

    def _setup_fuzzy_matching(self):
        """Setup fuzzy matching parameters."""
        self.fuzzy_threshold = 0.8  # Minimum similarity for fuzzy matches
        self.max_edit_distance = 2  # Maximum edit distance for fuzzy matches

    def recognize_header(self, text: str, doc_id: str = "unknown") -> HeaderMatch:
        """
        Recognize CV section header in multilingual text.

        Args:
            text: Header text to analyze
            doc_id: Document ID for metrics

        Returns:
            HeaderMatch with recognition result
        """
        metrics = get_metrics_collector(doc_id)
        clean_text = text.strip()

        self.logger.debug(f"HEADER_RECOGNIZE: analyzing '{clean_text}'")

        if not clean_text:
            return HeaderMatch(
                text=text,
                section_type=SectionType.UNKNOWN,
                confidence=0.0,
                language_detected="unknown",
                script_type=ScriptType.UNKNOWN,
                normalized_form="",
                match_method="none",
            )

        # Step 1: Detect text direction and script
        direction_analysis = detect_text_direction(clean_text)
        primary_script = direction_analysis.primary_script

        # Step 2: Normalize text for matching
        normalized_text = self._normalize_text(clean_text)

        # Step 3: Try exact pattern matching
        exact_match = self._try_exact_matching(normalized_text, primary_script)
        if exact_match and exact_match.confidence > 0.9:
            exact_match.text = text
            self.logger.info(
                f"HEADER_RECOGNIZE: exact match | {exact_match.section_type.value}"
            )
            return exact_match

        # Step 4: Try fuzzy matching
        fuzzy_match = self._try_fuzzy_matching(normalized_text, primary_script)
        if fuzzy_match and fuzzy_match.confidence > 0.7:
            fuzzy_match.text = text
            self.logger.info(
                f"HEADER_RECOGNIZE: fuzzy match | {fuzzy_match.section_type.value}"
            )
            return fuzzy_match

        # Step 5: Try cross-script matching (transliteration/translation)
        cross_script_match = self._try_cross_script_matching(normalized_text)
        if cross_script_match and cross_script_match.confidence > 0.6:
            cross_script_match.text = text
            self.logger.info(
                f"HEADER_RECOGNIZE: cross-script match | {cross_script_match.section_type.value}"
            )
            return cross_script_match

        # Step 6: Return unknown match
        unknown_match = HeaderMatch(
            text=text,
            section_type=SectionType.UNKNOWN,
            confidence=0.0,
            language_detected=self._detect_language(primary_script),
            script_type=primary_script,
            normalized_form=normalized_text,
            match_method="none",
        )

        self.logger.debug(f"HEADER_RECOGNIZE: no match found | text='{clean_text}'")
        return unknown_match

    def _normalize_text(self, text: str) -> str:
        """Normalize text for matching."""
        # Remove excessive whitespace
        normalized = re.sub(r"\s+", " ", text.strip())

        # Remove common punctuation and symbols
        normalized = re.sub(r"[:\-–—_•·▪▫◦‣⁃]+\s*", " ", normalized)

        # Normalize Unicode (decompose and recompose)
        normalized = unicodedata.normalize("NFKC", normalized)

        return normalized.lower()

    def _try_exact_matching(
        self, text: str, primary_script: ScriptType
    ) -> Optional[HeaderMatch]:
        """Try exact pattern matching."""
        script_key = self._script_to_key(primary_script)

        for section_type, script_patterns in self.compiled_patterns.items():
            if script_key in script_patterns:
                pattern = script_patterns[script_key]
                if pattern.search(text):
                    return HeaderMatch(
                        text="",  # Will be set by caller
                        section_type=section_type,
                        confidence=0.95,
                        language_detected=self._detect_language(primary_script),
                        script_type=primary_script,
                        normalized_form=text,
                        match_method="exact",
                    )

        return None

    def _try_fuzzy_matching(
        self, text: str, primary_script: ScriptType
    ) -> Optional[HeaderMatch]:
        """Try fuzzy matching with edit distance."""
        script_key = self._script_to_key(primary_script)
        best_match = None
        best_score = 0.0

        for section_type, script_patterns in self.header_patterns.items():
            if script_key in script_patterns:
                patterns = script_patterns[script_key]
                for pattern in patterns:
                    similarity = self._calculate_similarity(text, pattern.lower())
                    if similarity > best_score and similarity >= self.fuzzy_threshold:
                        best_score = similarity
                        best_match = HeaderMatch(
                            text="",  # Will be set by caller
                            section_type=section_type,
                            confidence=similarity,
                            language_detected=self._detect_language(primary_script),
                            script_type=primary_script,
                            normalized_form=text,
                            match_method="fuzzy",
                        )

        return best_match

    def _try_cross_script_matching(self, text: str) -> Optional[HeaderMatch]:
        """Try matching across different scripts (for mixed-language headers)."""
        # This is a simplified implementation
        # In practice, you might want to use transliteration libraries
        best_match = None
        best_score = 0.0

        # Try matching against all scripts
        for section_type, script_patterns in self.header_patterns.items():
            for script, patterns in script_patterns.items():
                for pattern in patterns:
                    similarity = self._calculate_similarity(text, pattern.lower())
                    if similarity > best_score and similarity >= 0.6:
                        best_score = similarity
                        script_type = self._key_to_script(script)
                        best_match = HeaderMatch(
                            text="",  # Will be set by caller
                            section_type=section_type,
                            confidence=similarity
                            * 0.8,  # Reduce confidence for cross-script
                            language_detected=self._detect_language(script_type),
                            script_type=script_type,
                            normalized_form=text,
                            match_method="cross_script",
                        )

        return best_match

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """Calculate similarity between two strings using simple edit distance."""
        if not text1 or not text2:
            return 0.0

        # Simple implementation of normalized edit distance
        len1, len2 = len(text1), len(text2)
        if len1 == 0:
            return 0.0 if len2 > 0 else 1.0
        if len2 == 0:
            return 0.0

        # Create distance matrix
        distances = [[0] * (len2 + 1) for _ in range(len1 + 1)]

        # Initialize first row and column
        for i in range(len1 + 1):
            distances[i][0] = i
        for j in range(len2 + 1):
            distances[0][j] = j

        # Fill distance matrix
        for i in range(1, len1 + 1):
            for j in range(1, len2 + 1):
                cost = 0 if text1[i - 1] == text2[j - 1] else 1
                distances[i][j] = min(
                    distances[i - 1][j] + 1,  # deletion
                    distances[i][j - 1] + 1,  # insertion
                    distances[i - 1][j - 1] + cost,  # substitution
                )

        # Calculate similarity (1 - normalized edit distance)
        max_len = max(len1, len2)
        similarity = 1.0 - (distances[len1][len2] / max_len)
        return max(0.0, similarity)

    def _script_to_key(self, script_type: ScriptType) -> str:
        """Convert script type to key for pattern lookup."""
        script_mapping = {
            ScriptType.LATIN: "latin",
            ScriptType.CYRILLIC: "cyrillic",
            ScriptType.ARABIC: "arabic",
            ScriptType.HEBREW: "hebrew",
            ScriptType.CJK: "cjk",
        }
        return script_mapping.get(script_type, "latin")

    def _key_to_script(self, key: str) -> ScriptType:
        """Convert key back to script type."""
        key_mapping = {
            "latin": ScriptType.LATIN,
            "cyrillic": ScriptType.CYRILLIC,
            "arabic": ScriptType.ARABIC,
            "hebrew": ScriptType.HEBREW,
            "cjk": ScriptType.CJK,
        }
        return key_mapping.get(key, ScriptType.LATIN)

    def _detect_language(self, script_type: ScriptType) -> str:
        """Detect likely language from script type."""
        language_mapping = {
            ScriptType.LATIN: "en",  # Default to English for Latin
            ScriptType.CYRILLIC: "ru",  # Default to Russian for Cyrillic
            ScriptType.ARABIC: "ar",
            ScriptType.HEBREW: "he",
            ScriptType.CJK: "zh",  # Default to Chinese for CJK
            ScriptType.DEVANAGARI: "hi",
            ScriptType.THAI: "th",
        }
        return language_mapping.get(script_type, "unknown")


# Convenience functions
def recognize_header(text: str, doc_id: str = "unknown") -> HeaderMatch:
    """Convenience function for header recognition."""
    recognizer = MultilingualHeaderRecognizer()
    return recognizer.recognize_header(text, doc_id)


def get_section_type(text: str) -> SectionType:
    """Quick function to get section type from header text."""
    match = recognize_header(text)
    return match.section_type


def is_header_text(text: str, threshold: float = 0.7) -> bool:
    """Check if text is likely a section header."""
    match = recognize_header(text)
    return match.confidence >= threshold


# Export main classes and functions
__all__ = [
    "SectionType",
    "HeaderMatch",
    "MultilingualHeaderRecognizer",
    "recognize_header",
    "get_section_type",
    "is_header_text",
]
