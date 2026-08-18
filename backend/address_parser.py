import re


def parse_address(address: str):

    if not address:
        return None

    # Keep only the street-address portion before the first comma.
    street_address = address.split(",")[0].strip().upper()

    # Remove extra spaces.
    street_address = re.sub(r"\s+", " ", street_address)

    # Remove unsupported punctuation while keeping normal address characters.
    street_address = re.sub(r"[^A-Z0-9\s\-]", "", street_address)

    parts = street_address.split()

    # We now allow addresses without a street suffix.
    # Example:
    # 14351 VISTA PANORAMA
    if len(parts) < 2:
        return None

    number = parts[0]

    if not number.isdigit():
        return None

    suffix_map = {
        "HIGHWAY": "HWY",
        "HWY": "HWY",
        "STREET": "ST",
        "ST": "ST",
        "ROAD": "RD",
        "RD": "RD",
        "AVENUE": "AVE",
        "AVE": "AVE",
        "BOULEVARD": "BLVD",
        "BLVD": "BLVD",
        "DRIVE": "DR",
        "DR": "DR",
        "COURT": "CT",
        "CT": "CT",
        "LANE": "LN",
        "LN": "LN",
        "PLACE": "PL",
        "PL": "PL",
        "PARKWAY": "PKWY",
        "PKWY": "PKWY",
        "TERRACE": "TER",
        "TER": "TER",
        "CIRCLE": "CIR",
        "CIR": "CIR",
        "WAY": "WAY",
        "TRAIL": "TRL",
        "TRL": "TRL",
        "PLAZA": "PLZ",
        "PLZ": "PLZ",
        "LOOP": "LOOP",
        "PASS": "PASS",
        "PATH": "PATH",
        "POINT": "PT",
        "PT": "PT",
        "RIDGE": "RDG",
        "RDG": "RDG",
        "VIEW": "VW",
        "VW": "VW"
    }

    raw_suffix = parts[-1]

    # If the final word is a recognized suffix, separate it.
    if raw_suffix in suffix_map:
        suffix = suffix_map[raw_suffix]
        street_parts = parts[1:-1]
    else:
        # Some valid San Diego County streets do not use a standard suffix.
        # Example: 14351 VISTA PANORAMA
        suffix = ""
        street_parts = parts[1:]

    street = " ".join(street_parts).strip()

    if not street:
        return None

    return {
        "number": number,
        "street": street,
        "suffix": suffix
    }
