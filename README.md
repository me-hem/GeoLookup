# GeoLookup

A small Python CLI that detects your location and prints the weather.

It opens with a banner and a menu. Choosing today's weather or the 7-day forecast asks in the terminal whether GeoLookup may access your location. Allow that prompt and the app looks up where you are, then asks [Open-Meteo](https://open-meteo.com/) for the forecast. Deny, or choose Exit, and nothing is looked up. You do not type a city.

No API key. Open-Meteo's free tier is for non-commercial use.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Use

```bash
python geolookup.py
```

The menu is:

1. Today's weather
2. Next 7 days
3. Exit

After you choose 1 or 2, the terminal asks you to allow or deny location access.
