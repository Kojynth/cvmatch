"""Strict CV JSON schema used by Generator role."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class ContactInfo(BaseModel):
    full_name: str = ""
    email: str = ""
    phone: str = ""
    linkedin_url: str = ""
    location: str = ""


class SkillCategory(BaseModel):
    category: str = ""
    items: List[str] = Field(default_factory=list)


class ExperienceItem(BaseModel):
    title: str = ""
    company: str = ""
    start_date: str = ""
    end_date: str = ""
    location: str = ""
    summary: str = ""
    highlights: List[str] = Field(default_factory=list)


class EducationItem(BaseModel):
    school: str = ""
    degree: str = ""
    field_of_study: str = ""
    start_date: str = ""
    end_date: str = ""
    location: str = ""
    details: List[str] = Field(default_factory=list)


class ProjectItem(BaseModel):
    name: str = ""
    description: str = ""
    technologies: str = ""
    url: str = ""


class LanguageItem(BaseModel):
    language: str = ""
    level: str = ""


class CertificationItem(BaseModel):
    name: str = ""
    organization: str = ""
    date: str = ""
    url: str = ""


class RenderHints(BaseModel):
    notes: str = ""
    section_order: List[str] = Field(default_factory=list)
    emphasis: List[str] = Field(default_factory=list)
    tone: str = ""


class CVJSON(BaseModel):
    schema_version: str = Field(default="cv.v1")
    target_job_title: str
    target_company: str
    contact: ContactInfo
    summary: str
    skills: List[SkillCategory] = Field(default_factory=list)
    experience: List[ExperienceItem] = Field(default_factory=list)
    education: List[EducationItem] = Field(default_factory=list)
    projects: Optional[List[ProjectItem]] = None
    languages: Optional[List[LanguageItem]] = None
    certifications: Optional[List[CertificationItem]] = None
    ats_keywords: Optional[List[str]] = None
    render_hints: Optional[RenderHints] = None
