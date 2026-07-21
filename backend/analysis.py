from models import Property


def analyze(property: Property):

    score = 5
    notes = []

    if property.zoning == "RM":
        score += 2
        notes.append("Residential multifamily zoning detected.")

    if property.lot_size_sqft:
        if property.lot_size_sqft > 10000:
            score += 2
            notes.append("Large lot size may allow greater development potential.")
        else:
            notes.append("Lot size may limit development.")

    return {
        "development_score": score,
        "notes": notes
    }