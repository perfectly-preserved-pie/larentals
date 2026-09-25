"""Choice labels and source coverage for listing filters."""

from collections import Counter
from collections.abc import Iterable


SUBTYPE_GROUPS: dict[str, tuple[str, tuple[str, ...]]] = {
    "group:single_family": ("Single-family home", ("Single Family Residence",)),
    "group:apartment": ("Apartment / studio / loft", ("Apartment", "Studio", "Loft")),
    "group:condo": ("Condo / co-op", ("Condominium", "Stock Cooperative", "Own Your Own")),
    "group:townhouse": ("Townhouse", ("Townhouse",)),
    "group:small_multi": ("Duplex / triplex / fourplex", ("Duplex", "Triplex", "Quadplex")),
}


def build_home_type_options(values: Iterable[object]) -> list[dict[str, str]]:
    """Put useful home-type groups ahead of searchable, exact MLS labels.

    Counts describe the unfiltered source data, so renters can see which choices
    are sparse before they combine them with price or location filters. Unknown
    stays separate from every physical home-type group.

    Args:
        values: Source subtype values for the page's listings.

    Returns:
        Dropdown options with stable group and exact subtype values.
    """
    counts = Counter(
        "Unknown" if value is None or str(value).strip() in ("", "<NA>", "nan", "None")
        else str(value).strip()
        for value in values
    )
    grouped = {subtype for _, members in SUBTYPE_GROUPS.values() for subtype in members}
    options = [
        {"label": f"{label} ({sum(counts[item] for item in members):,})", "value": key}
        for key, (label, members) in SUBTYPE_GROUPS.items()
        if any(counts[item] for item in members)
    ]
    other_count = sum(count for subtype, count in counts.items() if subtype not in grouped and subtype != "Unknown")
    if other_count:
        options.append({"label": f"Other home types ({other_count:,})", "value": "group:other"})
    if counts["Unknown"]:
        options.append({"label": f"Type not specified ({counts['Unknown']:,})", "value": "Unknown"})
    options.extend(
        {"label": f"Specific: {subtype} ({count:,})", "value": subtype}
        for subtype, count in sorted(counts.items())
        if subtype != "Unknown"
    )
    return options


def pet_policy_status(raw: object) -> str:
    """Classify only an explicit permission as allowed and an explicit ban as prohibited.

    Blank, ``Call``, and restriction-only policies need confirmation. A policy
    containing both permission and a ban is ambiguous, so it stays unknown.

    Args:
        raw: Pet-policy text from an MLS listing.

    Returns:
        ``allowed``, ``prohibited``, or ``unknown``.
    """
    tokens = {token.strip().lower() for token in str(raw if raw is not None else "").split(",")}
    allowed = bool(tokens & {"yes", "cats ok", "dogs ok"})
    prohibited = bool(tokens & {"no", "none"})
    if allowed and not prohibited:
        return "allowed"
    if prohibited and not allowed:
        return "prohibited"
    return "unknown"


def build_pet_policy_options(values: Iterable[object]) -> list[dict[str, str]]:
    """Show source-wide pet-policy counts without treating missing rules as permission.

    The inclusive choice keeps possible homes in view for pet owners; its count
    combines explicit permission with listings that require a policy check.

    Args:
        values: Pet-policy fields from all lease listings.

    Returns:
        Radio choices with source-wide counts and stable filter values.
    """
    counts = Counter(pet_policy_status(value) for value in values)
    return [
        {"label": f"Any pet status ({sum(counts.values()):,})", "value": "any"},
        {"label": f"Allowed, confirmed ({counts['allowed']:,})", "value": "allowed"},
        {"label": f"Allowed or unclear ({counts['allowed'] + counts['unknown']:,})", "value": "possible"},
        {"label": f"Unclear or unlisted ({counts['unknown']:,})", "value": "unknown"},
        {"label": f"Not allowed ({counts['prohibited']:,})", "value": "prohibited"},
    ]
