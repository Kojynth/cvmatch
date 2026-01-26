"""Strict Offer Keywords JSON schema."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field


class OfferKeywordsJSON(BaseModel):
    schema_version: str = Field(default="offer_keywords.v1")
    language: str = ""
    job_title: str = ""
    company: str = ""
    seniority: str = ""
    keywords: List[str] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    tools: List[str] = Field(default_factory=list)
    soft_skills: List[str] = Field(default_factory=list)
    responsibilities: List[str] = Field(default_factory=list)
    education: List[str] = Field(default_factory=list)
    certifications: List[str] = Field(default_factory=list)
