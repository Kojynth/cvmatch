"""Strict ProfileJSON schema aligned with Profile Details UI."""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class PersonalInfo(BaseModel):
    full_name: str = ""
    email: str = ""
    phone: str = ""
    linkedin_url: str = ""
    location: str = ""


class ExperienceItem(BaseModel):
    title: str = ""
    company: str = ""
    start_date: str = ""
    end_date: str = ""
    location: str = ""
    description: str = ""
    source: str = ""


class EducationItem(BaseModel):
    school: str = ""
    degree: str = ""
    field_of_study: str = ""
    start_date: str = ""
    end_date: str = ""
    grade: str = ""
    source: str = ""


class SkillItem(BaseModel):
    name: str = ""
    level: str = ""


class LanguageItem(BaseModel):
    language: str = ""
    proficiency: str = ""


class ProjectItem(BaseModel):
    name: str = ""
    url: str = ""
    technologies: str = ""
    description: str = ""


class CertificationItem(BaseModel):
    name: str = ""
    organization: str = ""
    date: str = ""
    url: str = ""


class PublicationItem(BaseModel):
    title: str = ""
    authors: str = ""
    journal: str = ""
    date: str = ""
    url: str = ""


class VolunteeringItem(BaseModel):
    organization: str = ""
    role: str = ""
    period: str = ""
    description: str = ""


class AwardItem(BaseModel):
    name: str = ""
    organization: str = ""
    date: str = ""
    description: str = ""


class ReferenceItem(BaseModel):
    name: str = ""
    title: str = ""
    company: str = ""
    email: str = ""
    phone: str = ""


class ProfileJSON(BaseModel):
    schema_version: str = Field(default="profile.v1")
    personal_info: PersonalInfo = Field(default_factory=PersonalInfo)
    experiences: List[ExperienceItem] = Field(default_factory=list)
    education: List[EducationItem] = Field(default_factory=list)
    skills: List[SkillItem] = Field(default_factory=list)
    soft_skills: List[SkillItem] = Field(default_factory=list)
    languages: List[LanguageItem] = Field(default_factory=list)
    projects: List[ProjectItem] = Field(default_factory=list)
    certifications: List[CertificationItem] = Field(default_factory=list)
    publications: List[PublicationItem] = Field(default_factory=list)
    volunteering: List[VolunteeringItem] = Field(default_factory=list)
    awards: List[AwardItem] = Field(default_factory=list)
    references: List[ReferenceItem] = Field(default_factory=list)
    interests: List[str] = Field(default_factory=list)
