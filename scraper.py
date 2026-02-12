#!/usr/bin/env python3
"""
HFEA Clinic Data Scraper

Scrapes fertility clinic data from HFEA website and outputs to CSV.
"""

import argparse
import csv
import re
import sys
import time
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse, quote
import requests
from bs4 import BeautifulSoup
import extractors


# Headers to use for requests
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

BASE_URL = 'https://www.hfea.gov.uk'
SEARCH_PATH = '/choose-a-clinic/clinic-search/results/'
RATE_LIMIT_DELAY = 1.5  # seconds between requests
RATE_LIMIT_BACKOFF_MULTIPLIER = 2
REQUEST_TIMEOUT = 30
DEFAULT_MAX_RETRIES = 3
DEFAULT_MAX_PAGES = 20
DEFAULT_OUTPUT = 'output/clinics_data.csv'


def build_search_url(location, distance):
    """
    Construct an HFEA clinic search URL from location and distance.

    Args:
        location: Postcode or place name (e.g. 'E16 4JT')
        distance: Search radius in miles (positive number)

    Returns:
        Full search URL string

    Raises:
        ValueError: If location is empty/whitespace or distance is not positive
    """
    if not location or not location.strip():
        raise ValueError("Location must not be empty")
    distance = float(distance)
    if distance <= 0:
        raise ValueError("Distance must be a positive number")
    return f"{BASE_URL}{SEARCH_PATH}?location={quote(location.strip())}&distance={int(distance)}"


def fetch_page(url, max_retries=DEFAULT_MAX_RETRIES):
    """
    Fetch a page with rate limiting and retries.

    Args:
        url: URL to fetch
        max_retries: Number of retry attempts

    Returns:
        HTML content as string, or None if failed
    """
    for attempt in range(max_retries):
        try:
            time.sleep(RATE_LIMIT_DELAY)
            response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            print(f"  ⚠ Error fetching {url}: {e}")
            if attempt < max_retries - 1:
                print(f"  Retrying ({attempt + 2}/{max_retries})...")
                time.sleep(RATE_LIMIT_DELAY * RATE_LIMIT_BACKOFF_MULTIPLIER)
            else:
                print(f"  ✗ Failed after {max_retries} attempts")
                return None


def extract_clinic_urls_from_page(html, debug=False):
    """
    Extract clinic URLs and treatment info from a search results page.
    Also extracts satellite clinics (those without detail page hrefs).

    Args:
        html: HTML content of search results page
        debug: If True, print verbose logging

    Returns:
        List of dicts with clinic info: {
            'name': str,
            'url': str or None (for satellites),
            'clinic_id': int or None (for satellites),
            'treatments': dict,
            'is_satellite': bool,
            'parent_clinics': list of parent clinic names,
            'distance': float or None (miles from search center)
        }
    """
    soup = BeautifulSoup(html, 'lxml')
    clinics = []

    clinic_cards = soup.find_all('li', class_='clinic')

    if debug:
        print(f"  DEBUG: Found {len(clinic_cards)} clinic cards on page")

    for i, card in enumerate(clinic_cards, 1):
        if debug:
            print(f"  DEBUG: Processing card {i}/{len(clinic_cards)}")

        name_heading = card.find('h3', class_='clinic-name')
        if not name_heading:
            if debug:
                print(f"  DEBUG: Card {i} - No h3.clinic-name found, SKIPPING")
            continue

        link = name_heading.find('a')
        if not link:
            if debug:
                print(f"  DEBUG: Card {i} - No link in h3, SKIPPING")
            continue

        href = link.get('href')
        name = link.get_text(strip=True)

        # Extract distance (e.g., "4.54 miles")
        distance = None
        distance_p = card.find('p', class_='distance')
        if distance_p:
            distance_text = distance_p.get_text(strip=True)
            distance_match = re.search(r'([\d.]+)\s*miles?', distance_text, re.IGNORECASE)
            if distance_match:
                distance = float(distance_match.group(1))

        if debug:
            print(f"  DEBUG: Card {i} - Name: {name}, href: {href}, distance: {distance} miles")

        # Extract treatments from card
        treatments = extractors.extract_treatments_from_search_card(card)

        # Check if this is a satellite/transport clinic (no href)
        if not href:
            # Determine clinic type and extract parent references from desc
            parent_clinics = []
            clinic_type = 'unknown'  # satellite, transport, or unknown
            desc_paragraphs = card.find_all('p', class_='clinic-desc')

            for p in desc_paragraphs:
                text = p.get_text(strip=True)
                if 'Satellite clinic to' in text:
                    clinic_type = 'satellite'
                elif 'Transport clinic to' in text:
                    clinic_type = 'transport'
                else:
                    continue

                parent_link = p.find('a')
                if parent_link:
                    parent_name = parent_link.get_text(strip=True)
                    parent_href = parent_link.get('href')
                    parent_id = None
                    if parent_href:
                        id_match = re.search(r'/results/(\d+)/?', parent_href)
                        if id_match:
                            parent_id = int(id_match.group(1))
                    parent_clinics.append({
                        'name': parent_name,
                        'clinic_id': parent_id,
                        'url': parent_href
                    })

            if debug:
                print(f"  DEBUG: Card {i} - {clinic_type} clinic, parent(s): {parent_clinics}")

            clinics.append({
                'name': name,
                'url': None,
                'clinic_id': None,
                'treatments': treatments,
                'clinic_type': clinic_type,
                'parent_clinics': parent_clinics,
                'distance': distance
            })

            if debug:
                print(f"  DEBUG: Card {i} - Added as {clinic_type} clinic")
            continue

        # Extract clinic ID from URL like /choose-a-clinic/clinic-search/results/153/
        match = re.search(r'/results/(\d+)/?', href)
        if match:
            clinic_id = int(match.group(1))

            if debug:
                print(f"  DEBUG: Card {i} - Extracted clinic_id: {clinic_id}")

            clinics.append({
                'name': name,
                'url': href,
                'clinic_id': clinic_id,
                'treatments': treatments,
                'clinic_type': 'clinic',
                'parent_clinics': [],
                'distance': distance
            })

            if debug:
                print(f"  DEBUG: Card {i} - Successfully added to list")
        else:
            print(f"  ⚠ Warning: Clinic '{name}' has unexpected href format: '{href}' — included without clinic_id")
            clinics.append({
                'name': name,
                'url': href,
                'clinic_id': None,
                'treatments': treatments,
                'clinic_type': 'clinic',
                'parent_clinics': [],
                'distance': distance,
                'unexpected_href': href
            })

    return clinics


def scrape_search_results(search_url, max_pages=DEFAULT_MAX_PAGES, debug=False):
    """
    Scrape all clinic URLs from paginated search results.

    Args:
        search_url: Initial search URL
        max_pages: Maximum number of pages to scrape
        debug: If True, print verbose logging

    Returns:
        List of clinic info dicts
    """
    print(f"Scraping search results from: {search_url}")
    print()

    all_clinics = []

    for page_num in range(1, max_pages + 1):
        print(f"📄 Fetching page {page_num}/{max_pages}...")

        # Build URL for this page
        parsed = urlparse(search_url)
        params = parse_qs(parsed.query)
        params['page'] = [str(page_num)]
        new_query = urlencode(params, doseq=True)
        page_url = urlunparse(parsed._replace(query=new_query))

        if debug:
            print(f"  DEBUG: Page URL: {page_url}")

        # Fetch page
        html = fetch_page(page_url)
        if not html:
            print(f"  ⚠ Skipping page {page_num}")
            continue

        # Extract clinic URLs
        clinics = extract_clinic_urls_from_page(html, debug=debug)
        print(f"  ✓ Found {len(clinics)} clinics on page {page_num}")

        all_clinics.extend(clinics)

        # If we got no clinics, we've probably reached the end
        if not clinics:
            print(f"  No clinics found, stopping pagination")
            break

    print()
    print(f"✓ Total clinics found: {len(all_clinics)}")
    print()

    return all_clinics


def scrape_clinic_detail(clinic_id, clinic_name, treatments_from_search):
    """
    Scrape detailed data from a single clinic page.

    Args:
        clinic_id: Clinic ID number
        clinic_name: Clinic name (for logging)
        treatments_from_search: Dict of treatments extracted from search card

    Returns:
        Dict with all 21 data fields, or None if failed
    """
    url = f"{BASE_URL}{SEARCH_PATH}{clinic_id}/"

    print(f"  Fetching detail page...")
    html = fetch_page(url)

    if not html:
        return None

    # Extract all data
    try:
        data = extractors.extract_all_clinic_data(html)

        # Add treatment data from search results
        data['Do they do IVF'] = treatments_from_search.get('ivf', False)
        data['Do they do ICSI'] = treatments_from_search.get('icsi', False)
        data['Do they do Surgical sperm collection'] = treatments_from_search.get('surgical_sperm', False)

        return data
    except Exception as e:
        print(f"  ✗ Error extracting data: {e}")
        return None


def resolve_parent_clinics(clinics):
    """
    Analyze satellite-parent relationships and compute parent distances.

    For each parent clinic referenced by a satellite, tracks the minimum
    satellite distance and determines whether the parent is in search results.

    Args:
        clinics: List of clinic dicts from scrape_search_results

    Returns:
        (parent_distance_map, missing_parent_ids):
            parent_distance_map: dict mapping parent clinic_id to
                minimum satellite distance (float or None)
            missing_parent_ids: set of parent clinic_ids not in search results
    """
    result_clinic_ids = {
        c['clinic_id'] for c in clinics
        if c.get('clinic_id') is not None
    }

    # Collect satellite distances per parent (only satellites, not transport clinics)
    parent_satellite_distances = {}
    for c in clinics:
        if c.get('clinic_type') != 'satellite':
            continue
        satellite_distance = c.get('distance')
        for parent in c.get('parent_clinics', []):
            parent_id = parent.get('clinic_id')
            if parent_id is None:
                continue
            if parent_id not in parent_satellite_distances:
                parent_satellite_distances[parent_id] = []
            if satellite_distance is not None:
                parent_satellite_distances[parent_id].append(satellite_distance)

    # Min distance per parent (None if no satellite had a distance)
    parent_distance_map = {}
    for parent_id, distances in parent_satellite_distances.items():
        parent_distance_map[parent_id] = min(distances) if distances else None

    missing_parent_ids = set(parent_satellite_distances.keys()) - result_clinic_ids

    return parent_distance_map, missing_parent_ids


def scrape_all_clinics(search_url, max_pages=DEFAULT_MAX_PAGES, debug=False):
    """
    Scrape all clinics from search results and their detail pages.

    Args:
        search_url: HFEA search results URL
        max_pages: Maximum number of result pages to scrape
        debug: If True, print verbose logging

    Returns:
        List of dicts with clinic data
    """
    # Step 1: Get all clinic URLs from search results
    clinics = scrape_search_results(search_url, max_pages, debug=debug)

    if not clinics:
        print("✗ No clinics found in search results")
        return []

    # Step 1b: Resolve parent clinic relationships
    parent_distance_map, missing_parent_ids = resolve_parent_clinics(clinics)

    # Step 2: Scrape each clinic detail page
    print("=" * 60)
    print("Scraping clinic detail pages...")
    print("=" * 60)
    print()

    all_data = []
    clinic_id_to_data_index = {}
    successful = 0
    failed = 0

    for i, clinic in enumerate(clinics, 1):
        clinic_type = clinic.get('clinic_type', 'clinic')

        # Handle satellite, transport, and unknown clinic types (no detail page)
        if clinic_type in ('satellite', 'transport', 'unknown'):
            parent_clinics = clinic.get('parent_clinics', [])
            parent_names = ', '.join(p['name'] for p in parent_clinics) if parent_clinics else 'Unknown'

            type_label = clinic_type.capitalize()
            print(f"[{i}/{len(clinics)}] {clinic['name']} ({type_label})")

            data = {
                'Name of clinic': clinic['name'],
                'Satellite of': parent_names if clinic_type == 'satellite' else '',
                'Transport for': parent_names if clinic_type == 'transport' else '',
                'Distance (miles)': clinic.get('distance'),
                'BMI eligibility limit': None,
                'Do they do egg-freezing': None,
                'Do they do IVF': clinic.get('treatments', {}).get('ivf', False),
                'Do they do ICSI': clinic.get('treatments', {}).get('icsi', False),
                'Do they do Surgical sperm collection': clinic.get('treatments', {}).get('surgical_sperm', False),
                'Treats NHS patients': None,
                'Treats private patients': None,
                'At least one counselling session included': None,
                'Inspection rating out of 5': None,
                'Patient rating out of 5': None,
                'Number of patient ratings': None,
                'Patient empowerment rating': None,
                'Patient empathy rating': None,
                'Under 38s births per embryo transferred': None,
                'Error bars: Under 38s births per embryo transferred': None,
                'Under 38s births per egg collection': None,
                'Error bars: Under 38s births per egg collection': None,
                'Under 38s births per donor insemination treatment': None,
                'Error bars: Under 38s births per donor insemination treatment': None
            }
            if clinic_type == 'unknown':
                data['Warning'] = 'Unknown clinic type (no href, not satellite or transport)'

            all_data.append(data)
            successful += 1
            print(f"  ✓ {type_label} clinic added")
        elif clinic.get('unexpected_href'):
            print(f"[{i}/{len(clinics)}] {clinic['name']} (⚠ unexpected href: {clinic['unexpected_href']})")

            data = {
                'Name of clinic': clinic['name'],
                'Satellite of': '',
                'Distance (miles)': clinic.get('distance'),
                'Warning': f"Unexpected href format: {clinic['unexpected_href']}",
                'BMI eligibility limit': None,
                'Do they do egg-freezing': None,
                'Do they do IVF': clinic.get('treatments', {}).get('ivf', False),
                'Do they do ICSI': clinic.get('treatments', {}).get('icsi', False),
                'Do they do Surgical sperm collection': clinic.get('treatments', {}).get('surgical_sperm', False),
                'Treats NHS patients': None,
                'Treats private patients': None,
                'At least one counselling session included': None,
                'Inspection rating out of 5': None,
                'Patient rating out of 5': None,
                'Number of patient ratings': None,
                'Patient empowerment rating': None,
                'Patient empathy rating': None,
                'Under 38s births per embryo transferred': None,
                'Error bars: Under 38s births per embryo transferred': None,
                'Under 38s births per egg collection': None,
                'Error bars: Under 38s births per egg collection': None,
                'Under 38s births per donor insemination treatment': None,
                'Error bars: Under 38s births per donor insemination treatment': None
            }

            all_data.append(data)
            successful += 1
            print(f"  ⚠ Added with limited data (no detail page available)")
        else:
            # Regular clinic with detail page
            print(f"[{i}/{len(clinics)}] {clinic['name']} (ID: {clinic['clinic_id']})")

            data = scrape_clinic_detail(
                clinic['clinic_id'],
                clinic['name'],
                clinic.get('treatments', {})
            )

            if data:
                data['Satellite of'] = ''
                data['Transport for'] = ''
                data['Distance (miles)'] = clinic.get('distance')
                all_data.append(data)
                clinic_id_to_data_index[clinic['clinic_id']] = len(all_data) - 1
                successful += 1
                print(f"  ✓ Data extracted successfully")
            else:
                failed += 1
                print(f"  ✗ Failed to extract data")

        print()

    # Step 3: Overwrite distances for parent clinics already in results
    for parent_id, min_distance in parent_distance_map.items():
        if parent_id in clinic_id_to_data_index:
            idx = clinic_id_to_data_index[parent_id]
            all_data[idx]['Distance (miles)'] = min_distance

    # Step 4: Fetch parent clinics not in search results
    if missing_parent_ids:
        print("=" * 60)
        print(f"Fetching {len(missing_parent_ids)} parent clinic(s) outside search area...")
        print("=" * 60)
        print()

        for parent_id in sorted(missing_parent_ids):
            # Find parent name from satellite references
            parent_name = None
            for c in clinics:
                for p in c.get('parent_clinics', []):
                    if p.get('clinic_id') == parent_id:
                        parent_name = p['name']
                        break
                if parent_name:
                    break

            display_name = parent_name or f"Unknown (ID: {parent_id})"
            print(f"  Fetching parent: {display_name} (ID: {parent_id})")

            data = scrape_clinic_detail(parent_id, display_name, {})
            if data:
                data['Satellite of'] = ''
                data['Transport for'] = ''
                data['Distance (miles)'] = parent_distance_map.get(parent_id)
                data['Warning'] = 'Parent clinic outside search area'
                all_data.append(data)
                successful += 1
                print(f"    ✓ Added parent clinic (outside search area)")
            else:
                failed += 1
                print(f"    ✗ Failed to fetch parent clinic")

            print()

    # Summary
    total_expected = len(clinics) + len(missing_parent_ids)
    print("=" * 60)
    print("Scraping Summary:")
    print(f"  ✓ Successful: {successful}/{total_expected}")
    if failed > 0:
        print(f"  ✗ Failed: {failed}/{total_expected}")
    if missing_parent_ids:
        print(f"  Parent clinics fetched from outside search area: {len(missing_parent_ids)}")
    print("=" * 60)
    print()

    return all_data


def write_csv(data, output_path):
    """
    Write clinic data to CSV file with metadata rows.

    Args:
        data: List of clinic data dicts
        output_path: Path to output CSV file
    """
    if not data:
        print("⚠ No data to write")
        return

    # Column headers
    fieldnames = [
        'Name of clinic',
        'Satellite of',
        'Transport for',
        'Distance (miles)',
        'BMI eligibility limit',
        'Do they do egg-freezing',
        'Do they do IVF',
        'Do they do ICSI',
        'Do they do Surgical sperm collection',
        'Treats NHS patients',
        'Treats private patients',
        'At least one counselling session included',
        'Inspection rating out of 5',
        'Patient rating out of 5',
        'Number of patient ratings',
        'Patient empowerment rating',
        'Patient empathy rating',
        'Under 38s births per embryo transferred',
        'Error bars: Under 38s births per embryo transferred',
        'Under 38s births per egg collection',
        'Error bars: Under 38s births per egg collection',
        'Under 38s births per donor insemination treatment',
        'Error bars: Under 38s births per donor insemination treatment',
        'Warning'
    ]

    # Type metadata row
    types = {
        'Name of clinic': 'string',
        'Satellite of': 'string',
        'Transport for': 'string',
        'Distance (miles)': 'number',
        'Warning': 'string',
        'BMI eligibility limit': 'boolean',
        'Do they do egg-freezing': 'boolean',
        'Do they do IVF': 'boolean',
        'Do they do ICSI': 'boolean',
        'Do they do Surgical sperm collection': 'boolean',
        'Treats NHS patients': 'boolean',
        'Treats private patients': 'boolean',
        'At least one counselling session included': 'boolean',
        'Inspection rating out of 5': 'number',
        'Patient rating out of 5': 'number',
        'Number of patient ratings': 'number',
        'Patient empowerment rating': 'number',
        'Patient empathy rating': 'number',
        'Under 38s births per embryo transferred': 'percentage',
        'Error bars: Under 38s births per embryo transferred': 'percentage points',
        'Under 38s births per egg collection': 'percentage',
        'Error bars: Under 38s births per egg collection': 'percentage points',
        'Under 38s births per donor insemination treatment': 'percentage',
        'Error bars: Under 38s births per donor insemination treatment': 'percentage points'
    }

    # Where to find metadata row
    where_to_find = {
        'Name of clinic': 'h1',
        'Satellite of': 'Search results page > Satellite clinic to X',
        'Transport for': 'Search results page > Transport clinic to X',
        'Distance (miles)': 'Search results page > p.distance (for parent clinics: distance of nearest satellite)',
        'BMI eligibility limit': 'Clinic details > Eligibility > BMI limit',
        'Do they do egg-freezing': 'Clinic details > Treatments > Fertility preservation',
        'Do they do IVF': 'Search results page > Treatments offered',
        'Do they do ICSI': 'Search results page > Treatments offered',
        'Do they do Surgical sperm collection': 'Search results page > Treatments offered',
        'Treats NHS patients': 'Clinic details > Eligibility > Treats NHS patients',
        'Treats private patients': 'Clinic details > Eligibility > Treats private patients',
        'At least one counselling session included': 'Clinic details > Eligibility > Number of counselling sessions included',
        'Inspection rating out of 5': 'Ratings row',
        'Patient rating out of 5': 'Ratings row',
        'Number of patient ratings': 'Ratings row',
        'Patient empowerment rating': 'How do existing patients rate the clinic? > To what extent did you feel you understood everything that was happening throughout your treatment?',
        'Patient empathy rating': 'How do existing patients rate the clinic? > Was the level of empathy and understanding shown towards you by the clinic team?',
        'Under 38s births per embryo transferred': 'What are the clinic\'s statistics? > Births per embryo transferred – excluding donor eggs and PGT-A > .rangeChart.mean span',
        'Error bars: Under 38s births per embryo transferred': 'What are the clinic\'s statistics? > Births per embryo transferred – excluding donor eggs and PGT-A > .rangeChart.range width',
        'Under 38s births per egg collection': 'What are the clinic\'s statistics? > Births per egg collection -- excluding donor eggs, including PGT-A > .rangeChart.mean span',
        'Error bars: Under 38s births per egg collection': 'What are the clinic\'s statistics? > Births per egg collection -- excluding donor eggs, including PGT-A > .rangeChart.range width',
        'Under 38s births per donor insemination treatment': 'What are the clinic\'s statistics? > What is the clinic\'s Donor Insemination birth rate? > .rangeChart.mean span',
        'Error bars: Under 38s births per donor insemination treatment': 'What are the clinic\'s statistics? > What is the clinic\'s Donor Insemination birth rate? > .rangeChart.range width',
        'Warning': 'Scraper warnings (e.g. unexpected href format)'
    }

    try:
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)

            # Write header row with label
            header_with_label = {'Name of clinic': 'Thing of interest:'}
            header_with_label.update({field: field for field in fieldnames if field != 'Name of clinic'})
            writer.writerow(header_with_label)

            # Write type metadata row
            type_row = {'Name of clinic': 'Type:'}
            type_row.update({field: types[field] for field in fieldnames if field != 'Name of clinic'})
            writer.writerow(type_row)

            # Write where to find metadata row
            where_row = {'Name of clinic': 'Where to find it on the page:'}
            where_row.update({field: where_to_find[field] for field in fieldnames if field != 'Name of clinic'})
            writer.writerow(where_row)

            # Write data rows
            writer.writerows(data)

        print(f"✓ Data written to: {output_path}")
        print(f"  Data rows: {len(data)}")
        print(f"  Columns: {len(fieldnames)}")
        print(f"  Metadata rows: 3 (Thing of interest, Type, Where to find)")

    except Exception as e:
        print(f"✗ Error writing CSV: {e}")


def parse_args(argv=None):
    """Parse command-line arguments.

    Args:
        argv: Argument list (defaults to sys.argv[1:])

    Returns:
        Parsed argparse.Namespace
    """
    parser = argparse.ArgumentParser(
        description='Scrape HFEA clinic data from search results',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --location "E16 4JT" --distance 50
  %(prog)s --location SW1A1AA --distance 30 --output my_clinics.csv
  %(prog)s --interactive
        """
    )

    parser.add_argument(
        '--location',
        help='Postcode or place name to search from (e.g. "E16 4JT")'
    )
    parser.add_argument(
        '--distance',
        type=float,
        help='Search radius in miles (e.g. 50)'
    )
    parser.add_argument(
        '--output',
        default=DEFAULT_OUTPUT,
        help=f'Output CSV file path (default: {DEFAULT_OUTPUT})'
    )
    parser.add_argument(
        '--max-pages',
        type=int,
        default=DEFAULT_MAX_PAGES,
        help=f'Maximum number of search result pages to scrape (default: {DEFAULT_MAX_PAGES})'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable verbose debug logging'
    )
    parser.add_argument(
        '--interactive',
        action='store_true',
        help='Prompt for location and distance if not provided'
    )

    return parser.parse_args(argv)


def resolve_args(args, input_fn=None):
    """Resolve all arguments, prompting interactively for any not provided.

    Modifies args in place.

    Args:
        args: Parsed argparse.Namespace
        input_fn: Callable for reading user input (defaults to builtin input)

    Raises:
        SystemExit: If required arguments are missing and not in interactive mode,
            or if interactive input is invalid
    """
    if input_fn is None:
        input_fn = input

    if args.interactive:
        if not args.location:
            args.location = input_fn("Enter postcode or location: ")
        if args.distance is None:
            distance_str = input_fn("Enter search radius in miles: ")
            try:
                args.distance = float(distance_str)
            except (ValueError, TypeError):
                print(f"Invalid distance: {distance_str!r}")
                sys.exit(1)
        output_str = input_fn(f"Enter output file path [{args.output}]: ")
        if output_str.strip():
            args.output = output_str.strip()
        max_pages_str = input_fn(f"Enter max pages to scrape [{args.max_pages}]: ")
        if max_pages_str.strip():
            try:
                args.max_pages = int(max_pages_str)
            except ValueError:
                print(f"Invalid max pages: {max_pages_str!r}")
                sys.exit(1)
    else:
        if not args.location or args.distance is None:
            print("Error: --location and --distance are required (or use --interactive)")
            sys.exit(1)


def main(argv=None):
    """Main entry point."""
    args = parse_args(argv)
    resolve_args(args)

    search_url = build_search_url(args.location, args.distance)

    print("=" * 60)
    print("HFEA Clinic Data Scraper")
    print("=" * 60)
    print(f"  Location: {args.location}")
    print(f"  Distance: {args.distance} miles")
    print(f"  URL: {search_url}")
    print()

    # Scrape all clinics
    data = scrape_all_clinics(search_url, args.max_pages, debug=args.debug)

    if not data:
        print("✗ No data collected")
        return 1

    # Write to CSV
    write_csv(data, args.output)

    print()
    print("✓ Scraping complete!")

    return 0


if __name__ == '__main__':
    exit(main())
