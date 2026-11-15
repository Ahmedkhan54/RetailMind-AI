"""Real geographic lookups used only to group observed data by Indian state.

The map must never invent a state or a coordinate.  A state is attached to a
row only when:

1. the mapped ``region`` value is itself a recognised state name, or
2. the mapped ``city`` value exists in the bundled gazetteer below.

Anything else stays unmatched and is reported to the user.
"""

from __future__ import annotations

from typing import Any, Iterable

import pandas as pd

# Canonical spellings exactly as they appear in public/india-states.geo.json.
INDIA_STATE_NAMES: tuple[str, ...] = (
    "Andaman and Nicobar Islands",
    "Andhra Pradesh",
    "Arunachal Pradesh",
    "Assam",
    "Bihar",
    "Chandigarh",
    "Chhattisgarh",
    "Dadra and Nagar Haveli and Daman and Diu",
    "Delhi",
    "Goa",
    "Gujarat",
    "Haryana",
    "Himachal Pradesh",
    "Jammu and Kashmir",
    "Jharkhand",
    "Karnataka",
    "Kerala",
    "Ladakh",
    "Lakshadweep",
    "Madhya Pradesh",
    "Maharashtra",
    "Manipur",
    "Meghalaya",
    "Mizoram",
    "Nagaland",
    "Odisha",
    "Puducherry",
    "Punjab",
    "Rajasthan",
    "Sikkim",
    "Tamil Nadu",
    "Telangana",
    "Tripura",
    "Uttar Pradesh",
    "Uttarakhand",
    "West Bengal",
)


def _key(value: Any) -> str:
    """Normalise a label the same way for every lookup (ASCII, single spaces)."""
    text = str(value).casefold().replace("&", " and ")
    cleaned = "".join(character if character.isalnum() else " " for character in text)
    return " ".join(cleaned.split())


_STATE_BY_KEY: dict[str, str] = {_key(name): name for name in INDIA_STATE_NAMES}

_STATE_ALIASES: dict[str, str] = {
    "orissa": "Odisha",
    "uttaranchal": "Uttarakhand",
    "pondicherry": "Puducherry",
    "j and k": "Jammu and Kashmir",
    "jammu and kashmir state": "Jammu and Kashmir",
    "ncr": "Delhi",
    "new delhi": "Delhi",
    "delhi ncr": "Delhi",
    "andaman and nicobar": "Andaman and Nicobar Islands",
    "dnh and dd": "Dadra and Nagar Haveli and Daman and Diu",
    "dadra and nagar haveli": "Dadra and Nagar Haveli and Daman and Diu",
    "daman and diu": "Dadra and Nagar Haveli and Daman and Diu",
    "dadra nagar haveli and daman diu": "Dadra and Nagar Haveli and Daman and Diu",
    "telengana": "Telangana",
    "chattisgarh": "Chhattisgarh",
    "west bengal state": "West Bengal",
    "tamilnadu": "Tamil Nadu",
    "maharasthra": "Maharashtra",
    "karanataka": "Karnataka",
}
_STATE_BY_KEY.update({key: value for key, value in _STATE_ALIASES.items()})


def resolve_state_name(value: Any) -> str | None:
    """Return the canonical state name for a *state-like* value, else ``None``.

    Sales zones such as ``West``, ``South Gujarat`` or ``Central Gujarat`` are
    deliberately not mapped: they are not states, and pretending otherwise
    would place real money on the wrong boundary.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return _STATE_BY_KEY.get(_key(value))


# City -> state.  Every entry is a real, well-known location.  Cities absent
# from this table are never guessed; they are reported as unmatched.
CITY_STATES: dict[str, str] = {
    # Gujarat
    "ahmedabad": "Gujarat", "gandhinagar": "Gujarat", "surat": "Gujarat",
    "vadodara": "Gujarat", "baroda": "Gujarat", "rajkot": "Gujarat",
    "vapi": "Gujarat", "valsad": "Gujarat", "bhavnagar": "Gujarat",
    "jamnagar": "Gujarat", "junagadh": "Gujarat", "anand": "Gujarat",
    "navsari": "Gujarat", "bharuch": "Gujarat",
    # Maharashtra
    "mumbai": "Maharashtra", "bombay": "Maharashtra", "navi mumbai": "Maharashtra",
    "thane": "Maharashtra", "pune": "Maharashtra", "poona": "Maharashtra",
    "nashik": "Maharashtra", "nagpur": "Maharashtra", "aurangabad": "Maharashtra",
    "solapur": "Maharashtra", "kolhapur": "Maharashtra",
    # Delhi NCR
    "delhi": "Delhi", "new delhi": "Delhi", "gurugram": "Haryana",
    "gurgaon": "Haryana", "noida": "Uttar Pradesh", "faridabad": "Haryana",
    "ghaziabad": "Uttar Pradesh",
    # Karnataka
    "bengaluru": "Karnataka", "bangalore": "Karnataka", "mysuru": "Karnataka",
    "mysore": "Karnataka", "mangaluru": "Karnataka", "mangalore": "Karnataka",
    "hubballi": "Karnataka", "hubli": "Karnataka", "belagavi": "Karnataka",
    # Telangana / Andhra Pradesh
    "hyderabad": "Telangana", "warangal": "Telangana",
    "visakhapatnam": "Andhra Pradesh", "vijayawada": "Andhra Pradesh",
    "guntur": "Andhra Pradesh", "nellore": "Andhra Pradesh",
    "tirupati": "Andhra Pradesh",
    # Tamil Nadu
    "chennai": "Tamil Nadu", "madras": "Tamil Nadu", "coimbatore": "Tamil Nadu",
    "madurai": "Tamil Nadu", "salem": "Tamil Nadu",
    "tiruchirappalli": "Tamil Nadu", "trichy": "Tamil Nadu",
    # Kerala
    "kochi": "Kerala", "cochin": "Kerala", "thiruvananthapuram": "Kerala",
    "trivandrum": "Kerala", "kozhikode": "Kerala", "calicut": "Kerala",
    "kollam": "Kerala", "thrissur": "Kerala",
    # West Bengal / East
    "kolkata": "West Bengal", "calcutta": "West Bengal", "howrah": "West Bengal",
    "siliguri": "West Bengal", "patna": "Bihar", "ranchi": "Jharkhand",
    "bhubaneswar": "Odisha", "cuttack": "Odisha", "guwahati": "Assam",
    "shillong": "Meghalaya", "imphal": "Manipur", "agartala": "Tripura",
    # North / Central
    "jaipur": "Rajasthan", "jodhpur": "Rajasthan", "udaipur": "Rajasthan",
    "kota": "Rajasthan", "lucknow": "Uttar Pradesh", "kanpur": "Uttar Pradesh",
    "agra": "Uttar Pradesh", "varanasi": "Uttar Pradesh", "meerut": "Uttar Pradesh",
    "prayagraj": "Uttar Pradesh", "indore": "Madhya Pradesh",
    "bhopal": "Madhya Pradesh", "jabalpur": "Madhya Pradesh",
    "gwalior": "Madhya Pradesh", "raipur": "Chhattisgarh",
    "chandigarh": "Chandigarh", "ludhiana": "Punjab", "amritsar": "Punjab",
    "jalandhar": "Punjab", "dehradun": "Uttarakhand", "shimla": "Himachal Pradesh",
    "jammu": "Jammu and Kashmir", "srinagar": "Jammu and Kashmir",
    # Goa
    "panaji": "Goa", "panjim": "Goa", "margao": "Goa", "goa": "Goa",
}

CITY_STATE_BY_KEY: dict[str, str] = {_key(city): state for city, state in CITY_STATES.items()}


def state_for_city(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return CITY_STATE_BY_KEY.get(_key(value))


def _series_map(values: Iterable[Any], resolver) -> list[str | None]:
    cache: dict[str, str | None] = {}
    result: list[str | None] = []
    for value in values:
        if value is None or (isinstance(value, float) and pd.isna(value)):
            result.append(None)
            continue
        key = _key(value)
        if key not in cache:
            cache[key] = resolver(value)
        result.append(cache[key])
    return result


def resolve_states(frame: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """Return ``(state, source)`` series aligned to ``frame``.

    ``source`` is ``"region"`` when the region value itself is a state,
    ``"city"`` when it was derived from the city gazetteer, and ``None`` when
    neither field could be matched.  No value is guessed.
    """
    index = frame.index
    region_states: list[str | None] = [None] * len(frame)
    city_states: list[str | None] = [None] * len(frame)
    if "region" in frame.columns:
        region_states = _series_map(frame["region"].tolist(), resolve_state_name)
    if "city" in frame.columns:
        city_states = _series_map(frame["city"].tolist(), state_for_city)

    states: list[str | None] = []
    sources: list[str | None] = []
    for region_state, city_state in zip(region_states, city_states):
        if region_state:
            states.append(region_state)
            sources.append("region")
        elif city_state:
            states.append(city_state)
            sources.append("city")
        else:
            states.append(None)
            sources.append(None)
    return (
        pd.Series(states, index=index, dtype="object"),
        pd.Series(sources, index=index, dtype="object"),
    )


def state_aggregate(frame: pd.DataFrame, limit: int = 60) -> list[dict[str, Any]]:
    """Aggregate observed sales/profit by resolved state.

    Returns ``[]`` when neither the region nor the city column can be mapped.
    Values are always the dataset's own sums; nothing is estimated.
    """
    if frame.empty or "sales" not in frame.columns:
        return []
    if "region" not in frame.columns and "city" not in frame.columns:
        return []
    states, sources = resolve_states(frame)
    work = pd.DataFrame(
        {
            "state": states.to_numpy(),
            "source": sources.to_numpy(),
            "sales": pd.to_numeric(frame.get("sales"), errors="coerce").to_numpy(),
            "profit": pd.to_numeric(frame.get("profit"), errors="coerce").to_numpy()
            if "profit" in frame.columns
            else [0.0] * len(frame),
        }
    ).dropna(subset=["state", "sales"])
    if work.empty:
        return []
    grouped = (
        work.groupby("state", as_index=False)
        .agg(sales=("sales", "sum"), profit=("profit", "sum"), sources=("source", lambda values: sorted({v for v in values if v})))
        .sort_values("sales", ascending=False)
        .head(limit)
    )
    rows: list[dict[str, Any]] = []
    for row in grouped.to_dict(orient="records"):
        sales = float(row["sales"])
        profit = float(row["profit"])
        rows.append(
            {
                "state": str(row["state"]),
                "sales": sales,
                "profit": profit,
                "margin": (profit / sales) if sales else None,
                "source": "+".join(row["sources"]),
            }
        )
    return rows


def state_options(frame: pd.DataFrame, limit: int = 60) -> list[str]:
    return [row["state"] for row in state_aggregate(frame, limit=limit)]


def unmatched_state_labels(frame: pd.DataFrame, limit: int = 60) -> list[dict[str, Any]]:
    """Region values that are not states, with their real observed sales."""
    if frame.empty or "region" not in frame.columns:
        return []
    raw = frame[["region", "sales"]].dropna(subset=["region"]).copy()
    raw["region"] = raw["region"].astype(str).str.strip()
    raw = raw[raw["region"] != ""]
    if raw.empty:
        return []
    totals = raw.groupby("region", as_index=False)["sales"].sum().sort_values("sales", ascending=False)
    rows: list[dict[str, Any]] = []
    for row in totals.head(limit).to_dict(orient="records"):
        if resolve_state_name(row["region"]):
            continue
        rows.append({"label": str(row["region"]), "sales": float(row["sales"])})
    return rows
