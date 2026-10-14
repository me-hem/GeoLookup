"""Location and weather lookups. No API keys."""

from __future__ import annotations

from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import requests

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
IP_TIMEOUT = 6

WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Rime fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    56: "Light freezing drizzle",
    57: "Freezing drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Freezing rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Light rain showers",
    81: "Rain showers",
    82: "Heavy rain showers",
    85: "Light snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Thunderstorm with heavy hail",
}

COMPASS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


class GeoLookupError(Exception):
    """A location or weather request failed in a way the user can act on."""


@dataclass(frozen=True)
class Place:
    name: str
    region: str
    country: str
    latitude: float
    longitude: float
    source: str

    @property
    def label(self) -> str:
        parts = [self.name, self.region, self.country]
        return ", ".join(part for part in parts if part)


@dataclass(frozen=True)
class DayForecast:
    date: str
    high_c: float
    low_c: float
    precipitation_mm: float
    description: str


@dataclass(frozen=True)
class Weather:
    description: str
    temperature_c: float
    feels_like_c: float
    humidity: int
    wind_kmh: float
    wind_direction: str
    days: tuple[DayForecast, ...]


def compass(degrees: float) -> str:
    index = int((degrees % 360) / 45 + 0.5) % 8
    return COMPASS[index]


def describe(code: int) -> str:
    return WEATHER_CODES.get(code, f"Weather code {code}")


class Client:
    def __init__(self, timeout: float = 10) -> None:
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "GeoLookup/0.1"

    def get_json(self, url: str, params: dict | None = None) -> dict:
        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
        except requests.Timeout as exc:
            raise GeoLookupError(
                "The request timed out. Check your connection and try again."
            ) from exc
        except requests.RequestException as exc:
            raise GeoLookupError(f"Could not reach the service ({exc.__class__.__name__}).") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise GeoLookupError("The service returned a response that was not JSON.") from exc
        if not isinstance(payload, dict):
            raise GeoLookupError("The service returned an unexpected response.")
        return payload


def _ip_get(url: str, params: dict | None = None) -> dict | None:
    try:
        response = requests.get(
            url,
            params=params,
            timeout=IP_TIMEOUT,
            headers={"User-Agent": "GeoLookup/0.1"},
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _candidate(city, region, country, latitude, longitude) -> tuple | None:
    if not city or latitude is None or longitude is None:
        return None
    try:
        lat = float(latitude)
        lon = float(longitude)
    except (TypeError, ValueError):
        return None
    return (str(city).strip(), str(region or "").strip(), str(country or "").strip(), lat, lon)


def _from_ip_api() -> tuple | None:
    data = _ip_get(
        "http://ip-api.com/json/",
        {"fields": "status,country,regionName,city,lat,lon"},
    )
    if not data or data.get("status") != "success":
        return None
    return _candidate(data.get("city"), data.get("regionName"), data.get("country"), data.get("lat"), data.get("lon"))


def _from_ipwho() -> tuple | None:
    data = _ip_get("https://ipwho.is/")
    if not data or not data.get("success", False):
        return None
    return _candidate(data.get("city"), data.get("region"), data.get("country"), data.get("latitude"), data.get("longitude"))


def _from_ipapi_co() -> tuple | None:
    data = _ip_get("https://ipapi.co/json/")
    if not data or data.get("error"):
        return None
    return _candidate(
        data.get("city"),
        data.get("region"),
        data.get("country_name"),
        data.get("latitude"),
        data.get("longitude"),
    )


def _from_ipinfo() -> tuple | None:
    data = _ip_get("https://ipinfo.io/json")
    if not data or not data.get("loc"):
        return None
    try:
        latitude, longitude = str(data["loc"]).split(",", 1)
    except ValueError:
        return None
    return _candidate(data.get("city"), data.get("region"), data.get("country"), latitude, longitude)


def _from_geojs() -> tuple | None:
    data = _ip_get("https://get.geojs.io/v1/ip/geo.json")
    if not data:
        return None
    return _candidate(data.get("city"), data.get("region"), data.get("country"), data.get("latitude"), data.get("longitude"))


def locate_by_ip(client: Client) -> Place:
    """City the IP databases agree on. Used only after the CLI grants location access."""
    del client
    finders = (_from_ip_api, _from_ipwho, _from_ipapi_co, _from_ipinfo, _from_geojs)
    found: list[tuple] = []
    with ThreadPoolExecutor(max_workers=len(finders)) as pool:
        futures = [pool.submit(finder) for finder in finders]
        for future in as_completed(futures):
            try:
                item = future.result()
            except Exception:
                item = None
            if item:
                found.append(item)
    if not found:
        raise GeoLookupError("Could not detect your location from your internet connection.")

    groups: dict[str, list[tuple]] = defaultdict(list)
    for item in found:
        groups[item[0].casefold()].append(item)
    best_count = max(len(items) for items in groups.values())
    tied = [items for items in groups.values() if len(items) == best_count]
    if len(tied) == 1:
        chosen = tied[0]
    else:
        latitudes = sorted(item[3] for item in found)
        longitudes = sorted(item[4] for item in found)
        mid_lat = latitudes[len(latitudes) // 2]
        mid_lon = longitudes[len(longitudes) // 2]

        def distance(items: list[tuple]) -> float:
            lat = sum(item[3] for item in items) / len(items)
            lon = sum(item[4] for item in items) / len(items)
            return (lat - mid_lat) ** 2 + (lon - mid_lon) ** 2

        chosen = min(tied, key=distance)

    city = max({item[0] for item in chosen}, key=lambda name: sum(item[0] == name for item in chosen))
    regions = [item[1] for item in chosen if item[1]]
    region = max(set(regions), key=regions.count) if regions else ""
    countries = [item[2] for item in chosen if len(item[2]) > 2]
    if not countries:
        countries = [item[2] for item in chosen if item[2]]
    country = countries[0] if countries else ""
    return Place(
        name=city,
        region=region,
        country=country,
        latitude=sum(item[3] for item in chosen) / len(chosen),
        longitude=sum(item[4] for item in chosen) / len(chosen),
        source="ip",
    )


def fetch_weather(client: Client, place: Place, days: int = 7) -> Weather:
    data = client.get_json(
        FORECAST_URL,
        {
            "latitude": place.latitude,
            "longitude": place.longitude,
            "current": ",".join(
                [
                    "temperature_2m",
                    "relative_humidity_2m",
                    "apparent_temperature",
                    "weather_code",
                    "wind_speed_10m",
                    "wind_direction_10m",
                ]
            ),
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum",
            "timezone": "auto",
            "forecast_days": days,
        },
    )
    current = data.get("current")
    daily = data.get("daily")
    if not current or not daily:
        raise GeoLookupError("The forecast did not include current conditions.")

    days = tuple(
        DayForecast(
            date=daily["time"][index],
            high_c=float(daily["temperature_2m_max"][index]),
            low_c=float(daily["temperature_2m_min"][index]),
            precipitation_mm=float(daily["precipitation_sum"][index]),
            description=describe(int(daily["weather_code"][index])),
        )
        for index in range(len(daily["time"]))
    )
    return Weather(
        description=describe(int(current["weather_code"])),
        temperature_c=float(current["temperature_2m"]),
        feels_like_c=float(current["apparent_temperature"]),
        humidity=int(current["relative_humidity_2m"]),
        wind_kmh=float(current["wind_speed_10m"]),
        wind_direction=compass(float(current["wind_direction_10m"])),
        days=days,
    )
