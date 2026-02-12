#!/usr/bin/env python3
"""
HTML Archiver for HFEA Clinic Pages

Fetches and saves example HTML files from HFEA website for testing and reference.
"""

import os

import requests

from scraper import HEADERS, REQUEST_TIMEOUT


def save_html_archive(url, filename, output_dir="archived_html"):
    """
    Fetch HTML from URL and save to file.

    Args:
        url: URL to fetch
        filename: Name for saved HTML file
        output_dir: Directory to save to (default: archived_html)

    Returns:
        Path to saved file
    """
    print(f"Fetching: {url}")

    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)

        # Save HTML
        filepath = os.path.join(output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(response.text)

        print(f"✓ Saved to: {filepath}")
        print(f"  Size: {len(response.text):,} characters")

        return filepath

    except requests.RequestException as e:
        print(f"✗ Error fetching {url}: {e}")
        return None


def main():
    """Archive example HTML pages for testing."""

    print("HFEA HTML Archiver")
    print("=" * 60)
    print()

    # URLs to archive — these serve as test fixtures for the test suite.
    # Run this script once to populate archived_html/ before running tests.
    urls_to_archive = [
        {
            "url": "https://www.hfea.gov.uk/choose-a-clinic/clinic-search/results/?location=e16%204jt&distance=50",
            "filename": "search_results_page1.html",
            "description": "Search results page 1 (first 10 of 88 clinics)",
        },
        {
            "url": "https://www.hfea.gov.uk/choose-a-clinic/clinic-search/results/153/",
            "filename": "clinic_detail_153.html",
            "description": "Clinic detail page - Homerton Fertility Centre (ID 153, NHS only)",
        },
        {
            "url": "https://www.hfea.gov.uk/choose-a-clinic/clinic-search/results/94/",
            "filename": "barts_detail.html",
            "description": "Clinic detail page - Barts Health Centre (ID 94, NHS + private)",
        },
    ]

    # Fetch and save each
    results = []
    for item in urls_to_archive:
        print(f"📄 {item['description']}")
        filepath = save_html_archive(item["url"], item["filename"])
        results.append({"url": item["url"], "filepath": filepath, "success": filepath is not None})
        print()

    # Summary
    print("=" * 60)
    print("Summary:")
    successful = sum(1 for r in results if r["success"])
    print(f"  ✓ Successfully archived: {successful}/{len(results)} files")

    if successful == len(results):
        print()
        print("All HTML files archived successfully!")
        print("You can now test extraction logic against these files.")
    else:
        print()
        print("Some files failed to archive. Check errors above.")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
