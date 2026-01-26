"""Post-processing utilities for extraction payloads."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional

from ..logging.safe_logger import get_safe_logger
from ..config import DEFAULT_PII_CONFIG

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


def redistribute_sections(payload: Dict[str, Any], inplace: bool = False) -> Dict[str, Any]:
    """Redistribute misclassified items across sections and strip routing metadata."""
    data = payload if inplace else deepcopy(payload)

    experiences = _extract_list(data, 'experiences')
    projects = _extract_list(data, 'projects')
    volunteering = _extract_list(data, 'volunteering')
    education = _extract_list(data, 'education')
    certifications = _extract_list(data, 'certifications')

    rerouted_counts = {
        'projects': 0,
        'volunteering': 0,
        'education': 0,
        'certifications': 0,
        'experience_from_projects': 0,
        'experience_from_volunteering': 0,
    }

    retained_experiences: List[Dict[str, Any]] = []

    # Forward reroutes (experience -> other sections)
    for exp in experiences:
        target = exp.get('_reroute_to')
        if not target:
            retained_experiences.append(_strip_routing_metadata(exp))
            continue

        clean_exp = _strip_routing_metadata(exp)
        if target == 'projects':
            projects.append(_experience_to_project(clean_exp))
            rerouted_counts['projects'] += 1
        elif target == 'volunteering':
            volunteering.append(_experience_to_volunteering(clean_exp))
            rerouted_counts['volunteering'] += 1
        elif target == 'education':
            education.append(_experience_to_education(clean_exp))
            rerouted_counts['education'] += 1
        elif target == 'certifications':
            certifications.append(_experience_to_certification(clean_exp))
            rerouted_counts['certifications'] += 1
        else:
            retained_experiences.append(clean_exp)

    # Reverse reroutes (projects/volunteering -> experience)
    retained_projects: List[Dict[str, Any]] = []
    for item in projects:
        override = _routing_override_target(item)
        if override == 'experience':
            retained_experiences.append(_strip_routing_metadata(_project_to_experience(item)))
            rerouted_counts['experience_from_projects'] += 1
        else:
            retained_projects.append(_strip_routing_metadata(item))
    projects[:] = retained_projects

    retained_volunteering: List[Dict[str, Any]] = []
    for item in volunteering:
        override = _routing_override_target(item)
        if override == 'experience':
            retained_experiences.append(_strip_routing_metadata(_volunteering_to_experience(item)))
            rerouted_counts['experience_from_volunteering'] += 1
        else:
            retained_volunteering.append(_strip_routing_metadata(item))
    volunteering[:] = retained_volunteering

    data['experiences'] = retained_experiences
    data['projects'] = projects
    data['volunteering'] = volunteering
    data['education'] = [_strip_routing_metadata(item) for item in education]
    data['certifications'] = [_strip_routing_metadata(item) for item in certifications]

    if any(rerouted_counts.values()):
        summary = ' '.join(f"{key}={value}" for key, value in rerouted_counts.items() if value)
        logger.info(f"EXTRACTION_POST: redistribution_summary | {summary}")

    _log_residual_flags(data)
    return data


def _extract_list(data: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    value = data.get(key)
    if isinstance(value, list):
        return value
    if value is None:
        value = []
        data[key] = value
        return value
    if isinstance(value, dict):
        data[key] = [value]
        return data[key]
    data[key] = []
    return data[key]


def _strip_routing_metadata(item: Dict[str, Any]) -> Dict[str, Any]:
    item.pop('_reroute_to', None)
    item.pop('_reroute_reason', None)
    item.pop('_routing_override', None)
    return item


def _routing_override_target(item: Dict[str, Any]) -> Optional[str]:
    override = item.get('_routing_override')
    if isinstance(override, dict):
        return override.get('target_section')
    return None


def _experience_to_project(exp: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'name': exp.get('project_name') or exp.get('title') or exp.get('company') or 'Projet sans nom',
        'role': exp.get('title'),
        'description': exp.get('description'),
        'technologies': exp.get('technologies') or [],
        'achievements': exp.get('achievements') or [],
        'client': exp.get('company'),
        'start_date': exp.get('start_date'),
        'end_date': exp.get('end_date'),
        'location': exp.get('location'),
        'source': exp.get('source') or 'experience_reroute',
    }


def _experience_to_volunteering(exp: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'role': exp.get('title') or 'Bénévolat',
        'organization': exp.get('company'),
        'description': exp.get('description'),
        'start_date': exp.get('start_date'),
        'end_date': exp.get('end_date'),
        'location': exp.get('location'),
        'source': exp.get('source') or 'experience_reroute',
    }


def _experience_to_education(exp: Dict[str, Any]) -> Dict[str, Any]:
    degree = exp.get('title') or 'Formation à définir'
    institution = exp.get('company') or 'Institution à définir'
    year = exp.get('period') or _build_period(exp)
    return {
        'degree': degree,
        'institution': institution,
        'location': exp.get('location'),
        'description': exp.get('description'),
        'start_year': _extract_year(exp.get('start_date')),
        'end_year': _extract_year(exp.get('end_date')),
        'year': year,
        'confidence': exp.get('confidence', 'medium'),
        'source': exp.get('source') or 'experience_reroute',
    }


def _experience_to_certification(exp: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'name': exp.get('title') or exp.get('description') or 'Certification',
        'issuer': exp.get('company'),
        'date': exp.get('end_date') or exp.get('start_date'),
        'source': exp.get('source') or 'experience_reroute',
    }


def _project_to_experience(project: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'title': project.get('role') or project.get('name'),
        'company': project.get('client') or project.get('organization') or project.get('name'),
        'description': project.get('description'),
        'start_date': project.get('start_date'),
        'end_date': project.get('end_date'),
        'achievements': project.get('achievements'),
        'technologies': project.get('technologies'),
        'location': project.get('location'),
        'source': project.get('source') or 'project_reverse_reroute',
        'confidence': project.get('confidence', 'medium'),
    }


def _volunteering_to_experience(vol: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'title': vol.get('role') or 'Bénévolat',
        'company': vol.get('organization'),
        'description': vol.get('description'),
        'start_date': vol.get('start_date'),
        'end_date': vol.get('end_date'),
        'location': vol.get('location'),
        'source': vol.get('source') or 'volunteering_reverse_reroute',
        'confidence': vol.get('confidence', 'medium'),
    }


def _build_period(exp: Dict[str, Any]) -> Optional[str]:
    start = exp.get('start_date')
    end = exp.get('end_date')
    if not start and not end:
        return None
    start = start or ''
    end = end or 'Présent'
    return f"{start} - {end}".strip()


def _extract_year(value: Any) -> Optional[int]:
    if not value:
        return None
    text = str(value)
    for token in text.replace('/', ' ').replace('-', ' ').split():
        if token.isdigit() and len(token) == 4:
            try:
                return int(token)
            except ValueError:
                continue
    return None


def _log_residual_flags(data: Dict[str, Any]) -> None:
    flagged_sections = []
    for section_name, items in data.items():
        if not isinstance(items, list):
            continue
        if any(isinstance(item, dict) and (item.get('_reroute_to') or item.get('_routing_override')) for item in items):
            flagged_sections.append(section_name)
    if flagged_sections:
        logger.warning(f"EXTRACTION_POST: residual_routing_flags | sections={flagged_sections}")
