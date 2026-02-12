"""Unit tests for scraper parent clinic resolution and extraction."""

import argparse
import pytest
from scraper import (
    resolve_parent_clinics, extract_clinic_urls_from_page,
    build_search_url, parse_args, resolve_args,
    DEFAULT_MAX_PAGES, DEFAULT_OUTPUT,
)


class TestResolveParentClinics:

    def test_single_satellite_parent_in_results(self):
        clinics = [
            {'name': 'Parent Clinic', 'clinic_id': 6, 'clinic_type': 'clinic',
             'distance': 20.0, 'parent_clinics': []},
            {'name': 'Satellite A', 'clinic_id': None, 'clinic_type': 'satellite',
             'distance': 4.48, 'parent_clinics': [
                 {'name': 'Parent Clinic', 'clinic_id': 6, 'url': '/results/6/'}
             ]},
        ]
        parent_dist, missing = resolve_parent_clinics(clinics)
        assert parent_dist == {6: 4.48}
        assert missing == set()

    def test_multiple_satellites_same_parent_takes_minimum(self):
        clinics = [
            {'name': 'Parent', 'clinic_id': 6, 'clinic_type': 'clinic',
             'distance': 30.0, 'parent_clinics': []},
            {'name': 'Sat A', 'clinic_id': None, 'clinic_type': 'satellite',
             'distance': 5.0, 'parent_clinics': [
                 {'name': 'Parent', 'clinic_id': 6, 'url': '/results/6/'}
             ]},
            {'name': 'Sat B', 'clinic_id': None, 'clinic_type': 'satellite',
             'distance': 3.0, 'parent_clinics': [
                 {'name': 'Parent', 'clinic_id': 6, 'url': '/results/6/'}
             ]},
        ]
        parent_dist, missing = resolve_parent_clinics(clinics)
        assert parent_dist == {6: 3.0}
        assert missing == set()

    def test_parent_not_in_results_is_missing(self):
        clinics = [
            {'name': 'Sat A', 'clinic_id': None, 'clinic_type': 'satellite',
             'distance': 4.48, 'parent_clinics': [
                 {'name': 'Distant Parent', 'clinic_id': 99, 'url': '/results/99/'}
             ]},
        ]
        parent_dist, missing = resolve_parent_clinics(clinics)
        assert parent_dist == {99: 4.48}
        assert missing == {99}

    def test_satellite_with_multiple_parents(self):
        clinics = [
            {'name': 'Parent A', 'clinic_id': 75, 'clinic_type': 'clinic',
             'distance': 50.0, 'parent_clinics': []},
            {'name': 'Sat', 'clinic_id': None, 'clinic_type': 'satellite',
             'distance': 4.54, 'parent_clinics': [
                 {'name': 'Parent A', 'clinic_id': 75, 'url': '/results/75/'},
                 {'name': 'Parent B', 'clinic_id': 105, 'url': '/results/105/'},
                 {'name': 'Parent C', 'clinic_id': 301, 'url': '/results/301/'},
             ]},
        ]
        parent_dist, missing = resolve_parent_clinics(clinics)
        assert parent_dist == {75: 4.54, 105: 4.54, 301: 4.54}
        assert missing == {105, 301}

    def test_no_satellites(self):
        clinics = [
            {'name': 'Clinic A', 'clinic_id': 1, 'clinic_type': 'clinic',
             'distance': 5.0, 'parent_clinics': []},
        ]
        parent_dist, missing = resolve_parent_clinics(clinics)
        assert parent_dist == {}
        assert missing == set()

    def test_satellite_with_none_distance(self):
        clinics = [
            {'name': 'Sat', 'clinic_id': None, 'clinic_type': 'satellite',
             'distance': None, 'parent_clinics': [
                 {'name': 'Parent', 'clinic_id': 6, 'url': '/results/6/'}
             ]},
        ]
        parent_dist, missing = resolve_parent_clinics(clinics)
        assert parent_dist == {6: None}

    def test_parent_with_no_id_is_ignored(self):
        clinics = [
            {'name': 'Sat', 'clinic_id': None, 'clinic_type': 'satellite',
             'distance': 3.0, 'parent_clinics': [
                 {'name': 'Mystery Parent', 'clinic_id': None, 'url': None}
             ]},
        ]
        parent_dist, missing = resolve_parent_clinics(clinics)
        assert parent_dist == {}
        assert missing == set()

    def test_mixed_none_and_real_distances_takes_min_of_real(self):
        clinics = [
            {'name': 'Sat A', 'clinic_id': None, 'clinic_type': 'satellite',
             'distance': None, 'parent_clinics': [
                 {'name': 'Parent', 'clinic_id': 6, 'url': '/results/6/'}
             ]},
            {'name': 'Sat B', 'clinic_id': None, 'clinic_type': 'satellite',
             'distance': 7.0, 'parent_clinics': [
                 {'name': 'Parent', 'clinic_id': 6, 'url': '/results/6/'}
             ]},
        ]
        parent_dist, missing = resolve_parent_clinics(clinics)
        assert parent_dist == {6: 7.0}

    def test_transport_clinics_are_excluded(self):
        """Transport clinics should not contribute to parent distance map."""
        clinics = [
            {'name': 'Transport A', 'clinic_id': None, 'clinic_type': 'transport',
             'distance': 2.0, 'parent_clinics': [
                 {'name': 'Parent', 'clinic_id': 109, 'url': '/results/109/'}
             ]},
        ]
        parent_dist, missing = resolve_parent_clinics(clinics)
        assert parent_dist == {}
        assert missing == set()

    def test_transport_and_satellite_mixed(self):
        """Only satellites feed into parent resolution, not transports."""
        clinics = [
            {'name': 'Parent', 'clinic_id': 109, 'clinic_type': 'clinic',
             'distance': 10.0, 'parent_clinics': []},
            {'name': 'Satellite', 'clinic_id': None, 'clinic_type': 'satellite',
             'distance': 5.0, 'parent_clinics': [
                 {'name': 'Parent', 'clinic_id': 109, 'url': '/results/109/'}
             ]},
            {'name': 'Transport', 'clinic_id': None, 'clinic_type': 'transport',
             'distance': 2.0, 'parent_clinics': [
                 {'name': 'Parent', 'clinic_id': 109, 'url': '/results/109/'}
             ]},
        ]
        parent_dist, missing = resolve_parent_clinics(clinics)
        # Only satellite distance (5.0), not transport distance (2.0)
        assert parent_dist == {109: 5.0}
        assert missing == set()


class TestExtractClinicTypes:

    def test_satellite_clinic(self):
        html = '''
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
        '''
        clinics = extract_clinic_urls_from_page(html)
        assert len(clinics) == 1
        assert clinics[0]['clinic_type'] == 'satellite'
        assert clinics[0]['parent_clinics'] == [
            {'name': 'Parent Clinic', 'clinic_id': 6,
             'url': '/choose-a-clinic/clinic-search/results/6/'}
        ]

    def test_satellite_with_multiple_parents(self):
        html = '''
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
        '''
        clinics = extract_clinic_urls_from_page(html)
        assert len(clinics) == 1
        assert clinics[0]['clinic_type'] == 'satellite'
        assert len(clinics[0]['parent_clinics']) == 2
        assert clinics[0]['parent_clinics'][0]['clinic_id'] == 75
        assert clinics[0]['parent_clinics'][1]['clinic_id'] == 105

    def test_transport_clinic(self):
        html = '''
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
        '''
        clinics = extract_clinic_urls_from_page(html)
        assert len(clinics) == 1
        assert clinics[0]['clinic_type'] == 'transport'
        assert clinics[0]['name'] == 'Croydon University Hospital'
        assert clinics[0]['parent_clinics'] == [
            {'name': "London Women's Clinic", 'clinic_id': 105,
             'url': '/choose-a-clinic/clinic-search/results/105/'}
        ]
        assert clinics[0]['distance'] == 10.5

    def test_unknown_type_no_desc(self):
        """A card with no href and no recognisable clinic-desc text."""
        html = '''
        <ul class="list-group clinic-list">
          <li class="clinic">
            <div class="row pb-20">
              <div class="col-md-8">
                <h3 class="clinic-name"><a>Mystery Clinic</a></h3>
              </div>
            </div>
          </li>
        </ul>
        '''
        clinics = extract_clinic_urls_from_page(html)
        assert len(clinics) == 1
        assert clinics[0]['clinic_type'] == 'unknown'
        assert clinics[0]['parent_clinics'] == []

    def test_regular_clinic_with_href(self):
        html = '''
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
        '''
        clinics = extract_clinic_urls_from_page(html)
        assert len(clinics) == 1
        assert clinics[0]['clinic_type'] == 'clinic'
        assert clinics[0]['clinic_id'] == 153

    def test_mixed_page(self):
        """A page with a regular clinic, a satellite, and a transport."""
        html = '''
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
        '''
        clinics = extract_clinic_urls_from_page(html)
        assert len(clinics) == 3
        assert clinics[0]['clinic_type'] == 'clinic'
        assert clinics[0]['name'] == "King's Fertility"
        assert clinics[1]['clinic_type'] == 'satellite'
        assert clinics[1]['name'] == 'Satellite X'
        assert clinics[2]['clinic_type'] == 'transport'
        assert clinics[2]['name'] == 'Kingston Hospital ACU'


class TestBuildSearchUrl:

    def test_simple_postcode(self):
        url = build_search_url('E16 4JT', 50)
        assert url == 'https://www.hfea.gov.uk/choose-a-clinic/clinic-search/results/?location=E16%204JT&distance=50'

    def test_postcode_without_space(self):
        url = build_search_url('SW1A1AA', 30)
        assert url == 'https://www.hfea.gov.uk/choose-a-clinic/clinic-search/results/?location=SW1A1AA&distance=30'

    def test_strips_whitespace(self):
        url = build_search_url('  E16 4JT  ', 50)
        assert url == 'https://www.hfea.gov.uk/choose-a-clinic/clinic-search/results/?location=E16%204JT&distance=50'

    def test_distance_truncated_to_int(self):
        url = build_search_url('E16 4JT', 50.7)
        assert 'distance=50' in url

    def test_distance_as_string(self):
        url = build_search_url('E16 4JT', '50')
        assert 'distance=50' in url

    def test_empty_location_raises(self):
        with pytest.raises(ValueError, match="empty"):
            build_search_url('', 50)

    def test_whitespace_only_location_raises(self):
        with pytest.raises(ValueError, match="empty"):
            build_search_url('   ', 50)

    def test_none_location_raises(self):
        with pytest.raises(ValueError, match="empty"):
            build_search_url(None, 50)

    def test_zero_distance_raises(self):
        with pytest.raises(ValueError, match="positive"):
            build_search_url('E16 4JT', 0)

    def test_negative_distance_raises(self):
        with pytest.raises(ValueError, match="positive"):
            build_search_url('E16 4JT', -5)


class TestParseArgs:

    def test_location_and_distance(self):
        args = parse_args(['--location', 'E16 4JT', '--distance', '50'])
        assert args.location == 'E16 4JT'
        assert args.distance == 50.0
        assert not args.interactive

    def test_interactive_flag(self):
        args = parse_args(['--interactive'])
        assert args.interactive is True
        assert args.location is None
        assert args.distance is None

    def test_defaults(self):
        args = parse_args(['--location', 'X', '--distance', '10'])
        assert args.output == DEFAULT_OUTPUT
        assert args.max_pages == DEFAULT_MAX_PAGES
        assert args.debug is False

    def test_all_options(self):
        args = parse_args([
            '--location', 'SW1A1AA', '--distance', '30',
            '--output', 'out.csv', '--max-pages', '5', '--debug',
        ])
        assert args.location == 'SW1A1AA'
        assert args.distance == 30.0
        assert args.output == 'out.csv'
        assert args.max_pages == 5
        assert args.debug is True


class TestResolveArgs:

    def _make_args(self, location=None, distance=None, interactive=False,
                   output=DEFAULT_OUTPUT, max_pages=DEFAULT_MAX_PAGES):
        return argparse.Namespace(
            location=location, distance=distance, interactive=interactive,
            output=output, max_pages=max_pages,
        )

    def test_non_interactive_with_both_args(self):
        args = self._make_args(location='E16 4JT', distance=50)
        resolve_args(args)
        assert args.location == 'E16 4JT'
        assert args.distance == 50

    def test_non_interactive_missing_location_exits(self):
        args = self._make_args(distance=50)
        with pytest.raises(SystemExit):
            resolve_args(args)

    def test_non_interactive_missing_distance_exits(self):
        args = self._make_args(location='E16 4JT')
        with pytest.raises(SystemExit):
            resolve_args(args)

    def test_interactive_prompts_for_all(self):
        args = self._make_args(interactive=True)
        inputs = iter(['E16 4JT', '50', 'my_output.csv', '5'])
        resolve_args(args, input_fn=lambda _: next(inputs))
        assert args.location == 'E16 4JT'
        assert args.distance == 50.0
        assert args.output == 'my_output.csv'
        assert args.max_pages == 5

    def test_interactive_accepts_defaults_on_empty_input(self):
        args = self._make_args(interactive=True)
        inputs = iter(['E16 4JT', '50', '', ''])
        resolve_args(args, input_fn=lambda _: next(inputs))
        assert args.output == DEFAULT_OUTPUT
        assert args.max_pages == DEFAULT_MAX_PAGES

    def test_interactive_prompts_only_for_missing(self):
        args = self._make_args(location='SW1A1AA', interactive=True)
        inputs = iter(['30', '', ''])
        resolve_args(args, input_fn=lambda _: next(inputs))
        assert args.location == 'SW1A1AA'
        assert args.distance == 30.0

    def test_interactive_skips_location_and_distance_when_provided(self):
        args = self._make_args(location='E16 4JT', distance=50, interactive=True)
        # Only output and max_pages prompts should fire
        inputs = iter(['', ''])
        resolve_args(args, input_fn=lambda _: next(inputs))
        assert args.location == 'E16 4JT'
        assert args.distance == 50

    def test_interactive_invalid_distance_exits(self):
        args = self._make_args(interactive=True)
        inputs = iter(['E16 4JT', 'not-a-number'])
        with pytest.raises(SystemExit):
            resolve_args(args, input_fn=lambda _: next(inputs))

    def test_interactive_invalid_max_pages_exits(self):
        args = self._make_args(interactive=True)
        inputs = iter(['E16 4JT', '50', '', 'abc'])
        with pytest.raises(SystemExit):
            resolve_args(args, input_fn=lambda _: next(inputs))

    def test_interactive_custom_output(self):
        args = self._make_args(location='X', distance=10, interactive=True)
        inputs = iter(['custom/path.csv', ''])
        resolve_args(args, input_fn=lambda _: next(inputs))
        assert args.output == 'custom/path.csv'
