#!/usr/bin/env python3
"""
Analyze satellite clinics and their parent relationships.

Reuses scraper.py's search result parsing to avoid duplicating
pagination, fetching, and clinic card extraction logic.
"""

from scraper import scrape_search_results


def categorise_clinics(clinics):
    """Categorise a list of clinic dicts from scrape_search_results by type.

    Args:
        clinics: List of clinic dicts as returned by scrape_search_results

    Returns:
        dict with keys:
            'satellites': list of satellite clinic dicts
            'transports': list of transport clinic dicts
            'unknowns': list of unknown-type clinic dicts
            'clinics': list of regular clinic dicts
            'total_cards': int
    """
    satellites = []
    transports = []
    unknowns = []
    regular = []

    for c in clinics:
        clinic_type = c.get("clinic_type", "clinic")
        if clinic_type == "satellite":
            satellites.append(c)
        elif clinic_type == "transport":
            transports.append(c)
        elif clinic_type == "unknown":
            unknowns.append(c)
        else:
            regular.append(c)

    return {
        "satellites": satellites,
        "transports": transports,
        "unknowns": unknowns,
        "clinics": regular,
        "total_cards": len(clinics),
    }


def main():
    search_url = "https://www.hfea.gov.uk/choose-a-clinic/clinic-search/results/?location=e16%204jt&distance=50"

    print("=" * 60)
    print("Clinic Analysis")
    print("=" * 60)
    print()

    # Extract all clinic info from search pages in a single pass
    print("Extracting clinic information from search pages...")
    all_clinics = scrape_search_results(search_url)
    info = categorise_clinics(all_clinics)

    satellites = info["satellites"]
    transports = info["transports"]
    unknowns = info["unknowns"]
    regular = info["clinics"]
    total_cards = info["total_cards"]

    regular_names = [c["name"] for c in regular]

    print(f"\nFound {total_cards} total clinic cards across all pages")
    print(f"  Regular clinics: {len(regular)}")
    print(f"  Satellite clinics: {len(satellites)}")
    print(f"  Transport clinics: {len(transports)}")
    if unknowns:
        print(f"  Unknown type: {len(unknowns)}")
    print()

    # Analyze satellites
    print("=" * 60)
    print("SATELLITE CLINIC ANALYSIS")
    print("=" * 60)
    print()

    satellites_with_parents_in_results = 0
    satellites_without_parents = 0

    for sat in satellites:
        print(f"Satellite: {sat['name']}")
        parents = sat.get("parent_clinics", [])

        if parents:
            print("  Parent(s):")
            has_parent_in_results = False
            for parent in parents:
                in_results = parent["name"] in regular_names
                status = "IN RESULTS" if in_results else "NOT in results"
                print(f"    - {parent['name']} ({status})")
                if in_results:
                    has_parent_in_results = True

            if has_parent_in_results:
                satellites_with_parents_in_results += 1
            else:
                satellites_without_parents += 1
        else:
            print("  No parent clinic reference found")
            satellites_without_parents += 1

        print()

    # Report transport clinics
    if transports:
        print("=" * 60)
        print("TRANSPORT CLINICS")
        print("=" * 60)
        print()

        for t in transports:
            print(f"Transport: {t['name']}")
            parents = t.get("parent_clinics", [])
            if parents:
                for parent in parents:
                    in_results = parent["name"] in regular_names
                    status = "IN RESULTS" if in_results else "NOT in results"
                    print(f"  Parent: {parent['name']} ({status})")
            print()

    # Report unknown types
    if unknowns:
        print("=" * 60)
        print("UNKNOWN CLINIC TYPES")
        print("=" * 60)
        print()

        for u in unknowns:
            print(f"Unknown: {u['name']}")
            parents = u.get("parent_clinics", [])
            if parents:
                for parent in parents:
                    print(f"  Parent: {parent['name']}")
            print()

    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total satellite clinics: {len(satellites)}")
    print(f"  Satellites with parent in results: {satellites_with_parents_in_results}")
    print(f"  Satellites without parent in results: {satellites_without_parents}")
    print(f"Total transport clinics: {len(transports)}")
    if unknowns:
        print(f"Total unknown type: {len(unknowns)}")
    print(f"\nTotal regular clinics: {len(regular)}")
    all_locations = len(regular) + len(satellites) + len(transports) + len(unknowns)
    print(f"Total unique locations: {all_locations}")
    print(f"Total clinic cards found: {total_cards}")


if __name__ == "__main__":
    main()
