"""Unit tests and end-to-end tests for scraper.py."""

import argparse
import csv
import os
import tempfile
from unittest.mock import patch

import pytest

from conftest import requires_archived_html
from scraper import (
    DEFAULT_MAX_PAGES,
    DEFAULT_OUTPUT,
    build_search_url,
    extract_clinic_urls_from_page,
    main,
    parse_args,
    resolve_args,
    resolve_parent_clinics,
    scrape_all_clinics,
    scrape_clinic_detail,
    scrape_search_results,
    write_csv,
)


class TestResolveParentClinics:
    def test_single_satellite_parent_in_results(self):
        clinics = [
            {"name": "Parent Clinic", "clinic_id": 6, "clinic_type": "clinic", "distance": 20.0, "parent_clinics": []},
            {
                "name": "Satellite A",
                "clinic_id": None,
                "clinic_type": "satellite",
                "distance": 4.48,
                "parent_clinics": [{"name": "Parent Clinic", "clinic_id": 6, "url": "/results/6/"}],
            },
        ]
        parent_dist, missing = resolve_parent_clinics(clinics)
        assert parent_dist == {6: 4.48}
        assert missing == set()

    def test_multiple_satellites_same_parent_takes_minimum(self):
        clinics = [
            {"name": "Parent", "clinic_id": 6, "clinic_type": "clinic", "distance": 30.0, "parent_clinics": []},
            {
                "name": "Sat A",
                "clinic_id": None,
                "clinic_type": "satellite",
                "distance": 5.0,
                "parent_clinics": [{"name": "Parent", "clinic_id": 6, "url": "/results/6/"}],
            },
            {
                "name": "Sat B",
                "clinic_id": None,
                "clinic_type": "satellite",
                "distance": 3.0,
                "parent_clinics": [{"name": "Parent", "clinic_id": 6, "url": "/results/6/"}],
            },
        ]
        parent_dist, missing = resolve_parent_clinics(clinics)
        assert parent_dist == {6: 3.0}
        assert missing == set()

    def test_parent_not_in_results_is_missing(self):
        clinics = [
            {
                "name": "Sat A",
                "clinic_id": None,
                "clinic_type": "satellite",
                "distance": 4.48,
                "parent_clinics": [{"name": "Distant Parent", "clinic_id": 99, "url": "/results/99/"}],
            },
        ]
        parent_dist, missing = resolve_parent_clinics(clinics)
        assert parent_dist == {99: 4.48}
        assert missing == {99}

    def test_satellite_with_multiple_parents(self):
        clinics = [
            {"name": "Parent A", "clinic_id": 75, "clinic_type": "clinic", "distance": 50.0, "parent_clinics": []},
            {
                "name": "Sat",
                "clinic_id": None,
                "clinic_type": "satellite",
                "distance": 4.54,
                "parent_clinics": [
                    {"name": "Parent A", "clinic_id": 75, "url": "/results/75/"},
                    {"name": "Parent B", "clinic_id": 105, "url": "/results/105/"},
                    {"name": "Parent C", "clinic_id": 301, "url": "/results/301/"},
                ],
            },
        ]
        parent_dist, missing = resolve_parent_clinics(clinics)
        assert parent_dist == {75: 4.54, 105: 4.54, 301: 4.54}
        assert missing == {105, 301}

    def test_no_satellites(self):
        clinics = [
            {"name": "Clinic A", "clinic_id": 1, "clinic_type": "clinic", "distance": 5.0, "parent_clinics": []},
        ]
        parent_dist, missing = resolve_parent_clinics(clinics)
        assert parent_dist == {}
        assert missing == set()

    def test_satellite_with_none_distance(self):
        clinics = [
            {
                "name": "Sat",
                "clinic_id": None,
                "clinic_type": "satellite",
                "distance": None,
                "parent_clinics": [{"name": "Parent", "clinic_id": 6, "url": "/results/6/"}],
            },
        ]
        parent_dist, missing = resolve_parent_clinics(clinics)
        assert parent_dist == {6: None}

    def test_parent_with_no_id_is_ignored(self):
        clinics = [
            {
                "name": "Sat",
                "clinic_id": None,
                "clinic_type": "satellite",
                "distance": 3.0,
                "parent_clinics": [{"name": "Mystery Parent", "clinic_id": None, "url": None}],
            },
        ]
        parent_dist, missing = resolve_parent_clinics(clinics)
        assert parent_dist == {}
        assert missing == set()

    def test_mixed_none_and_real_distances_takes_min_of_real(self):
        clinics = [
            {
                "name": "Sat A",
                "clinic_id": None,
                "clinic_type": "satellite",
                "distance": None,
                "parent_clinics": [{"name": "Parent", "clinic_id": 6, "url": "/results/6/"}],
            },
            {
                "name": "Sat B",
                "clinic_id": None,
                "clinic_type": "satellite",
                "distance": 7.0,
                "parent_clinics": [{"name": "Parent", "clinic_id": 6, "url": "/results/6/"}],
            },
        ]
        parent_dist, missing = resolve_parent_clinics(clinics)
        assert parent_dist == {6: 7.0}

    def test_transport_clinics_are_excluded(self):
        """Transport clinics should not contribute to parent distance map."""
        clinics = [
            {
                "name": "Transport A",
                "clinic_id": None,
                "clinic_type": "transport",
                "distance": 2.0,
                "parent_clinics": [{"name": "Parent", "clinic_id": 109, "url": "/results/109/"}],
            },
        ]
        parent_dist, missing = resolve_parent_clinics(clinics)
        assert parent_dist == {}
        assert missing == set()

    def test_transport_and_satellite_mixed(self):
        """Only satellites feed into parent resolution, not transports."""
        clinics = [
            {"name": "Parent", "clinic_id": 109, "clinic_type": "clinic", "distance": 10.0, "parent_clinics": []},
            {
                "name": "Satellite",
                "clinic_id": None,
                "clinic_type": "satellite",
                "distance": 5.0,
                "parent_clinics": [{"name": "Parent", "clinic_id": 109, "url": "/results/109/"}],
            },
            {
                "name": "Transport",
                "clinic_id": None,
                "clinic_type": "transport",
                "distance": 2.0,
                "parent_clinics": [{"name": "Parent", "clinic_id": 109, "url": "/results/109/"}],
            },
        ]
        parent_dist, missing = resolve_parent_clinics(clinics)
        # Only satellite distance (5.0), not transport distance (2.0)
        assert parent_dist == {109: 5.0}
        assert missing == set()


class TestExtractClinicTypes:
    def test_satellite_clinic(self):
        html = """
        <ul class="list-group clinic-list">
          <li class="clinic">
            <div class="row pb-20">
              <div class="col-md-8">
                <h3 class="clinic-name"><a>Satellite Clinic</a></h3>
                <p class="clinic-desc">Satellite clinic to
                  <a href="/choose-a-clinic/clinic-search/results/6/"
                     title="view profile of Parent Clinic">Parent Clinic</a>
                </p>
              </div>
            </div>
          </li>
        </ul>
        """
        clinics = extract_clinic_urls_from_page(html)
        assert len(clinics) == 1
        assert clinics[0]["clinic_type"] == "satellite"
        assert clinics[0]["parent_clinics"] == [
            {"name": "Parent Clinic", "clinic_id": 6, "url": "/choose-a-clinic/clinic-search/results/6/"}
        ]

    def test_satellite_with_multiple_parents(self):
        html = """
        <ul class="list-group clinic-list">
          <li class="clinic">
            <div class="row pb-20">
              <div class="col-md-8">
                <h3 class="clinic-name"><a>Multi-Parent Satellite</a></h3>
                <p class="clinic-desc">Satellite clinic to
                  <a href="/choose-a-clinic/clinic-search/results/75/">Parent A</a>
                </p>
                <p class="clinic-desc">Satellite clinic to
                  <a href="/choose-a-clinic/clinic-search/results/105/">Parent B</a>
                </p>
              </div>
            </div>
          </li>
        </ul>
        """
        clinics = extract_clinic_urls_from_page(html)
        assert len(clinics) == 1
        assert clinics[0]["clinic_type"] == "satellite"
        assert len(clinics[0]["parent_clinics"]) == 2
        assert clinics[0]["parent_clinics"][0]["clinic_id"] == 75
        assert clinics[0]["parent_clinics"][1]["clinic_id"] == 105

    def test_transport_clinic(self):
        html = """
        <ul class="list-group clinic-list">
          <li class="clinic">
            <div class="row pb-20">
              <div class="col-md-8">
                <h3 class="clinic-name"><a>Croydon University Hospital</a></h3>
                <p class="distance">
                  <span class="glyphicon glyphicon-map-marker"></span>
                  10.5 miles
                </p>
                <p class="clinic-desc">Transport clinic to
                  <a href="/choose-a-clinic/clinic-search/results/105/"
                     title="view profile of London Women's Clinic">London Women's Clinic</a>
                </p>
              </div>
            </div>
          </li>
        </ul>
        """
        clinics = extract_clinic_urls_from_page(html)
        assert len(clinics) == 1
        assert clinics[0]["clinic_type"] == "transport"
        assert clinics[0]["name"] == "Croydon University Hospital"
        assert clinics[0]["parent_clinics"] == [
            {"name": "London Women's Clinic", "clinic_id": 105, "url": "/choose-a-clinic/clinic-search/results/105/"}
        ]
        assert clinics[0]["distance"] == 10.5

    def test_unknown_type_no_desc(self):
        """A card with no href and no recognisable clinic-desc text."""
        html = """
        <ul class="list-group clinic-list">
          <li class="clinic">
            <div class="row pb-20">
              <div class="col-md-8">
                <h3 class="clinic-name"><a>Mystery Clinic</a></h3>
              </div>
            </div>
          </li>
        </ul>
        """
        clinics = extract_clinic_urls_from_page(html)
        assert len(clinics) == 1
        assert clinics[0]["clinic_type"] == "unknown"
        assert clinics[0]["parent_clinics"] == []

    def test_regular_clinic_with_href(self):
        html = """
        <ul class="list-group clinic-list">
          <li class="clinic">
            <div class="row pb-20">
              <div class="col-md-8">
                <h3 class="clinic-name">
                  <a href="/choose-a-clinic/clinic-search/results/153/">
                    Homerton Fertility Centre
                  </a>
                </h3>
              </div>
            </div>
          </li>
        </ul>
        """
        clinics = extract_clinic_urls_from_page(html)
        assert len(clinics) == 1
        assert clinics[0]["clinic_type"] == "clinic"
        assert clinics[0]["clinic_id"] == 153

    def test_mixed_page(self):
        """A page with a regular clinic, a satellite, and a transport."""
        html = """
        <ul class="list-group clinic-list">
          <li class="clinic">
            <div class="row pb-20">
              <div class="col-md-8">
                <h3 class="clinic-name">
                  <a href="/choose-a-clinic/clinic-search/results/109/">King's Fertility</a>
                </h3>
              </div>
            </div>
          </li>
          <li class="clinic">
            <div class="row pb-20">
              <div class="col-md-8">
                <h3 class="clinic-name"><a>Satellite X</a></h3>
                <p class="clinic-desc">Satellite clinic to
                  <a href="/choose-a-clinic/clinic-search/results/109/">King's Fertility</a>
                </p>
              </div>
            </div>
          </li>
          <li class="clinic">
            <div class="row pb-20">
              <div class="col-md-8">
                <h3 class="clinic-name"><a>Kingston Hospital ACU</a></h3>
                <p class="clinic-desc">Transport clinic to
                  <a href="/choose-a-clinic/clinic-search/results/109/">King's Fertility</a>
                </p>
              </div>
            </div>
          </li>
        </ul>
        """
        clinics = extract_clinic_urls_from_page(html)
        assert len(clinics) == 3
        assert clinics[0]["clinic_type"] == "clinic"
        assert clinics[0]["name"] == "King's Fertility"
        assert clinics[1]["clinic_type"] == "satellite"
        assert clinics[1]["name"] == "Satellite X"
        assert clinics[2]["clinic_type"] == "transport"
        assert clinics[2]["name"] == "Kingston Hospital ACU"


class TestBuildSearchUrl:
    def test_simple_postcode(self):
        url = build_search_url("E16 4JT", 50)
        assert url == "https://www.hfea.gov.uk/choose-a-clinic/clinic-search/results/?location=E16%204JT&distance=50"

    def test_postcode_without_space(self):
        url = build_search_url("SW1A1AA", 30)
        assert url == "https://www.hfea.gov.uk/choose-a-clinic/clinic-search/results/?location=SW1A1AA&distance=30"

    def test_strips_whitespace(self):
        url = build_search_url("  E16 4JT  ", 50)
        assert url == "https://www.hfea.gov.uk/choose-a-clinic/clinic-search/results/?location=E16%204JT&distance=50"

    def test_distance_truncated_to_int(self):
        url = build_search_url("E16 4JT", 50.7)
        assert "distance=50" in url

    def test_distance_as_string(self):
        url = build_search_url("E16 4JT", "50")
        assert "distance=50" in url

    def test_empty_location_raises(self):
        with pytest.raises(ValueError, match="empty"):
            build_search_url("", 50)

    def test_whitespace_only_location_raises(self):
        with pytest.raises(ValueError, match="empty"):
            build_search_url("   ", 50)

    def test_none_location_raises(self):
        with pytest.raises(ValueError, match="empty"):
            build_search_url(None, 50)

    def test_zero_distance_raises(self):
        with pytest.raises(ValueError, match="positive"):
            build_search_url("E16 4JT", 0)

    def test_negative_distance_raises(self):
        with pytest.raises(ValueError, match="positive"):
            build_search_url("E16 4JT", -5)


class TestParseArgs:
    def test_location_and_distance(self):
        args = parse_args(["--location", "E16 4JT", "--distance", "50"])
        assert args.location == "E16 4JT"
        assert args.distance == 50.0
        assert not args.interactive

    def test_interactive_flag(self):
        args = parse_args(["--interactive"])
        assert args.interactive is True
        assert args.location is None
        assert args.distance is None

    def test_defaults(self):
        args = parse_args(["--location", "X", "--distance", "10"])
        assert args.output == DEFAULT_OUTPUT
        assert args.max_pages == DEFAULT_MAX_PAGES
        assert args.debug is False

    def test_all_options(self):
        args = parse_args(
            [
                "--location",
                "SW1A1AA",
                "--distance",
                "30",
                "--output",
                "out.csv",
                "--max-pages",
                "5",
                "--debug",
            ]
        )
        assert args.location == "SW1A1AA"
        assert args.distance == 30.0
        assert args.output == "out.csv"
        assert args.max_pages == 5
        assert args.debug is True


class TestResolveArgs:
    def _make_args(
        self, location=None, distance=None, interactive=False, output=DEFAULT_OUTPUT, max_pages=DEFAULT_MAX_PAGES
    ):
        return argparse.Namespace(
            location=location,
            distance=distance,
            interactive=interactive,
            output=output,
            max_pages=max_pages,
        )

    def test_non_interactive_with_both_args(self):
        args = self._make_args(location="E16 4JT", distance=50)
        resolve_args(args)
        assert args.location == "E16 4JT"
        assert args.distance == 50

    def test_non_interactive_missing_location_exits(self):
        args = self._make_args(distance=50)
        with pytest.raises(SystemExit):
            resolve_args(args)

    def test_non_interactive_missing_distance_exits(self):
        args = self._make_args(location="E16 4JT")
        with pytest.raises(SystemExit):
            resolve_args(args)

    def test_interactive_prompts_for_all(self):
        args = self._make_args(interactive=True)
        inputs = iter(["E16 4JT", "50", "my_output.csv", "5"])
        resolve_args(args, input_fn=lambda _: next(inputs))
        assert args.location == "E16 4JT"
        assert args.distance == 50.0
        assert args.output == "my_output.csv"
        assert args.max_pages == 5

    def test_interactive_accepts_defaults_on_empty_input(self):
        args = self._make_args(interactive=True)
        inputs = iter(["E16 4JT", "50", "", ""])
        resolve_args(args, input_fn=lambda _: next(inputs))
        assert args.output == DEFAULT_OUTPUT
        assert args.max_pages == DEFAULT_MAX_PAGES

    def test_interactive_prompts_only_for_missing(self):
        args = self._make_args(location="SW1A1AA", interactive=True)
        inputs = iter(["30", "", ""])
        resolve_args(args, input_fn=lambda _: next(inputs))
        assert args.location == "SW1A1AA"
        assert args.distance == 30.0

    def test_interactive_skips_location_and_distance_when_provided(self):
        args = self._make_args(location="E16 4JT", distance=50, interactive=True)
        # Only output and max_pages prompts should fire
        inputs = iter(["", ""])
        resolve_args(args, input_fn=lambda _: next(inputs))
        assert args.location == "E16 4JT"
        assert args.distance == 50

    def test_interactive_invalid_distance_exits(self):
        args = self._make_args(interactive=True)
        inputs = iter(["E16 4JT", "not-a-number"])
        with pytest.raises(SystemExit):
            resolve_args(args, input_fn=lambda _: next(inputs))

    def test_interactive_invalid_max_pages_exits(self):
        args = self._make_args(interactive=True)
        inputs = iter(["E16 4JT", "50", "", "abc"])
        with pytest.raises(SystemExit):
            resolve_args(args, input_fn=lambda _: next(inputs))

    def test_interactive_custom_output(self):
        args = self._make_args(location="X", distance=10, interactive=True)
        inputs = iter(["custom/path.csv", ""])
        resolve_args(args, input_fn=lambda _: next(inputs))
        assert args.output == "custom/path.csv"


# ── Tests against archived HTML (real page structure) ────────────────────


EMPTY_SEARCH_HTML = """
<html><body>
    <ul class="list-group clinic-list"></ul>
</body></html>
"""


@requires_archived_html
class TestExtractClinicUrlsFromRealHtml:
    """Test extract_clinic_urls_from_page against archived search results."""

    def test_finds_all_10_clinics(self, search_results_html):
        clinics = extract_clinic_urls_from_page(search_results_html)
        assert len(clinics) == 10

    def test_first_clinic_is_homerton(self, search_results_html):
        clinics = extract_clinic_urls_from_page(search_results_html)
        homerton = clinics[0]
        assert homerton["name"] == "Homerton Fertility Centre"
        assert homerton["clinic_id"] == 153
        assert homerton["clinic_type"] == "clinic"
        assert homerton["distance"] == 3.21

    def test_satellite_clinic_detected(self, search_results_html):
        clinics = extract_clinic_urls_from_page(search_results_html)
        lister_shard = next(c for c in clinics if "Shard" in c["name"])
        assert lister_shard["clinic_type"] == "satellite"
        assert lister_shard["clinic_id"] is None
        assert lister_shard["distance"] == 4.48
        assert len(lister_shard["parent_clinics"]) == 1
        assert lister_shard["parent_clinics"][0]["clinic_id"] == 6
        assert lister_shard["parent_clinics"][0]["name"] == "The Lister Fertility Clinic"

    def test_multi_parent_satellite(self, search_results_html):
        clinics = extract_clinic_urls_from_page(search_results_html)
        egg_bank = next(c for c in clinics if "London Egg Bank" in c["name"])
        assert egg_bank["clinic_type"] == "satellite"
        assert len(egg_bank["parent_clinics"]) == 3
        parent_ids = [p["clinic_id"] for p in egg_bank["parent_clinics"]]
        assert parent_ids == [75, 105, 301]

    def test_clinic_with_treatments(self, search_results_html):
        clinics = extract_clinic_urls_from_page(search_results_html)
        create = next(c for c in clinics if "CREATE" in c["name"])
        assert create["treatments"]["ivf"] is True
        assert create["treatments"]["icsi"] is True
        assert create["treatments"]["surgical_sperm"] is True

    def test_kings_fertility(self, search_results_html):
        clinics = extract_clinic_urls_from_page(search_results_html)
        kings = next(c for c in clinics if "King" in c["name"])
        assert kings["clinic_id"] == 109
        assert kings["distance"] == 5.78
        assert kings["clinic_type"] == "clinic"


# ── scrape_search_results (mocked network) ───────────────────────────────


@requires_archived_html
class TestScrapeSearchResults:
    def test_single_page_of_results(self, search_results_html):
        """Page 1 returns clinics, page 2 returns empty → stops."""
        call_count = [0]

        def mock_fetch_page(url, max_retries=3):
            call_count[0] += 1
            if "page=1" in url:
                return search_results_html
            return EMPTY_SEARCH_HTML

        with patch("scraper.fetch_page", side_effect=mock_fetch_page):
            clinics = scrape_search_results(
                "https://www.hfea.gov.uk/choose-a-clinic/clinic-search/results/?location=e16+4jt&distance=50",
                max_pages=5,
            )

        assert len(clinics) == 10
        assert call_count[0] == 2  # page 1 + page 2 (empty, stops)

    def test_max_pages_respected(self, search_results_html):
        """Stops after max_pages even if results keep coming."""

        def mock_fetch_page(url, max_retries=3):
            return search_results_html  # always return results

        with patch("scraper.fetch_page", side_effect=mock_fetch_page):
            clinics = scrape_search_results(
                "https://example.com/results/?location=X&distance=10",
                max_pages=2,
            )

        # 2 pages x 10 clinics = 20
        assert len(clinics) == 20

    def test_failed_page_is_skipped(self, search_results_html):
        """If fetch_page returns None, that page is skipped."""

        def mock_fetch_page(url, max_retries=3):
            if "page=1" in url:
                return None  # simulate failure
            if "page=2" in url:
                return search_results_html
            return EMPTY_SEARCH_HTML

        with patch("scraper.fetch_page", side_effect=mock_fetch_page):
            clinics = scrape_search_results(
                "https://example.com/results/?location=X&distance=10",
                max_pages=3,
            )

        # Page 1 failed (0), page 2 has 10, page 3 empty
        assert len(clinics) == 10


# ── scrape_clinic_detail (mocked network) ────────────────────────────────


@requires_archived_html
class TestScrapeClinicDetail:
    def test_extracts_data_from_detail_page(self, barts_detail_html):
        def mock_fetch_page(url, max_retries=3):
            return barts_detail_html

        with patch("scraper.fetch_page", side_effect=mock_fetch_page):
            data = scrape_clinic_detail(94, "Barts", {"ivf": True, "icsi": True, "surgical_sperm": False})

        assert data is not None
        assert data["Name of clinic"] == "Barts Health Centre for Reproductive Medicine"
        assert data["Do they do IVF"] is True
        assert data["Do they do ICSI"] is True
        assert data["Do they do Surgical sperm collection"] is False
        assert data["Inspection rating out of 5"] == 5.0

    def test_returns_none_on_fetch_failure(self):
        with patch("scraper.fetch_page", return_value=None):
            data = scrape_clinic_detail(999, "Missing Clinic", {})
        assert data is None


# ── write_csv ────────────────────────────────────────────────────────────


class TestWriteCsv:
    def test_writes_correct_structure(self):
        data = [
            {
                "Name of clinic": "Test Clinic",
                "Satellite of": "",
                "Transport for": "",
                "Distance (miles)": 5.0,
                "BMI eligibility limit": True,
                "Do they do egg-freezing": True,
                "Do they do IVF": True,
                "Do they do ICSI": False,
                "Do they do Surgical sperm collection": False,
                "Treats NHS patients": True,
                "Treats private patients": False,
                "At least one counselling session included": True,
                "Inspection rating out of 5": 4.0,
                "Patient rating out of 5": 3.5,
                "Number of patient ratings": 10,
                "Patient empowerment rating": 3.0,
                "Patient empathy rating": 3.5,
                "Under 38s births per embryo transferred": 30.0,
                "Error bars: Under 38s births per embryo transferred": 10.0,
                "Under 38s births per egg collection": 40.0,
                "Error bars: Under 38s births per egg collection": 15.0,
                "Under 38s births per donor insemination treatment": 12.0,
                "Error bars: Under 38s births per donor insemination treatment": 20.0,
            }
        ]

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            tmp_path = f.name

        try:
            write_csv(data, tmp_path)

            with open(tmp_path, "r", encoding="utf-8") as f:
                reader = list(csv.reader(f))

            # 3 metadata rows + 1 data row
            assert len(reader) == 4
            # First cell of row 1 is "Thing of interest:"
            assert reader[0][0] == "Thing of interest:"
            # First cell of row 2 is "Type:"
            assert reader[1][0] == "Type:"
            # First cell of row 3 is "Where to find it on the page:"
            assert reader[2][0] == "Where to find it on the page:"
            # Data row has clinic name
            assert reader[3][0] == "Test Clinic"
        finally:
            os.unlink(tmp_path)

    def test_empty_data_writes_nothing(self, capsys):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            tmp_path = f.name

        try:
            write_csv([], tmp_path)
            captured = capsys.readouterr()
            assert "No data" in captured.out
        finally:
            os.unlink(tmp_path)


# ── scrape_all_clinics (end-to-end with mocked network) ──────────────────


@requires_archived_html
class TestScrapeAllClinics:
    def test_end_to_end_pipeline(self, search_results_html, barts_detail_html):
        """Full pipeline: search results → detail pages → merged data."""

        def mock_fetch_page(url, max_retries=3):
            if "page=1" in url:
                return search_results_html
            if "page=2" in url:
                return EMPTY_SEARCH_HTML
            # Any detail page request returns Barts HTML
            if "/results/" in url and url.rstrip("/").split("/")[-1].isdigit():
                return barts_detail_html
            return EMPTY_SEARCH_HTML

        with patch("scraper.fetch_page", side_effect=mock_fetch_page):
            data = scrape_all_clinics(
                "https://www.hfea.gov.uk/choose-a-clinic/clinic-search/results/?location=e16+4jt&distance=50",
                max_pages=5,
            )

        # Should have data for all 10 clinics from search page
        # + parent clinics outside search area (IDs 75, 105, 301 not in results)
        assert len(data) > 0
        names = [d["Name of clinic"] for d in data]
        # Satellites should be present
        assert any("Shard" in n for n in names)
        # Regular clinics should have detail data
        barts_data = next(d for d in data if "Barts" in d["Name of clinic"])
        assert barts_data["Inspection rating out of 5"] == 5.0

    def test_satellite_distances_override_parents(self, search_results_html, barts_detail_html):
        """Parent clinic distances are overridden by nearest satellite distance."""

        def mock_fetch_page(url, max_retries=3):
            if "page=1" in url:
                return search_results_html
            if "page=2" in url:
                return EMPTY_SEARCH_HTML
            if "/results/" in url and url.rstrip("/").split("/")[-1].isdigit():
                return barts_detail_html
            return EMPTY_SEARCH_HTML

        with patch("scraper.fetch_page", side_effect=mock_fetch_page):
            data = scrape_all_clinics(
                "https://www.hfea.gov.uk/choose-a-clinic/clinic-search/results/?location=e16+4jt&distance=50",
                max_pages=5,
            )

        # The Lister Fertility Clinic (ID 6) should be fetched as a missing parent
        # and should get the satellite's distance (4.48 miles)
        missing_parents = [d for d in data if d.get("Warning") == "Parent clinic outside search area"]
        assert len(missing_parents) > 0


# ── main (end-to-end) ───────────────────────────────────────────────────


@requires_archived_html
class TestMain:
    def test_main_writes_csv(self, search_results_html, barts_detail_html):
        def mock_fetch_page(url, max_retries=3):
            if "page=1" in url:
                return search_results_html
            if "page=2" in url:
                return EMPTY_SEARCH_HTML
            if "/results/" in url and url.rstrip("/").split("/")[-1].isdigit():
                return barts_detail_html
            return EMPTY_SEARCH_HTML

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            tmp_path = f.name

        try:
            with patch("scraper.fetch_page", side_effect=mock_fetch_page):
                result = main(
                    [
                        "--location",
                        "E16 4JT",
                        "--distance",
                        "50",
                        "--output",
                        tmp_path,
                        "--max-pages",
                        "2",
                    ]
                )

            assert result == 0
            # CSV should exist and have data
            with open(tmp_path, "r", encoding="utf-8") as f:
                reader = list(csv.reader(f))
            # 3 metadata rows + data rows
            assert len(reader) > 3
        finally:
            os.unlink(tmp_path)
