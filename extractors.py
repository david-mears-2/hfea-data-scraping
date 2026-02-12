"""
Data extraction functions for HFEA clinic pages.

Each function takes a BeautifulSoup object and returns extracted data.
"""

import re
from bs4 import BeautifulSoup

# HFEA uses -900 as a placeholder for missing/insufficient data
HFEA_MISSING_DATA_PLACEHOLDER = -900.0

# Section ID for patient ratings on clinic detail pages
PATIENT_SECTION_ID = 'collapse-patient'


def safe_float(text, default=None):
    """Safely convert text to float, handling various edge cases."""
    if text is None:
        return default
    try:
        # Clean the text
        cleaned = str(text).strip().replace('%', '').replace(',', '')
        if not cleaned or cleaned.lower() in ['n/a', 'na', '', '-']:
            return default
        value = float(cleaned)
        # HFEA uses -900 as a placeholder for missing/insufficient data
        if value == HFEA_MISSING_DATA_PLACEHOLDER:
            return default
        return value
    except (ValueError, AttributeError):
        return default


def safe_int(text, default=None):
    """Safely convert text to int."""
    if text is None:
        return default
    try:
        cleaned = str(text).strip().replace(',', '')
        if not cleaned or cleaned.lower() in ['n/a', 'na', '', '-']:
            return default
        return int(cleaned)
    except (ValueError, AttributeError):
        return default


def extract_clinic_name(soup):
    """Extract clinic name from h1."""
    h1 = soup.find('h1')
    if h1:
        return h1.get_text(strip=True)
    return None


def extract_bmi_limit(soup):
    """Extract BMI eligibility limit from Clinic details > Eligibility."""
    # Find the Eligibility section by h2 heading
    eligibility_h2 = soup.find('h2', string=re.compile(r'^\s*Eligibility\s*$', re.IGNORECASE))
    if not eligibility_h2:
        return None

    # Get the parent detail div
    detail_div = eligibility_h2.find_parent('div', class_='detail')
    if not detail_div:
        return None

    # Find all li items within this section only
    all_li = detail_div.find_all('li')
    for li in all_li:
        text = li.get_text(strip=True)
        if re.search(r'BMI.*limit', text, re.IGNORECASE):
            # Check if there's a specific value mentioned
            match = re.search(r'(\d+(?:\.\d+)?)', text)
            if match:
                return safe_float(match.group(1))
            # If just "BMI limit" with no number, return True (they have a limit)
            return True
    return None


def extract_egg_freezing(soup):
    """Check if clinic offers egg-freezing (Fertility preservation)."""
    # Find the Treatments section by h2 heading
    treatments_h2 = soup.find('h2', string=re.compile(r'^\s*Treatments\s*$', re.IGNORECASE))
    if not treatments_h2:
        return False

    # Get the parent detail div
    detail_div = treatments_h2.find_parent('div', class_='detail')
    if not detail_div:
        return False

    # Find all li items within this section only
    all_li = detail_div.find_all('li')
    for li in all_li:
        if 'fertility preservation' in li.get_text().lower():
            return True
    return False


def extract_treatments_from_search_card(card_soup):
    """
    Extract treatments (IVF, ICSI, Surgical sperm collection) from search results card.

    Args:
        card_soup: BeautifulSoup of a clinic card from search results

    Returns:
        dict with treatment booleans
    """
    treatments = {
        'ivf': False,
        'icsi': False,
        'surgical_sperm': False
    }

    # Find the "Treatments offered" section
    for div in card_soup.find_all('div', class_='list'):
        h4 = div.find('h4')
        if h4 and 'treatment' in h4.get_text().lower():
            # Found treatments section
            ul = div.find('ul')
            if ul:
                treatment_items = [li.get_text(strip=True) for li in ul.find_all('li')]

                # Check for each treatment
                treatments['ivf'] = 'IVF' in treatment_items
                treatments['icsi'] = 'ICSI' in treatment_items
                treatments['surgical_sperm'] = 'Surgical sperm collection' in treatment_items
                break

    return treatments


def extract_nhs_private(soup):
    """Extract whether clinic treats NHS and/or private patients."""
    nhs = False
    private = False

    # Find the Eligibility section by h2 heading
    eligibility_h2 = soup.find('h2', string=re.compile(r'^\s*Eligibility\s*$', re.IGNORECASE))
    if eligibility_h2:
        # Get the parent detail div
        detail_div = eligibility_h2.find_parent('div', class_='detail')
        if detail_div:
            # Find all li items within this section only
            all_li = detail_div.find_all('li')
            for li in all_li:
                text = li.get_text().lower()
                if 'treats nhs patients' in text:
                    nhs = True
                if 'treats private patients' in text:
                    private = True

    return {'nhs': nhs, 'private': private}


def extract_counselling_sessions(soup):
    """Check if at least one counselling session is included."""
    # Find the Counselling and support section by h2 heading
    counselling_h2 = soup.find('h2', string=re.compile(r'^\s*Counselling and support\s*$', re.IGNORECASE))
    if not counselling_h2:
        return False

    # Get the parent detail div
    detail_div = counselling_h2.find_parent('div', class_='detail')
    if not detail_div:
        return False

    # Find all li items within this section only
    all_li = detail_div.find_all('li')
    for li in all_li:
        if 'number of counselling sessions included' in li.get_text().lower():
            return True
    return False


def extract_inspection_rating(soup):
    """Extract inspection rating out of 5."""
    # Look for the inspection section with id="collapse-inspection"
    inspection_section = soup.find('div', id='collapse-inspection')
    if inspection_section:
        # Find the .number span within the rating-container
        number_span = inspection_section.find('span', class_='number')
        if number_span:
            return safe_float(number_span.get_text(strip=True))

    # No fallback - if primary approach fails, return None
    # (Previous fallback used brittle global text search)
    return None


def extract_patient_rating(soup):
    """Extract overall patient rating out of 5."""
    # Look for the patient ratings section with id="collapse-patient"
    patient_section = soup.find('div', id=PATIENT_SECTION_ID)
    if patient_section:
        # Find the .number span within the rating-container in the intro
        panel_intro = patient_section.find('div', class_='panel-intro')
        if panel_intro:
            number_span = panel_intro.find('span', class_='number')
            if number_span:
                return safe_float(number_span.get_text(strip=True))

    # No fallback - if primary approach fails, return None
    # (Previous fallback extracted individual question rating instead of overall rating)
    return None


def extract_number_of_ratings(soup):
    """Extract number of patient ratings."""
    # Scope to patient section first
    patient_section = soup.find('div', id=PATIENT_SECTION_ID)
    if not patient_section:
        return None

    # Look specifically in panel-intro (overall rating area)
    panel_intro = patient_section.find('div', class_='panel-intro')
    if panel_intro:
        # Find all p tags and check each for the specific pattern
        for p in panel_intro.find_all('p'):
            text = p.get_text(strip=True)
            match = re.search(r'Based on (\d+)\s+rating', text, re.IGNORECASE)
            if match:
                return safe_int(match.group(1))

    return None


def extract_patient_empowerment_rating(soup):
    """
    Extract patient empowerment rating from:
    'To what extent did you feel you understood everything that was happening throughout your treatment?'
    """
    # Scope to patient section first
    patient_section = soup.find('div', id=PATIENT_SECTION_ID)
    if not patient_section:
        return None

    # Now search within section only
    question_text = patient_section.find(string=re.compile('understood everything.*happening', re.IGNORECASE))
    if question_text:
        parent = question_text.find_parent('div', class_='question')
        if parent:
            sr_only = parent.find('p', class_='sr-only')
            if sr_only:
                match = re.search(r'(\d+(?:\.\d+)?)\s*stars?', sr_only.get_text())
                if match:
                    return safe_float(match.group(1))

    return None


def extract_patient_empathy_rating(soup):
    """
    Extract patient empathy rating from:
    'Was the level of empathy and understanding shown towards you by the clinic team?'
    """
    # Scope to patient section first
    patient_section = soup.find('div', id=PATIENT_SECTION_ID)
    if not patient_section:
        return None

    # Now search within section only
    question_text = patient_section.find(string=re.compile('empathy.*understanding.*shown', re.IGNORECASE))
    if question_text:
        parent = question_text.find_parent('div', class_='question')
        if parent:
            sr_only = parent.find('p', class_='sr-only')
            if sr_only:
                match = re.search(r'(\d+(?:\.\d+)?)\s*stars?', sr_only.get_text())
                if match:
                    return safe_float(match.group(1))

    return None


def extract_birth_stats_under_38(soup):
    """
    Extract Under 38s birth statistics from HTML chart data attributes.

    Returns dict with:
        - embryo_transferred_mean: percentage
        - embryo_transferred_error: error bar width (max - min)
        - egg_collection_mean: percentage
        - egg_collection_error: error bar width
        - donor_insemination_mean: percentage
        - donor_insemination_error: error bar width
    """
    stats = {}

    # Each stat type: (input name pattern, dict key prefix)
    stat_types = [
        ('ivfembryo', 'embryo_transferred'),
        ('ivfegg', 'egg_collection'),
        ('dibirths', 'donor_insemination'),
    ]

    for input_name_pattern, key_prefix in stat_types:
        input_el = soup.find('input', attrs={'name': re.compile(input_name_pattern, re.IGNORECASE)})
        if not input_el:
            continue
        ul = input_el.find_parent('ul')
        if not ul:
            continue
        for li in ul.find_all('li'):
            label = li.find('label')
            if label and 'under 38' in li.get_text().lower():
                mean = safe_float(label.get('data-mean'))
                stats[f'{key_prefix}_mean'] = mean
                if mean is not None:
                    min_range = safe_float(label.get('data-min-range'))
                    max_range = safe_float(label.get('data-max-range'))
                    if min_range is not None and max_range is not None:
                        stats[f'{key_prefix}_error'] = max_range - min_range
                break

    return stats


def extract_all_clinic_data(detail_html, search_card_html=None):
    """
    Extract all 21 data fields from clinic detail page (and optional search card).

    Args:
        detail_html: HTML string of clinic detail page
        search_card_html: Optional HTML string of search results card

    Returns:
        dict with all 21 fields
    """
    soup = BeautifulSoup(detail_html, 'lxml')

    # Initialize with all fields
    data = {
        'Name of clinic': extract_clinic_name(soup),
        'BMI eligibility limit': extract_bmi_limit(soup),
        'Do they do egg-freezing': extract_egg_freezing(soup),
        'Do they do IVF': None,
        'Do they do ICSI': None,
        'Do they do Surgical sperm collection': None,
        'Treats NHS patients': None,
        'Treats private patients': None,
        'At least one counselling session included': extract_counselling_sessions(soup),
        'Inspection rating out of 5': extract_inspection_rating(soup),
        'Patient rating out of 5': extract_patient_rating(soup),
        'Number of patient ratings': extract_number_of_ratings(soup),
        'Patient empowerment rating': extract_patient_empowerment_rating(soup),
        'Patient empathy rating': extract_patient_empathy_rating(soup),
        'Under 38s births per embryo transferred': None,
        'Error bars: Under 38s births per embryo transferred': None,
        'Under 38s births per egg collection': None,
        'Error bars: Under 38s births per egg collection': None,
        'Under 38s births per donor insemination treatment': None,
        'Error bars: Under 38s births per donor insemination treatment': None
    }

    # Extract NHS/Private
    nhs_private = extract_nhs_private(soup)
    data['Treats NHS patients'] = nhs_private['nhs']
    data['Treats private patients'] = nhs_private['private']

    # Extract birth statistics
    birth_stats = extract_birth_stats_under_38(soup)
    data['Under 38s births per embryo transferred'] = birth_stats.get('embryo_transferred_mean')
    data['Error bars: Under 38s births per embryo transferred'] = birth_stats.get('embryo_transferred_error')
    data['Under 38s births per egg collection'] = birth_stats.get('egg_collection_mean')
    data['Error bars: Under 38s births per egg collection'] = birth_stats.get('egg_collection_error')
    data['Under 38s births per donor insemination treatment'] = birth_stats.get('donor_insemination_mean')
    data['Error bars: Under 38s births per donor insemination treatment'] = birth_stats.get('donor_insemination_error')

    # If search card HTML provided, extract treatments from there
    if search_card_html:
        card_soup = BeautifulSoup(search_card_html, 'lxml')
        treatments = extract_treatments_from_search_card(card_soup)
        data['Do they do IVF'] = treatments['ivf']
        data['Do they do ICSI'] = treatments['icsi']
        data['Do they do Surgical sperm collection'] = treatments['surgical_sperm']

    return data
