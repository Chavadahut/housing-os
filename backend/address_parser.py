import re


def parse_address(address: str):

    if not address:
        return None

    # Keep only the street-address portion before the first comma.
    street_address = address.split(",")[0].strip().upper()

    # Remove extra spaces.
    street_address = re.sub(r"\s+", " ", street_address)

    parts = street_address.split()

    if len(parts) < 3:
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
        "WAY": "WAY"
    }

    raw_suffix = parts[-1]

    suffix = suffix_map.get(raw_suffix)

    if suffix is None:
        return None

    # Everything between the street number and suffix is the street name.
    # This also supports multiword streets such as "EL CAMINO REAL".
    street = " ".join(parts[1:-1])

    if not street:
        return None

    # Allow only basic address characters.
    street = re.sub(r"[^A-Z0-9\s]", "", street)

    return {
        "number": number,
        "street": street,
        "suffix": suffix
    }