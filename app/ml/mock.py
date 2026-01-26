"""Mocks ML pour tests offline rapides."""

import re
from typing import List, Dict, Any


class MockZeroShot:
    """Mock du classificateur zero-shot basé sur des heuristiques simples."""
    
    def __init__(self, labels_config: Dict[str, List[str]]):
        """Initialise le mock avec la configuration des labels."""
        self.labels_config = labels_config
        
        # Créer des patterns regex pour chaque section
        self.section_patterns = {}
        for section, keywords in labels_config.items():
            # Créer un pattern qui match les mots-clés (case insensitive)
            pattern_parts = []
            for keyword in keywords:
                # Échapper les caractères spéciaux et permettre les variations
                escaped = re.escape(keyword.lower())
                # Permettre des variations d'accent et d'apostrophe
                escaped = escaped.replace('é', '[eé]').replace('è', '[eè]').replace('à', '[aà]')
                escaped = escaped.replace("'", "['']").replace(' ', r'\s+')
                pattern_parts.append(escaped)
            
            pattern = r'\b(?:' + '|'.join(pattern_parts) + r')\b'
            self.section_patterns[section] = re.compile(pattern, re.IGNORECASE)
    
    def classify(self, text: str) -> Dict[str, Any]:
        """Classifie un texte en utilisant des heuristiques simples."""
        text_lower = text.lower()
        scores = {}
        
        # Calculer un score pour chaque section basé sur les matches
        for section, pattern in self.section_patterns.items():
            matches = pattern.findall(text_lower)
            # Score basé sur le nombre de matches et la longueur du texte
            if matches:
                base_score = len(matches) * 0.3
                # Bonus si le match est au début
                if pattern.search(text_lower[:50]):
                    base_score += 0.2
                # Normaliser par la longueur du texte
                score = min(base_score + 0.1, 0.95)
            else:
                score = 0.05  # Score minimal
            
            scores[section] = score
        
        # Heuristiques spéciales
        self._apply_special_heuristics(text_lower, scores)
        
        # Trouver le meilleur score
        if scores:
            best_section = max(scores.keys(), key=lambda k: scores[k])
            best_score = scores[best_section]
        else:
            best_section = "other"
            best_score = 0.1
        
        return {
            "label": best_section,
            "score": best_score,
            "scores": scores
        }
    
    def _apply_special_heuristics(self, text_lower: str, scores: Dict[str, float]):
        """Applique des heuristiques spéciales pour améliorer la classification."""
        
        # Projets: patterns techniques
        if re.search(r'\b(github|gitlab|projet|site\s+web|app|application|développ)', text_lower):
            scores["projects"] = max(scores.get("projects", 0), 0.7)
        
        # Expériences: patterns temporels + entreprise
        if re.search(r'\b(\d{2}/\d{4}|\d{4})\b', text_lower) and re.search(r'\b(chez|stage|mission|poste)', text_lower):
            scores["experiences"] = max(scores.get("experiences", 0), 0.8)
        
        # Formation: institutions
        if re.search(r'\b(université|école|institut|master|licence|bac)', text_lower):
            scores["education"] = max(scores.get("education", 0), 0.75)
        
        # Compétences techniques: listes de technologies
        if re.search(r'\b(python|java|javascript|html|css|sql|react)\b', text_lower):
            scores["skills"] = max(scores.get("skills", 0), 0.6)
        
        # Contact: patterns d'information personnelle
        if re.search(r'\b(email|tél|phone|adresse|@|\.com)\b', text_lower):
            scores["personal_info"] = max(scores.get("personal_info", 0), 0.9)
        
        # Bénévolat: renforcement
        if re.search(r'\b(bénévol|volontaire|association|humanitaire|collecte)\b', text_lower):
            scores["volunteering"] = max(scores.get("volunteering", 0), 0.8)


class MockNer:
    """Mock du NER français basé sur des patterns simples."""
    
    def __init__(self):
        """Initialise le mock NER."""
        # Patterns pour différents types d'entités
        self.org_patterns = [
            re.compile(r'\b[A-Z][A-Za-z]*(?:\s+[A-Z][A-Za-z]*){0,3}(?:\s+(?:SARL|SAS|SA|Inc|GmbH|Ltd|Corp))\b'),
            re.compile(r'\b(?:SARL|SAS|SA)\s+[A-Za-z][A-Za-z\s]{2,20}\b'),
            re.compile(r'\b[A-Z]{2,}(?:\s+[A-Z]{2,})*\b'),  # Acronymes
            re.compile(r'\b(?:Université|École|Institut|Lycée)\s+[A-Za-z][A-Za-z\s]{2,30}\b', re.IGNORECASE),
        ]
        
        self.loc_patterns = [
            re.compile(r'\b(?:Paris|Lyon|Marseille|Toulouse|Nice|Nantes|Strasbourg|Montpellier|Bordeaux|Lille|Rennes|Reims|Le Havre|Saint-Étienne|Toulon|Grenoble|Dijon|Angers|Nîmes|Villeurbanne|Saint-Denis|Le Mans|Aix-en-Provence|Clermont-Ferrand|Brest|Tours|Amiens|Limoges|Annecy|Perpignan|Boulogne-Billancourt|Metz|Besançon|Orléans|Saint-Denis|Argenteuil|Rouen|Mulhouse|Caen|Nancy|Saint-Paul|Roubaix|Tourcoing|Nanterre|Vitry-sur-Seine|Avignon|Créteil|Dunkerque|Poitiers|Courbevoie|Versailles|Ivry|Ivry-sur-Seine)\b', re.IGNORECASE),
            re.compile(r'\b\d{5}\s+[A-Za-z][A-Za-z\s-]+\b'),  # Code postal + ville
            re.compile(r'\b[A-Z][a-z]+(?:-[A-Z][a-z]+)*(?:\s+sur\s+[A-Z][a-z]+)?\b'),  # Villes françaises
        ]
        
        self.date_patterns = [
            re.compile(r'\b\d{1,2}/\d{1,2}/\d{2,4}\b'),
            re.compile(r'\b\d{1,2}/\d{4}\b'),
            re.compile(r'\b(?:janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)\s+\d{4}\b', re.IGNORECASE),
            re.compile(r'\b\d{4}\b'),
            re.compile(r'\b\d{1,2}/\d{1,2}/\d{2}\b'),
        ]
    
    def tag_entities(self, lines: List[str]) -> List[List[Dict[str, Any]]]:
        """Tagge les entités dans les lignes."""
        results = []
        
        for line in lines:
            entities = []
            
            # Chercher les organisations
            for pattern in self.org_patterns:
                for match in pattern.finditer(line):
                    entities.append({
                        "entity_group": "ORG",
                        "word": match.group().strip(),
                        "start": match.start(),
                        "end": match.end(),
                        "score": 0.85
                    })
            
            # Chercher les lieux
            for pattern in self.loc_patterns:
                for match in pattern.finditer(line):
                    entities.append({
                        "entity_group": "LOC",
                        "word": match.group().strip(),
                        "start": match.start(),
                        "end": match.end(),
                        "score": 0.80
                    })
            
            # Chercher les dates
            for pattern in self.date_patterns:
                for match in pattern.finditer(line):
                    entities.append({
                        "entity_group": "DATE",
                        "word": match.group().strip(),
                        "start": match.start(),
                        "end": match.end(),
                        "score": 0.90
                    })
            
            # Supprimer les doublons et trier par position
            entities = self._remove_overlaps(entities)
            entities.sort(key=lambda x: x["start"])
            
            results.append(entities)
        
        return results
    
    def _remove_overlaps(self, entities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Supprime les entités qui se chevauchent, en gardant celle avec le meilleur score."""
        if not entities:
            return entities
        
        # Trier par position puis par score décroissant
        entities.sort(key=lambda x: (x["start"], -x["score"]))
        
        result = []
        for entity in entities:
            # Vérifier si cette entité chevauche avec une déjà acceptée
            overlap = False
            for accepted in result:
                if not (entity["end"] <= accepted["start"] or entity["start"] >= accepted["end"]):
                    # Chevauchement détecté
                    overlap = True
                    break
            
            if not overlap:
                result.append(entity)
        
        return result
