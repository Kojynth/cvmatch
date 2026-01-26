"""
Project Router - Routage intelligent des projets vs expériences professionnelles.

Distingue automatiquement les projets personnels/académiques/open-source
des expériences professionnelles classiques avec scoring et règles expertes.
"""

import re
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


class ContentType(Enum):
    """Types de contenu identifiés."""
    PROJECT = "project"
    EXPERIENCE = "experience"
    AMBIGUOUS = "ambiguous"


@dataclass
class RoutingDecision:
    """Décision de routage pour un élément."""
    content_type: ContentType
    confidence: float
    reasoning: str
    indicators: List[str]
    suggested_section: str


class ProjectRouter:
    """Routeur intelligent pour distinguer projets et expériences."""
    
    def __init__(self):
        self.logger = get_safe_logger(f"{__name__}.ProjectRouter", cfg=DEFAULT_PII_CONFIG)
        
        # Indicateurs forts de projets
        self.project_indicators = {
            # Mots-clés projet explicites
            "explicit": [
                "projet", "project", "progetti", "proyecto",
                "réalisation", "realisation", "realization", 
                "création", "creation", "sviluppo",
                "développement", "development", "desarrollo",
                "conception", "design", "diseño",
                "prototype", "prototipo", "mvp", "proof of concept", "poc"
            ],
            
            # Technologies et frameworks (indicateur de projet technique)
            "tech": [
                "github", "gitlab", "bitbucket", "git",
                "react", "angular", "vue", "node", "express", "django", "flask",
                "python", "javascript", "java", "c++", "c#", "php", "ruby",
                "docker", "kubernetes", "aws", "azure", "gcp",
                "api", "rest", "graphql", "microservice", "microservices",
                "mongodb", "postgresql", "mysql", "redis", "elasticsearch",
                "tensorflow", "pytorch", "machine learning", "ml", "ai", "ia"
            ],
            
            # Contexte académique/personnel
            "academic": [
                "stage de fin d'études", "projet de fin d'études", "final project",
                "thèse", "mémoire", "thesis", "dissertation",
                "personnel", "personal", "personale", "privé", "private",
                "open source", "opensource", "contribution", "community",
                "hackathon", "concours", "competition", "contest",
                "bénévole", "volunteer", "volontariat", "voluntario"
            ],
            
            # Durée courte (projets sont souvent courts)
            "duration": [
                r"\b\d{1,2}\s*(?:jour|day|días?|giorni?)\b",  # X jours
                r"\b\d{1,2}\s*(?:semaine|week|semana|settimana)\b",  # X semaines  
                r"\b\d{1,2}\s*(?:mois|month|mes|mese)\b",  # X mois (court)
                r"weekend", "week-end", "fin de semaine"
            ],
            
            # Verbes d'action technique/créative
            "action_verbs": [
                "développé", "developed", "desarrollado", "sviluppato",
                "créé", "created", "creado", "creato",
                "conçu", "designed", "diseñado", "progettato", 
                "implémenté", "implemented", "implementado",
                "prototypé", "prototyped", "prototipado",
                "programmé", "programmed", "programado",
                "codé", "coded", "codificado",
                "construit", "built", "construido", "costruito"
            ]
        }
        
        # Indicateurs forts d'expériences professionnelles
        self.experience_indicators = {
            # Contexte professionnel explicite
            "professional": [
                "poste", "position", "posto", "puesto",
                "fonction", "role", "ruolo", "función",
                "responsabilités", "responsibilities", "responsabilita",
                "missions", "mission", "missioni", "misiones",
                "équipe", "team", "equipe", "squadra",
                "manager", "chef", "supervisor", "lead",
                "client", "cliente", "customer", "clientela",
                "chiffre d'affaires", "revenue", "turnover", "fatturato"
            ],
            
            # Durée longue (expériences sont souvent longues)
            "long_duration": [
                r"\b(?:plus de|more than|oltre|más de)\s*\d+\s*(?:an|year|anno|año)",  # Plus de X ans
                r"\b\d+\s*(?:années?|years?|anni|años)\b",  # X années
                r"\b(?:depuis|since|da|desde)\s+\d{4}\b",  # Depuis YYYY
                r"\b(?:permanent|cdi|permanent|fisso|fijo)\b"  # Contrat permanent
            ],
            
            # Verbes d'action managérial/business
            "business_verbs": [
                "managé", "managed", "managiato", "manejado",
                "dirigé", "directed", "diretto", "dirigido", 
                "supervisé", "supervised", "supervisionado",
                "coordonné", "coordinated", "coordinado",
                "négocié", "negotiated", "negoziato", "negociado",
                "vendu", "sold", "venduto", "vendido",
                "généré", "generated", "generato", "generado"
            ],
            
            # Secteurs d'activité
            "sectors": [
                "banque", "bank", "banca", "banco",
                "assurance", "insurance", "assicurazione", "seguro",
                "conseil", "consulting", "consultoria", "consulenza",
                "retail", "commerce", "commercio", "comercio",
                "industrie", "industry", "industria",
                "finance", "finanza", "finanzas"
            ]
        }
        
        # Patterns regex compilés pour performance
        self._compile_patterns()
        
        # Poids pour le scoring
        self.weights = {
            "explicit_project": 0.4,
            "tech_indicators": 0.2,
            "academic_context": 0.3,
            "short_duration": 0.15,
            "creative_verbs": 0.1,
            "professional_context": -0.3,  # Négatif = indicateur d'expérience
            "long_duration": -0.2,
            "business_verbs": -0.25,
            "company_sector": -0.15
        }
    
    def _compile_patterns(self):
        """Compile les patterns regex pour la performance."""
        self.compiled_patterns = {}
        
        # Compiler les patterns de durée
        for category in ["duration", "long_duration"]:
            for source_dict in [self.project_indicators, self.experience_indicators]:
                if category in source_dict:
                    patterns_key = f"{category}_{'project' if source_dict == self.project_indicators else 'experience'}"
                    self.compiled_patterns[patterns_key] = [
                        re.compile(pattern, re.IGNORECASE) 
                        for pattern in source_dict[category]
                    ]
    
    def analyze_text_indicators(self, text: str) -> Dict[str, Any]:
        """Analyse les indicateurs dans un texte."""
        if not text:
            return {}
        
        text_lower = text.lower()
        indicators = {
            "project_score": 0.0,
            "experience_score": 0.0,
            "matched_indicators": [],
            "reasoning": []
        }
        
        # Analyser les indicateurs de projet
        for category, keywords in self.project_indicators.items():
            if category in ["duration"]:
                # Gérer les patterns regex
                patterns_key = f"{category}_project"
                if patterns_key in self.compiled_patterns:
                    for pattern in self.compiled_patterns[patterns_key]:
                        if pattern.search(text_lower):
                            weight = self.weights.get(f"short_{category}", 0.1)
                            indicators["project_score"] += weight
                            indicators["matched_indicators"].append(f"project_{category}_regex")
                            indicators["reasoning"].append(f"Duration pattern detected: {category}")
                            break
            else:
                # Gérer les mots-clés simples
                for keyword in keywords:
                    if keyword in text_lower:
                        weight = self._get_category_weight(category, True)
                        indicators["project_score"] += weight
                        indicators["matched_indicators"].append(f"project_{category}_{keyword[:10]}")
                        indicators["reasoning"].append(f"Project keyword: {keyword}")
        
        # Analyser les indicateurs d'expérience
        for category, keywords in self.experience_indicators.items():
            if category in ["long_duration"]:
                # Gérer les patterns regex
                patterns_key = f"{category}_experience"  
                if patterns_key in self.compiled_patterns:
                    for pattern in self.compiled_patterns[patterns_key]:
                        if pattern.search(text_lower):
                            weight = self.weights.get(f"long_{category.split('_')[0]}", -0.1)
                            indicators["experience_score"] += abs(weight)
                            indicators["matched_indicators"].append(f"experience_{category}_regex")
                            indicators["reasoning"].append(f"Long duration pattern: {category}")
                            break
            else:
                # Gérer les mots-clés simples
                for keyword in keywords:
                    if keyword in text_lower:
                        weight = abs(self._get_category_weight(category, False))
                        indicators["experience_score"] += weight
                        indicators["matched_indicators"].append(f"experience_{category}_{keyword[:10]}")
                        indicators["reasoning"].append(f"Experience keyword: {keyword}")
        
        return indicators
    
    def _get_category_weight(self, category: str, is_project: bool) -> float:
        """Obtient le poids d'une catégorie."""
        weight_map = {
            "explicit": "explicit_project" if is_project else "professional_context",
            "tech": "tech_indicators",
            "academic": "academic_context", 
            "action_verbs": "creative_verbs" if is_project else "business_verbs",
            "professional": "professional_context",
            "business_verbs": "business_verbs",
            "sectors": "company_sector"
        }
        
        weight_key = weight_map.get(category, category)
        return self.weights.get(weight_key, 0.1 if is_project else -0.1)
    
    def route_content(self, text: str, context: Optional[Dict[str, Any]] = None) -> RoutingDecision:
        """
        Route le contenu vers projet ou expérience.
        
        Args:
            text: Texte à analyser
            context: Contexte additionnel (section, métadonnées, etc.)
            
        Returns:
            RoutingDecision avec le type de contenu et la confiance
        """
        if not text:
            return RoutingDecision(
                content_type=ContentType.AMBIGUOUS,
                confidence=0.0,
                reasoning="Empty text",
                indicators=[],
                suggested_section="experience"  # Défaut
            )
        
        # Analyser les indicateurs textuels
        indicators = self.analyze_text_indicators(text)
        
        project_score = indicators["project_score"]
        experience_score = indicators["experience_score"]
        
        # Ajustements contextuels avec logique section-aware renforcée
        if context:
            section_name = context.get("section_name", "").lower()
            section_hint = context.get("section_hint", "").lower()
            has_company = context.get("has_company", False)
            has_dates = context.get("has_dates", False)
            
            # Section-aware routing: si section_hint=projects, forte préférence projects
            if any(keyword in section_hint for keyword in ["projet", "project", "réalisation", "creation"]):
                project_score += 0.5  # Forte pondération
                indicators["reasoning"].append("Section hint: explicitly in projects section")
                
                # Additional: si pas d'évidence d'emploi fort, router vers projects
                if not self._has_strong_employment_evidence(text, context):
                    project_score += 0.3
                    indicators["reasoning"].append("No strong employment evidence in project section")
            
            # Bonus si dans une section "projet" (nom de section)
            elif any(keyword in section_name for keyword in ["projet", "project", "réalisation", "creation"]):
                project_score += 0.3
                indicators["reasoning"].append("Section context: project section")
            
            # Validation emploi: si classification=experience mais section=projects, vérifier emploi
            classification = context.get("classification", "").lower()
            if (classification == "experience" and 
                any(keyword in section_hint for keyword in ["projet", "project"]) and
                not self._validate_employment_context(text, context)):
                # Override: pas assez d'évidence d'emploi, router vers projects
                project_score += 0.4
                experience_score -= 0.3
                indicators["reasoning"].append("Employment validation failed, overriding to projects")
            
            # Malus si entreprise explicite (sauf si tech/open source/academic)
            if has_company and not any(keyword in text.lower() 
                                     for keyword in ["github", "open", "personnel", "personal", 
                                                   "université", "école", "academic", "research"]):
                experience_score += 0.2
                indicators["reasoning"].append("Context: explicit company mentioned")
        
        # Décision finale
        net_score = project_score - experience_score
        confidence = min(abs(net_score), 1.0)
        
        if net_score > 0.3:
            content_type = ContentType.PROJECT
            suggested_section = "projects"
        elif net_score < -0.3:
            content_type = ContentType.EXPERIENCE
            suggested_section = "experience"
        else:
            content_type = ContentType.AMBIGUOUS
            # En cas d'ambiguité, privilégier expérience (plus courant)
            suggested_section = "experience" if experience_score >= project_score else "projects"
        
        reasoning = f"Score: project={project_score:.2f}, experience={experience_score:.2f}, net={net_score:.2f}"
        
        self.logger.debug(f"PROJECT_ROUTER: decision | text='{text[:50]}...' "
                         f"type={content_type.value} confidence={confidence:.2f} "
                         f"project_score={project_score:.2f} experience_score={experience_score:.2f}")
        
        return RoutingDecision(
            content_type=content_type,
            confidence=confidence,
            reasoning=reasoning,
            indicators=indicators["matched_indicators"][:10],  # Limiter pour logs
            suggested_section=suggested_section
        )
    
    def _has_strong_employment_evidence(self, text: str, context: Optional[Dict[str, Any]] = None) -> bool:
        """
        Vérifie s'il y a des preuves fortes d'un contexte d'emploi professionnel.
        
        Args:
            text: Texte à analyser
            context: Contexte additionnel
            
        Returns:
            True si des preuves d'emploi sont détectées
        """
        employment_keywords = [
            # Contrats de travail
            "cdi", "cdd", "contrat", "contract", "emploi", "employment", "job",
            "salarié", "employee", "salary", "salaire", "rémunération",
            
            # Hiérarchie professionnelle  
            "manager", "chef", "directeur", "supervisor", "responsable",
            "équipe", "team", "collaborateur", "colleague", "subordinate",
            
            # Contexte d'entreprise
            "département", "department", "division", "service",
            "budget", "objectif", "target", "kpi", "performance",
            "client", "customer", "meeting", "réunion"
        ]
        
        # Vérifier les mots-clés d'emploi
        text_lower = text.lower()
        employment_score = sum(1 for keyword in employment_keywords if keyword in text_lower)
        
        # Vérifier le contexte
        if context:
            # Présence de company + title professionnel
            has_company = context.get("has_company", False)
            title = context.get("title", "").lower()
            professional_titles = ["développeur", "developer", "ingénieur", "engineer", 
                                 "consultant", "analyst", "manager", "chef", "responsable"]
            has_professional_title = any(title_word in title for title_word in professional_titles)
            
            if has_company and has_professional_title:
                employment_score += 2
        
        # Seuil: au moins 2 indicateurs d'emploi
        is_employment = employment_score >= 2
        
        self.logger.debug(f"EMPLOYMENT_CHECK: text='{text[:30]}...' score={employment_score} "
                         f"is_employment={is_employment}")
        
        return is_employment
    
    def _validate_employment_context(self, text: str, context: Optional[Dict[str, Any]] = None) -> bool:
        """
        Validation renforcée du contexte d'emploi pour éviter la misclassification.
        
        Args:
            text: Texte à analyser  
            context: Contexte additionnel
            
        Returns:
            True si le contexte d'emploi est validé
        """
        # Whitelist d'emploi explicite
        employment_whitelist = [
            # Contrats français
            r"\b(?:cdi|cdd|stage(?:\s+professionnel)?|apprentissage|alternance)\b",
            # Hiérarchie claire
            r"\b(?:embauché|recruté|promoted|promu|hired)\b", 
            # Durée longue (indicateur d'emploi vs projet)
            r"\b(?:\d+\s*(?:années?|years?|ans))\b",
            # Contexte salarial
            r"\b(?:salaire|salary|rémunération|benefits|avantages)\b"
        ]
        
        # Compter les correspondances avec la whitelist
        whitelist_matches = 0
        for pattern in employment_whitelist:
            if re.search(pattern, text, re.IGNORECASE):
                whitelist_matches += 1
        
        # Vérifier d'autres indicateurs
        has_strong_evidence = self._has_strong_employment_evidence(text, context)
        
        # Decision: au moins 1 match whitelist OU évidence forte
        is_valid_employment = whitelist_matches >= 1 or has_strong_evidence
        
        self.logger.debug(f"EMPLOYMENT_VALIDATION: text='{text[:30]}...' "
                         f"whitelist_matches={whitelist_matches} strong_evidence={has_strong_evidence} "
                         f"is_valid={is_valid_employment}")
        
        return is_valid_employment
    
    def should_route_to_projects(self, text: str, context: Optional[Dict[str, Any]] = None,
                                confidence_threshold: float = 0.6) -> bool:
        """Détermine si le contenu doit aller en section projets."""
        decision = self.route_content(text, context)
        
        should_route = (decision.content_type == ContentType.PROJECT and 
                       decision.confidence >= confidence_threshold)
        
        if should_route:
            self.logger.info(f"PROJECT_ROUTER: routing_to_projects | text='{text[:30]}...' "
                           f"confidence={decision.confidence:.2f}")
        
        return should_route
    
    def get_routing_stats(self) -> Dict[str, Any]:
        """Obtient les statistiques de routage (placeholder pour implémentation future)."""
        return {
            "project_routes": 0,
            "experience_routes": 0, 
            "ambiguous_routes": 0,
            "total_routes": 0
        }


# Instance globale
_project_router = None


def get_project_router() -> ProjectRouter:
    """Obtient l'instance globale du routeur de projets."""
    global _project_router
    if _project_router is None:
        _project_router = ProjectRouter()
    return _project_router


def is_project_content(text: str, context: Optional[Dict[str, Any]] = None) -> bool:
    """Détermine si le contenu est un projet."""
    router = get_project_router()
    decision = router.route_content(text, context)
    return decision.content_type == ContentType.PROJECT


def route_to_appropriate_section(text: str, context: Optional[Dict[str, Any]] = None) -> str:
    """Route vers la section appropriée (projects ou experience)."""
    router = get_project_router()
    decision = router.route_content(text, context)
    return decision.suggested_section


if __name__ == "__main__":
    # Tests du routeur de projets
    router = ProjectRouter()
    
    test_cases = [
        # Projets évidents
        {
            "text": "Développement d'une application mobile React Native - Projet personnel de gestion de tâches avec API Node.js et base MongoDB",
            "context": {"section_name": "Projets", "has_company": False},
            "expected": ContentType.PROJECT
        },
        {
            "text": "Création d'un bot Discord en Python - Projet open source sur GitHub avec plus de 100 stars",
            "context": {"has_company": False},
            "expected": ContentType.PROJECT
        },
        {
            "text": "Prototype de machine learning pour prédiction de ventes - 2 semaines - TensorFlow",
            "context": {},
            "expected": ContentType.PROJECT
        },
        
        # Expériences évidentes  
        {
            "text": "Développeur Full-Stack chez Capgemini - Missions client banque, équipe de 5 personnes, 2 ans",
            "context": {"has_company": True, "has_dates": True},
            "expected": ContentType.EXPERIENCE
        },
        {
            "text": "Chef de projet IT - Management d'équipe, négociation client, responsable P&L depuis 3 ans",
            "context": {"has_company": True},
            "expected": ContentType.EXPERIENCE
        },
        
        # Cas ambigus
        {
            "text": "Migration système backend - Optimisation performances base de données",
            "context": {},
            "expected": ContentType.AMBIGUOUS
        },
        {
            "text": "Développement API REST - Architecture microservices Docker",
            "context": {"section_name": "Experience"},
            "expected": ContentType.AMBIGUOUS  # Pourrait être les deux
        }
    ]
    
    print("Test du routeur de projets")
    print("=" * 50)
    
    correct_predictions = 0
    
    for i, case in enumerate(test_cases):
        decision = router.route_content(case["text"], case.get("context", {}))
        expected = case["expected"]
        is_correct = decision.content_type == expected
        
        status = "[CORRECT]" if is_correct else "[ERREUR]"
        if is_correct:
            correct_predictions += 1
        
        print(f"{status} Test {i+1}")
        print(f"  Texte: {case['text'][:60]}...")
        print(f"  Attendu: {expected.value}")
        print(f"  Obtenu: {decision.content_type.value} (confiance: {decision.confidence:.2f})")
        print(f"  Section suggérée: {decision.suggested_section}")
        print(f"  Indicateurs: {decision.indicators[:3]}...")
        print()
    
    accuracy = correct_predictions / len(test_cases)
    print(f"Précision globale: {correct_predictions}/{len(test_cases)} ({accuracy*100:.1f}%)")