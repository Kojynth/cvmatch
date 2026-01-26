from .mapping_shared import (is_valid_date_format as _is_valid_date_format, is_valid_year as _is_valid_year, normalize_confidence as _normalize_confidence)
"""
Enhanced extraction mapper methods to avoid placeholder fallbacks.
These methods replace the originals to provide better quality control.
"""

import re
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


def enhance_extraction_mapping_with_validation(original_mapper_function):
    """
    Decorator to enhance existing mapper functions with validation.
    Patches the apply_smart_mapping function to avoid placeholders.
    """
    def apply_smart_mapping_no_placeholders(data: dict) -> dict:
        """Enhanced version of apply_smart_mapping that avoids placeholder fallbacks."""
        logger.info("MAP: start_enhanced_no_placeholders")
        
        # Import the original function's utilities
        from . import extraction_mapper
        _as_list = extraction_mapper._as_list
        _dedup_list_preserve_one = extraction_mapper._dedup_list_preserve_one
        _dedup_languages = extraction_mapper._dedup_languages
        _apply_post_mapping_qa = extraction_mapper._apply_post_mapping_qa
        
        out = {}
        
        # Personal info (passthrough)
        personal_info = data.get("personal_info") if isinstance(data.get("personal_info"), dict) else {}
        out["personal_info"] = personal_info
        logger.info(f"MAP: personal_info | fields={len(personal_info)}")

        list_sections = ["experiences","education","skills","soft_skills","languages",
                         "projects","certifications","publications","volunteering","interests","awards","references"]
        norm = {k: _as_list(data.get(k)) for k in list_sections}
        
        # Log input data counts
        input_counts = {k: len(norm[k]) for k in list_sections}
        logger.info(f"MAP: input_counts | " + " ".join(f"{k}={v}" for k, v in input_counts.items() if v > 0))

        # === NO-PLACEHOLDER MAPPING POUR EXPERIENCES ===
        raw_experiences = norm["experiences"]
        if raw_experiences:
            logger.info(f"MAP: experiences_no_placeholders_start | {len(raw_experiences)} items")
            
            mapped_experiences = []
            mapping_errors = 0
            rejected_count = 0
            
            for i, exp_data in enumerate(raw_experiences):
                try:
                    if isinstance(exp_data, dict):
                        mapped_exp = map_experience_data_no_placeholders(exp_data)
                        if mapped_exp:
                            mapped_experiences.append(mapped_exp)
                            logger.debug(f"  ✅ Exp {i+1}: {mapped_exp.get('title', 'No title')}")
                        else:
                            rejected_count += 1
                            logger.debug(f"  ❌ Exp {i+1}: Rejected - insufficient meaningful data")
                    else:
                        logger.debug(f"  ⚠️ Exp {i+1}: Non-dict format, skipping")
                        mapping_errors += 1
                except Exception as e:
                    logger.error(f"  ❌ Exp {i+1}: Mapping error - {e}")
                    mapping_errors += 1
            
            out["experiences"] = mapped_experiences
            logger.info(f"MAP: experiences_no_placeholders_done | {len(mapped_experiences)} accepted, {rejected_count} rejected, {mapping_errors} errors")
        else:
            out["experiences"] = []
        
        # === NO-PLACEHOLDER MAPPING POUR EDUCATION ===
        raw_education = norm["education"]
        if raw_education:
            logger.info(f"MAP: education_no_placeholders_start | {len(raw_education)} items")
            
            mapped_education = []
            mapping_errors = 0
            rejected_count = 0
            
            for i, edu_data in enumerate(raw_education):
                try:
                    if isinstance(edu_data, dict):
                        mapped_edu = map_education_data_no_placeholders(edu_data)
                        if mapped_edu:
                            mapped_education.append(mapped_edu)
                            logger.debug(f"  ✅ Edu {i+1}: {mapped_edu.get('degree', 'No degree')}")
                        else:
                            rejected_count += 1
                            logger.debug(f"  ❌ Edu {i+1}: Rejected - insufficient meaningful data")
                    else:
                        logger.debug(f"  ⚠️ Edu {i+1}: Non-dict format, skipping")
                        mapping_errors += 1
                except Exception as e:
                    logger.error(f"  ❌ Edu {i+1}: Mapping error - {e}")
                    mapping_errors += 1
            
            out["education"] = mapped_education
            logger.info(f"MAP: education_no_placeholders_done | {len(mapped_education)} accepted, {rejected_count} rejected, {mapping_errors} errors")
        else:
            out["education"] = []

        # === OTHER SECTIONS (using original logic) ===
        # Skills with deduplication
        raw_skills = norm["skills"]
        extracted_soft_skills = []
        cleaned_raw_skills = []
        for item in raw_skills or []:
            if isinstance(item, dict) and 'category' in item:
                cat = str(item.get('category', '')).strip().lower()
                if 'soft' in cat:
                    nested = item.get('skills') or []
                    for sk in nested:
                        if isinstance(sk, dict):
                            name = str(sk.get('name', '')).strip()
                            if name:
                                lvl = sk.get('level')
                                extracted_soft_skills.append({'name': name, 'level': lvl} if lvl is not None else {'name': name})
                    continue
            cleaned_raw_skills.append(item)
        raw_skills = cleaned_raw_skills
        
        def skills_norm_fn(s):
            if isinstance(s, dict):
                if 'category' in s:
                    return str(s.get("category", "")).strip().lower()
                else:
                    return str(s.get("name", "")).strip().lower()
            return str(s).strip().lower()
        
        out["skills"] = _dedup_list_preserve_one(raw_skills, norm_fn=skills_norm_fn)
        if len(raw_skills) != len(out["skills"]):
            logger.info(f"MAP: skills_dedup | {len(raw_skills)} → {len(out['skills'])} (removed {len(raw_skills) - len(out['skills'])} duplicates)")
        
        # Soft skills with deduplication
        raw_soft_skills = (norm["soft_skills"] or []) + extracted_soft_skills
        out["soft_skills"] = _dedup_list_preserve_one(raw_soft_skills, norm_fn=lambda s: str(s.get("name", "") if isinstance(s, dict) else s).strip().lower())
        
        # Languages with deduplication and canonization
        raw_languages = norm["languages"]
        out["languages"] = _dedup_languages(raw_languages)
        
        # Other sections (passthrough with filtering but no placeholders)
        for k in ["projects","certifications","publications","volunteering","interests","awards","references"]:
            raw_items = norm[k]
            # Enhanced filtering - reject items with placeholder content
            filtered_items = []
            for x in raw_items:
                if x and _item_has_meaningful_content(x):
                    filtered_items.append(x)

            # Section-specific post-filtering (from original)
            if k == "projects" and filtered_items:
                candidate_name = (personal_info or {}).get('full_name') if isinstance(personal_info, dict) else None
                name_norm = (candidate_name or '').strip().lower()
                platform_blacklist = {"linkedin", "linkedin.com", "indeed", "canva", "europass", "github", "gitlab",
                                      "microsoft", "azure", "aws", "google", "google cloud"}
                def keep_project(p):
                    try:
                        title = (p.get('name') or p.get('title') or '').strip()
                        tnorm = title.lower()
                        if name_norm and tnorm == name_norm:
                            return False
                        if tnorm in platform_blacklist:
                            return False
                        url = (p.get('url') or '').strip()
                        techs = p.get('tech_stack') or p.get('technologies') or []
                        desc = (p.get('description') or '').strip()
                        if url:
                            return True
                        if isinstance(techs, list) and len(techs) > 0:
                            return True
                if len(desc) >= 20 and re.search(r"(d[eé]velopp|con[cs]u|r[eé]alis|impl[eé]ment|prototyp|men[eé]|pilot[eé]|build|develop|design|implement|prototype)", desc, re.IGNORECASE):
                            return True
                        return False
                    except Exception:
                        return False
                kept = [p for p in filtered_items if isinstance(p, dict) and keep_project(p)]
                dropped = len(filtered_items) - len(kept)
                filtered_items = kept
                logger.info(f"MAP: projects_post_filter | kept={len(filtered_items)} dropped={dropped}")

            if k == "certifications" and filtered_items:
                allow_always = {"pix"}
                vendor_blocklist = {"microsoft","office","excel","word","azure","aws","amazon web services","google","google cloud","gcp","cisco","itil"}
                trigger_terms = {"certification","certifié","certifie","attestation","credential","identifiant","id","score","issued"}
                def keep_cert(c):
                    try:
                        name = str(c.get('name') if isinstance(c, dict) else c).strip().lower()
                        if not name:
                            return False
                        if name in allow_always:
                            return True
                        if name in vendor_blocklist:
                            text_blob = name
                            if isinstance(c, dict):
                                text_blob += " " + str(c.get('description') or '')
                            return any(t in text_blob for t in trigger_terms)
                        return True
                    except Exception:
                        return False
                kept = [c for c in filtered_items if keep_cert(c)]
                dropped = len(filtered_items) - len(kept)
                filtered_items = kept
                logger.info(f"MAP: certifications_post_filter | kept={len(filtered_items)} dropped={dropped}")
            
            out[k] = filtered_items
            
            if len(raw_items) != len(filtered_items):
                logger.info(f"MAP: {k}_filter | {len(raw_items)} → {len(filtered_items)} (removed {len(raw_items) - len(filtered_items)} placeholder/empty items)")
        
        # === QA POST-MAPPING (from original) ===
        logger.info("MAP: starting_post_mapping_qa")
        out = _apply_post_mapping_qa(out, data)

        # Merge education items (from original)
        def _norm_school(s: str) -> str:
            return re.sub(r"\s+", " ", (s or '').strip().lower())
        merged = []
        by_key = {}
        for edu in out.get('education', []) or []:
            key = (_norm_school(edu.get('institution')), edu.get('degree') or '')
            if key not in by_key:
                by_key[key] = edu.copy()
                merged.append(by_key[key])
            else:
                existing = by_key[key]
                s1, e1 = existing.get('start_date') or '', existing.get('end_date') or ''
                s2, e2 = edu.get('start_date') or '', edu.get('end_date') or ''
                existing['start_date'] = min([d for d in [s1, s2] if d], default=s1 or s2)
                existing['end_date'] = max([d for d in [e1, e2] if d], default=e1 or e2)
                desc1 = existing.get('description') or []
                desc2 = edu.get('description') or []
                existing['description'] = _dedup_list_preserve_one(desc1 + desc2, norm_fn=lambda x: str(x).strip().lower())
        if merged:
            out['education'] = merged
        
        # Final summary
        output_counts = {k: len(out.get(k, [])) for k in list_sections}
        total_items = sum(output_counts.values()) + (1 if personal_info else 0)
        logger.info(f"MAP: output_summary_enhanced | total_items={total_items} " + " ".join(f"{k}={v}" for k, v in output_counts.items() if v > 0))

        logger.info("MAP: done_enhanced_no_placeholders")
        return out
    
    return apply_smart_mapping_no_placeholders


def _item_has_meaningful_content(item: Any) -> bool:
    """Vérifie si un item a du contenu significatif."""
    if not item:
        return False
    
    if isinstance(item, dict):
        # Vérifier les champs clés pour du contenu significatif
        key_fields = ['name', 'title', 'description', 'company', 'institution', 'degree']
        for field in key_fields:
            value = item.get(field)
            if value and is_meaningful_content(value):
                return True
        return False
    
    elif isinstance(item, str):
        return is_meaningful_content(item)
    
    return True  # Autres types acceptés par défaut


def is_meaningful_content(value: Any, min_length: int = 3) -> bool:
    """Vérifie si le contenu est significatif et non un placeholder."""
    if not value:
        return False
    
    text = str(value).strip().lower()
    
    # Vérifier la longueur minimale
    if len(text) < min_length:
        return False
    
    # Vérifier les mots-clés de placeholder
    placeholder_keywords = ["définir", "specify", "unknown", "n/a", "tbd", "todo", "sans titre", "non spécifié"]
    if any(keyword in text for keyword in placeholder_keywords):
        return False
    
    # Vérifier si c'est juste de la ponctuation ou des espaces
    if not any(c.isalnum() for c in text):
        return False
    
    return True


def map_experience_data_no_placeholders(exp_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Mapping robuste pour les expériences SANS placeholders.
    Retourne None si pas assez d'informations significatives.
    """
    if not isinstance(exp_data, dict):
        return None
    
    logger.debug(f"🗂️ Mapping expérience sans placeholders: {exp_data.get('title', 'Sans titre')}")
    
    mapped = {}
    
    # === CHAMPS OBLIGATOIRES - VALIDATION STRICTE ===
    # Title (obligatoire) - doit être significatif
    title_candidates = [
        exp_data.get('title'),
        exp_data.get('position'), 
        exp_data.get('job_title'),
        exp_data.get('role')
    ]
    
    title = None
    for candidate in title_candidates:
        if is_meaningful_content(candidate, min_length=4):
            title = str(candidate).strip()
            break
    
    if not title:
        logger.debug(f"  ❌ Rejecting experience: no meaningful title found")
        return None
    
    mapped['title'] = title
    
    # === CHAMPS OPTIONNELS - SEULEMENT SI SIGNIFICATIFS ===
    # Company
    company_candidates = [
        exp_data.get('company'),
        exp_data.get('employer'),
        exp_data.get('organization'),
        exp_data.get('enterprise')
    ]
    
    for candidate in company_candidates:
        if is_meaningful_content(candidate, min_length=2):
            mapped['company'] = str(candidate).strip()
            break
    
    # Location
    location_candidates = [
        exp_data.get('location'),
        exp_data.get('city'), 
        exp_data.get('place'),
        exp_data.get('address')
    ]
    
    for candidate in location_candidates:
        if is_meaningful_content(candidate, min_length=2):
            mapped['location'] = str(candidate).strip()
            break
    
    # === DATES ===
    start_date = (exp_data.get('start_date') or 
                  exp_data.get('date_start') or 
                  exp_data.get('begin_date') or 
                  exp_data.get('from_date'))
    if start_date and is_meaningful_content(start_date, min_length=4):
        mapped['start_date'] = _normalize_date_safe(start_date)
    
    end_date = (exp_data.get('end_date') or 
                exp_data.get('date_end') or 
                exp_data.get('finish_date') or 
                exp_data.get('to_date'))
    if end_date and is_meaningful_content(end_date, min_length=4):
        mapped['end_date'] = _normalize_date_safe(end_date)
    
    # === CONTENU DESCRIPTIF ===
    description = (exp_data.get('description') or 
                   exp_data.get('summary') or 
                   exp_data.get('details') or 
                   exp_data.get('responsibilities'))
    if description and is_meaningful_content(description, min_length=10):
        mapped['description'] = str(description).strip()
    
    # === MÉTADONNÉES TECHNIQUES ===
    for meta_field in ['source_lines', 'extraction_method', 'confidence', 'span_start', 'span_end', 'flags', 'raw_text']:
        if meta_field in exp_data and exp_data[meta_field] is not None:
            mapped[meta_field] = exp_data[meta_field]
    
    # Vérification finale - au moins company OU location OU description pour accepter
    has_context = any(field in mapped for field in ['company', 'location', 'description'])
    
    if not has_context:
        logger.debug(f"  ❌ Rejecting experience '{title}': insufficient context information")
        return None
    
    logger.debug(f"✅ Experience accepted: '{mapped.get('title')}' @ {mapped.get('company', 'N/A')}")
    return mapped


def map_education_data_no_placeholders(edu_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Mapping robuste pour l'éducation SANS placeholders.
    Retourne None si pas assez d'informations significatives.
    """
    if not isinstance(edu_data, dict):
        return None
    
    logger.debug(f"🎓 Mapping éducation sans placeholders: {edu_data.get('degree', 'Sans diplôme')}")
    
    mapped = {}
    
    # === CHAMPS OBLIGATOIRES - VALIDATION STRICTE ===
    # Degree (obligatoire) - doit être significatif
    degree_candidates = [
        edu_data.get('degree'),
        edu_data.get('diploma'),
        edu_data.get('qualification'),
        edu_data.get('title')
    ]
    
    degree = None
    for candidate in degree_candidates:
        if is_meaningful_content(candidate, min_length=4):
            degree = str(candidate).strip()
            break
    
    if not degree:
        logger.debug(f"  ❌ Rejecting education: no meaningful degree found")
        return None
    
    mapped['degree'] = degree
    
    # Institution (obligatoire) - doit être significative
    institution_candidates = [
        edu_data.get('institution'),
        edu_data.get('school'),
        edu_data.get('university'),
        edu_data.get('college'),
        edu_data.get('establishment')
    ]
    
    institution = None
    for candidate in institution_candidates:
        if is_meaningful_content(candidate, min_length=3):
            institution = str(candidate).strip()
            break
    
    if not institution:
        logger.debug(f"  ❌ Rejecting education: no meaningful institution found")
        return None
    
    mapped['institution'] = institution
    
    # === CHAMPS OPTIONNELS ===
    # Field of study
    field_candidates = [
        edu_data.get('field_of_study'),
        edu_data.get('major'),
        edu_data.get('specialization'),
        edu_data.get('domain')
    ]
    
    for candidate in field_candidates:
        if is_meaningful_content(candidate, min_length=3):
            mapped['field_of_study'] = str(candidate).strip()
            break
    
    # Location
    location_candidates = [
        edu_data.get('location'),
        edu_data.get('city'),
        edu_data.get('place')
    ]
    
    for candidate in location_candidates:
        if is_meaningful_content(candidate, min_length=2):
            mapped['location'] = str(candidate).strip()
            break
    
    # === ANNÉES ===
    start_year = edu_data.get('start_year') or edu_data.get('year_start')
    if start_year and _is_valid_year(start_year):
        mapped['start_year'] = int(start_year)
    
    end_year = edu_data.get('end_year') or edu_data.get('year_end')
    if end_year and _is_valid_year(end_year):
        mapped['end_year'] = int(end_year)
    
    # Year (format texte)
    year = edu_data.get('year') or edu_data.get('period')
    if year and is_meaningful_content(year, min_length=4):
        mapped['year'] = str(year).strip()
    
    # === MÉTADONNÉES ===
    confidence = edu_data.get('confidence') or 'medium'
    mapped['confidence'] = _normalize_confidence(confidence)
    
    # Description
    description = (edu_data.get('description') or 
                   edu_data.get('summary') or 
                   edu_data.get('details'))
    if description and is_meaningful_content(description, min_length=10):
        mapped['description'] = str(description).strip()
    
    # Métadonnées techniques
    for meta_field in ['source_lines', 'extraction_method', 'raw_text']:
        if meta_field in edu_data and edu_data[meta_field] is not None:
            mapped[meta_field] = edu_data[meta_field]
    
    logger.debug(f"✅ Education accepted: '{mapped.get('degree')}' @ {mapped.get('institution')}")
    return mapped


def _normalize_date_safe(date_value: Any) -> Optional[str]:
    """Normalise une date de manière sûre sans placeholder."""
    if not date_value:
        return None
    
    date_str = str(date_value).strip()
    
    # Cas spéciaux : "present", "actuel", etc.
    present_words = ['present', 'présent', 'actuel', 'current', 'ongoing', 'now', 'en cours']
    if any(word in date_str.lower() for word in present_words):
        return 'present'
    
    # Nettoyage de base
    date_str = re.sub(r'[^\d/\-\s]', '', date_str)
    date_str = date_str.strip()
    
    if not date_str or len(date_str) < 4:
        return None
    
    # Formats supportés avec regex patterns
    date_patterns = [
        (r'^\d{4}$', lambda m: m.group(0)),  # YYYY
        (r'^(\d{1,2})/(\d{4})$', lambda m: f"{int(m.group(1)):02d}/{m.group(2)}"),  # M/YYYY -> MM/YYYY
        (r'^(\d{1,2})/(\d{1,2})/(\d{4})$', lambda m: f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}"),  # D/M/YYYY -> DD/MM/YYYY
        (r'^(\d{4})-(\d{1,2})$', lambda m: f"{int(m.group(2)):02d}/{m.group(1)}"),  # YYYY-M -> MM/YYYY
        (r'^(\d{4})-(\d{1,2})-(\d{1,2})$', lambda m: f"{int(m.group(3)):02d}/{int(m.group(2)):02d}/{m.group(1)}")  # YYYY-M-D -> DD/MM/YYYY
    ]
    
    for pattern, formatter in date_patterns:
        match = re.match(pattern, date_str)
        if match:
            try:
                formatted_date = formatter(match)
                # Validation basique des valeurs
                if _is_valid_date_format(formatted_date):
                    return formatted_date
            except (ValueError, IndexError):
                continue
    
    # Si aucun format reconnu mais semble être une date valide, retourner tel quel
    if re.search(r'\d{4}', date_str):  # Contient au moins une année
        return date_str
    
    return None


    conf_str = str(confidence).lower()
    
    if conf_str in ['high', 'élevé', 'élevée', 'fort', 'forte', '3']:
        return 'high'
    elif conf_str in ['low', 'faible', 'bas', 'basse', '1']:
        return 'low'
    elif conf_str in ['unknown', 'inconnu', 'incertain', '0']:
        return 'unknown'
    else:
        return 'medium'
