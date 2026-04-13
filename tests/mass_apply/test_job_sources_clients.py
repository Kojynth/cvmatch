from __future__ import annotations

import json

from app.utils.job_sources.api_key.usajobs_client import USAJobsClient
from app.utils.job_sources.base import JobSearchQuery
from app.utils.job_sources.sitemap_html import wttj_client


class _Response:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def test_fetch_jobs_uses_explicit_remote_indicator_outside_salary_block(
    monkeypatch,
) -> None:
    payload = {
        "SearchResult": {
            "SearchResultItems": [
                {
                    "MatchedObjectDescriptor": {
                        "PositionTitle": "Cloud Engineer",
                        "OrganizationName": "USAJobs",
                        "PositionID": "abc",
                        "PositionURI": "https://example.gov/job/abc",
                        "ApplyURI": ["https://apply.example.gov/job/abc?ref=token"],
                        "PositionLocation": [{"LocationName": "Washington, DC"}],
                        "PositionRemuneration": [
                            {"MinimumRange": "100000", "MaximumRange": "120000"}
                        ],
                        "UserArea": {"Details": {"RemoteIndicator": True}},
                    }
                }
            ]
        }
    }

    monkeypatch.setattr(
        "app.utils.job_sources.api_key.usajobs_client.get_api_key",
        lambda key: "value@example.com" if key == "usajobs_user_agent" else "secret",
    )
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda req, timeout=15: _Response(payload),
    )

    offers = USAJobsClient().fetch_jobs(JobSearchQuery(keywords="cloud", max_results=5))

    assert len(offers) == 1
    assert offers[0].remote_type == "fully_remote"
    assert offers[0].salary_min == 100000
    assert offers[0].salary_max == 120000


def test_extract_apply_url_prefers_native_external_endpoint(monkeypatch) -> None:
    monkeypatch.setattr(
        wttj_client,
        "is_safe_apply_url",
        lambda url: url == "https://jobs.lever.co/acme/apply",
    )

    html = """
    <html>
      <body>
        <script>
          window.__DATA__ = {"applyUrl":"https://jobs.lever.co/acme/apply"};
        </script>
      </body>
    </html>
    """

    assert (
        wttj_client._extract_apply_url(
            html,
            "https://www.welcometothejungle.com/en/jobs/cloud-devops",
        )
        == "https://jobs.lever.co/acme/apply"
    )
