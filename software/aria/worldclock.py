"""«Che ora e' a Tokyo?»: l'ora in un'altra citta' o paese, con i fusi orari di sistema (zoneinfo, ora legale compresa)."""
from __future__ import annotations

import datetime as dt
import re
from zoneinfo import ZoneInfo

from . import i18n
from .textutil import normalize

# nome (senza accenti, minuscolo) -> fuso; nome da dire
ZONES: dict[str, tuple[str, str]] = {
    "tokyo": ("Asia/Tokyo", "Tokyo"), "giappone": ("Asia/Tokyo", "in Giappone"), "osaka": ("Asia/Tokyo", "Osaka"), "kyoto": ("Asia/Tokyo", "Kyoto"),
    "new york": ("America/New_York", "New York"), "nuova york": ("America/New_York", "New York"), "washington": ("America/New_York", "Washington"), "boston": ("America/New_York", "Boston"),
    "miami": ("America/New_York", "Miami"), "toronto": ("America/Toronto", "Toronto"), "chicago": ("America/Chicago", "Chicago"), "houston": ("America/Chicago", "Houston"),
    "dallas": ("America/Chicago", "Dallas"), "denver": ("America/Denver", "Denver"), "los angeles": ("America/Los_Angeles", "Los Angeles"), "san francisco": ("America/Los_Angeles", "San Francisco"),
    "seattle": ("America/Los_Angeles", "Seattle"), "las vegas": ("America/Los_Angeles", "Las Vegas"), "california": ("America/Los_Angeles", "in California"), "stati uniti": ("America/New_York", "a New York"),
    "america": ("America/New_York", "a New York"), "usa": ("America/New_York", "a New York"), "messico": ("America/Mexico_City", "in Messico"), "citta del messico": ("America/Mexico_City", "a Città del Messico"),
    "san paolo": ("America/Sao_Paulo", "San Paolo"), "brasile": ("America/Sao_Paulo", "in Brasile"), "rio de janeiro": ("America/Sao_Paulo", "Rio de Janeiro"), "buenos aires": ("America/Argentina/Buenos_Aires", "Buenos Aires"),
    "argentina": ("America/Argentina/Buenos_Aires", "in Argentina"), "lima": ("America/Lima", "Lima"), "bogota": ("America/Bogota", "Bogotà"), "cile": ("America/Santiago", "in Cile"), "santiago": ("America/Santiago", "Santiago"),
    "londra": ("Europe/London", "Londra"), "regno unito": ("Europe/London", "nel Regno Unito"), "inghilterra": ("Europe/London", "in Inghilterra"), "dublino": ("Europe/Dublin", "Dublino"), "lisbona": ("Europe/Lisbon", "Lisbona"),
    "portogallo": ("Europe/Lisbon", "in Portogallo"), "parigi": ("Europe/Paris", "Parigi"), "francia": ("Europe/Paris", "in Francia"), "madrid": ("Europe/Madrid", "Madrid"), "spagna": ("Europe/Madrid", "in Spagna"),
    "barcellona": ("Europe/Madrid", "Barcellona"), "berlino": ("Europe/Berlin", "Berlino"), "germania": ("Europe/Berlin", "in Germania"), "roma": ("Europe/Rome", "Roma"), "milano": ("Europe/Rome", "Milano"),
    "italia": ("Europe/Rome", "in Italia"), "vienna": ("Europe/Vienna", "Vienna"), "zurigo": ("Europe/Zurich", "Zurigo"), "svizzera": ("Europe/Zurich", "in Svizzera"), "amsterdam": ("Europe/Amsterdam", "Amsterdam"),
    "bruxelles": ("Europe/Brussels", "Bruxelles"), "stoccolma": ("Europe/Stockholm", "Stoccolma"), "oslo": ("Europe/Oslo", "Oslo"), "copenaghen": ("Europe/Copenhagen", "Copenaghen"), "helsinki": ("Europe/Helsinki", "Helsinki"),
    "varsavia": ("Europe/Warsaw", "Varsavia"), "praga": ("Europe/Prague", "Praga"), "budapest": ("Europe/Budapest", "Budapest"), "atene": ("Europe/Athens", "Atene"), "grecia": ("Europe/Athens", "in Grecia"),
    "istanbul": ("Europe/Istanbul", "Istanbul"), "turchia": ("Europe/Istanbul", "in Turchia"), "mosca": ("Europe/Moscow", "Mosca"), "russia": ("Europe/Moscow", "in Russia"), "kiev": ("Europe/Kyiv", "Kiev"),
    "il cairo": ("Africa/Cairo", "Il Cairo"), "cairo": ("Africa/Cairo", "Il Cairo"), "egitto": ("Africa/Cairo", "in Egitto"), "johannesburg": ("Africa/Johannesburg", "Johannesburg"), "sudafrica": ("Africa/Johannesburg", "in Sudafrica"),
    "nairobi": ("Africa/Nairobi", "Nairobi"), "lagos": ("Africa/Lagos", "Lagos"), "casablanca": ("Africa/Casablanca", "Casablanca"), "marocco": ("Africa/Casablanca", "in Marocco"),
    "dubai": ("Asia/Dubai", "Dubai"), "emirati": ("Asia/Dubai", "negli Emirati"), "tel aviv": ("Asia/Jerusalem", "Tel Aviv"), "israele": ("Asia/Jerusalem", "in Israele"), "mumbai": ("Asia/Kolkata", "Mumbai"),
    "india": ("Asia/Kolkata", "in India"), "nuova delhi": ("Asia/Kolkata", "Nuova Delhi"), "delhi": ("Asia/Kolkata", "Delhi"), "bangkok": ("Asia/Bangkok", "Bangkok"), "thailandia": ("Asia/Bangkok", "in Thailandia"),
    "singapore": ("Asia/Singapore", "Singapore"), "hong kong": ("Asia/Hong_Kong", "Hong Kong"), "pechino": ("Asia/Shanghai", "Pechino"), "shanghai": ("Asia/Shanghai", "Shanghai"), "cina": ("Asia/Shanghai", "in Cina"),
    "seul": ("Asia/Seoul", "Seul"), "corea": ("Asia/Seoul", "in Corea"), "manila": ("Asia/Manila", "Manila"), "giacarta": ("Asia/Jakarta", "Giacarta"), "indonesia": ("Asia/Jakarta", "in Indonesia"),
    "sydney": ("Australia/Sydney", "Sydney"), "melbourne": ("Australia/Melbourne", "Melbourne"), "australia": ("Australia/Sydney", "in Australia"), "perth": ("Australia/Perth", "Perth"),
    "auckland": ("Pacific/Auckland", "Auckland"), "nuova zelanda": ("Pacific/Auckland", "in Nuova Zelanda"), "honolulu": ("Pacific/Honolulu", "Honolulu"), "hawaii": ("Pacific/Honolulu", "alle Hawaii"),
    "teheran": ("Asia/Tehran", "Teheran"), "riad": ("Asia/Riyadh", "Riad"), "arabia saudita": ("Asia/Riyadh", "in Arabia Saudita"), "islamabad": ("Asia/Karachi", "Islamabad"), "karachi": ("Asia/Karachi", "Karachi"),
}
_PLACE = re.compile(r"\b(?:a|in|ad|per|di|nel|nella|nello|negli|alle|sull|su)\s+(?:la\s+|il\s+|lo\s+|l\s+|i\s+|gli\s+|le\s+)?([a-z]+(?:\s+[a-z]+){0,2})\s*$")


def find_zone(text: str) -> tuple[str, str] | None:
    """Il luogo nominato nella frase («che ora e' a New York?», «che ore sono in Giappone») -> (fuso, nome da dire), o None."""
    t = normalize(text).strip(" ?.!")
    if i18n.is_en():
        for name in sorted(ZONES_EN, key=len, reverse=True):
            if re.search(rf"\b(?:in|at|for|of)\s+(?:the\s+)?{re.escape(name)}\b", t) or t.endswith(" " + name):
                return ZONES_EN[name]
        return None
    for name in sorted(ZONES, key=len, reverse=True):
        if re.search(rf"\b(?:a|in|ad|per|di|nel|nella|nello|negli|su|sul|sulla|da)\s+(?:la\s+|il\s+|lo\s+|l\s+|i\s+|gli\s+|le\s+)?{re.escape(name)}\b", t) or t.endswith(" " + name):
            return ZONES[name]
    return None


def time_in(zone: str, now: dt.datetime | None = None) -> dt.datetime:
    base = now.astimezone() if (now and now.tzinfo) else (now or dt.datetime.now()).astimezone()
    return base.astimezone(ZoneInfo(zone))


# ---- inglese: i luoghi come li dice un anglofono (nome della frase -> (fuso, nome da dire))
_EN_PLACES = {
    "tokyo": ("Asia/Tokyo", "Tokyo"), "japan": ("Asia/Tokyo", "Japan"), "osaka": ("Asia/Tokyo", "Osaka"), "kyoto": ("Asia/Tokyo", "Kyoto"),
    "new york": ("America/New_York", "New York"), "washington": ("America/New_York", "Washington"), "boston": ("America/New_York", "Boston"), "miami": ("America/New_York", "Miami"),
    "toronto": ("America/Toronto", "Toronto"), "chicago": ("America/Chicago", "Chicago"), "houston": ("America/Chicago", "Houston"), "dallas": ("America/Chicago", "Dallas"),
    "denver": ("America/Denver", "Denver"), "los angeles": ("America/Los_Angeles", "Los Angeles"), "san francisco": ("America/Los_Angeles", "San Francisco"), "seattle": ("America/Los_Angeles", "Seattle"),
    "las vegas": ("America/Los_Angeles", "Las Vegas"), "california": ("America/Los_Angeles", "California"), "united states": ("America/New_York", "New York"), "usa": ("America/New_York", "New York"),
    "america": ("America/New_York", "New York"), "mexico": ("America/Mexico_City", "Mexico"), "mexico city": ("America/Mexico_City", "Mexico City"), "sao paulo": ("America/Sao_Paulo", "Sao Paulo"),
    "brazil": ("America/Sao_Paulo", "Brazil"), "rio de janeiro": ("America/Sao_Paulo", "Rio de Janeiro"), "buenos aires": ("America/Argentina/Buenos_Aires", "Buenos Aires"),
    "argentina": ("America/Argentina/Buenos_Aires", "Argentina"), "lima": ("America/Lima", "Lima"), "bogota": ("America/Bogota", "Bogota"), "chile": ("America/Santiago", "Chile"),
    "santiago": ("America/Santiago", "Santiago"), "london": ("Europe/London", "London"), "united kingdom": ("Europe/London", "the UK"), "uk": ("Europe/London", "the UK"), "england": ("Europe/London", "England"),
    "britain": ("Europe/London", "Britain"), "dublin": ("Europe/Dublin", "Dublin"), "ireland": ("Europe/Dublin", "Ireland"), "lisbon": ("Europe/Lisbon", "Lisbon"), "portugal": ("Europe/Lisbon", "Portugal"),
    "paris": ("Europe/Paris", "Paris"), "france": ("Europe/Paris", "France"), "madrid": ("Europe/Madrid", "Madrid"), "spain": ("Europe/Madrid", "Spain"), "barcelona": ("Europe/Madrid", "Barcelona"),
    "berlin": ("Europe/Berlin", "Berlin"), "germany": ("Europe/Berlin", "Germany"), "rome": ("Europe/Rome", "Rome"), "milan": ("Europe/Rome", "Milan"), "italy": ("Europe/Rome", "Italy"),
    "vienna": ("Europe/Vienna", "Vienna"), "zurich": ("Europe/Zurich", "Zurich"), "switzerland": ("Europe/Zurich", "Switzerland"), "amsterdam": ("Europe/Amsterdam", "Amsterdam"),
    "brussels": ("Europe/Brussels", "Brussels"), "stockholm": ("Europe/Stockholm", "Stockholm"), "oslo": ("Europe/Oslo", "Oslo"), "copenhagen": ("Europe/Copenhagen", "Copenhagen"),
    "helsinki": ("Europe/Helsinki", "Helsinki"), "warsaw": ("Europe/Warsaw", "Warsaw"), "prague": ("Europe/Prague", "Prague"), "budapest": ("Europe/Budapest", "Budapest"), "athens": ("Europe/Athens", "Athens"),
    "greece": ("Europe/Athens", "Greece"), "istanbul": ("Europe/Istanbul", "Istanbul"), "turkey": ("Europe/Istanbul", "Turkey"), "moscow": ("Europe/Moscow", "Moscow"), "russia": ("Europe/Moscow", "Russia"),
    "kyiv": ("Europe/Kyiv", "Kyiv"), "kiev": ("Europe/Kyiv", "Kyiv"), "cairo": ("Africa/Cairo", "Cairo"), "egypt": ("Africa/Cairo", "Egypt"), "johannesburg": ("Africa/Johannesburg", "Johannesburg"),
    "south africa": ("Africa/Johannesburg", "South Africa"), "nairobi": ("Africa/Nairobi", "Nairobi"), "lagos": ("Africa/Lagos", "Lagos"), "casablanca": ("Africa/Casablanca", "Casablanca"),
    "morocco": ("Africa/Casablanca", "Morocco"), "dubai": ("Asia/Dubai", "Dubai"), "uae": ("Asia/Dubai", "the UAE"), "emirates": ("Asia/Dubai", "the Emirates"), "tel aviv": ("Asia/Jerusalem", "Tel Aviv"),
    "israel": ("Asia/Jerusalem", "Israel"), "mumbai": ("Asia/Kolkata", "Mumbai"), "india": ("Asia/Kolkata", "India"), "new delhi": ("Asia/Kolkata", "New Delhi"), "delhi": ("Asia/Kolkata", "Delhi"),
    "bangkok": ("Asia/Bangkok", "Bangkok"), "thailand": ("Asia/Bangkok", "Thailand"), "singapore": ("Asia/Singapore", "Singapore"), "hong kong": ("Asia/Hong_Kong", "Hong Kong"),
    "beijing": ("Asia/Shanghai", "Beijing"), "shanghai": ("Asia/Shanghai", "Shanghai"), "china": ("Asia/Shanghai", "China"), "seoul": ("Asia/Seoul", "Seoul"), "korea": ("Asia/Seoul", "Korea"),
    "south korea": ("Asia/Seoul", "South Korea"), "manila": ("Asia/Manila", "Manila"), "jakarta": ("Asia/Jakarta", "Jakarta"), "indonesia": ("Asia/Jakarta", "Indonesia"), "sydney": ("Australia/Sydney", "Sydney"),
    "melbourne": ("Australia/Melbourne", "Melbourne"), "australia": ("Australia/Sydney", "Australia"), "perth": ("Australia/Perth", "Perth"), "auckland": ("Pacific/Auckland", "Auckland"),
    "new zealand": ("Pacific/Auckland", "New Zealand"), "honolulu": ("Pacific/Honolulu", "Honolulu"), "hawaii": ("Pacific/Honolulu", "Hawaii"), "tehran": ("Asia/Tehran", "Tehran"),
    "riyadh": ("Asia/Riyadh", "Riyadh"), "saudi arabia": ("Asia/Riyadh", "Saudi Arabia"), "islamabad": ("Asia/Karachi", "Islamabad"), "karachi": ("Asia/Karachi", "Karachi"),
}
ZONES_EN = _EN_PLACES
