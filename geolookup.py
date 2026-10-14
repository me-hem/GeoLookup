"""GeoLookup menu. Location is detected automatically."""

from __future__ import annotations

from datetime import date

from rich import box
from rich.console import Console, Group
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table
from rich.text import Text

from core import Client, GeoLookupError, fetch_weather, locate_by_ip

console = Console()


def _day_label(iso_date: str) -> str:
    parsed = date.fromisoformat(iso_date)
    return parsed.strftime("%a %d %b")


def show_banner() -> None:
    title = Text(justify="center")
    title.append("GEO", style="bold white")
    title.append("LOOKUP", style="bold cyan")
    rule = Text("━" * 22, style="cyan", justify="center")
    tagline = Text("location, then the weather", style="dim", justify="center")
    console.print(
        Panel(
            Group(title, rule, tagline),
            box=box.DOUBLE,
            border_style="bright_cyan",
            padding=(1, 8),
        )
    )


def show_menu() -> None:
    console.print()
    console.print("[bold]1[/bold]  Today's weather")
    console.print("[bold]2[/bold]  Next 7 days")
    console.print("[bold]3[/bold]  Exit")


def show_today(place, weather) -> None:
    today = weather.days[0]
    body = (
        f"[bold]{weather.description}[/bold]\n\n"
        f"Temperature   [cyan]{weather.temperature_c:.1f}°C[/cyan]"
        f"   feels like {weather.feels_like_c:.1f}°C\n"
        f"Humidity      {weather.humidity}%\n"
        f"Wind          {weather.wind_kmh:.0f} km/h {weather.wind_direction}\n"
        f"Today         {today.low_c:.1f}°C – {today.high_c:.1f}°C"
        f"    rain {today.precipitation_mm:.1f} mm"
    )
    console.print()
    console.print(
        Panel(
            body,
            title=f"[bold]{place.label}[/bold]",
            subtitle=f"{place.latitude:.2f}, {place.longitude:.2f}",
            border_style="cyan",
        )
    )


def show_week(place, weather) -> None:
    table = Table(
        title=f"Next 7 days — {place.label}",
        box=box.SIMPLE_HEAVY,
        header_style="bold",
    )
    table.add_column("Date", style="cyan", no_wrap=True)
    table.add_column("Conditions")
    table.add_column("Low", justify="right")
    table.add_column("High", justify="right")
    table.add_column("Rain", justify="right")
    for day in weather.days:
        table.add_row(
            _day_label(day.date),
            day.description,
            f"{day.low_c:.1f}°C",
            f"{day.high_c:.1f}°C",
            f"{day.precipitation_mm:.1f} mm",
        )
    console.print()
    console.print(table)


def ask_location_access() -> bool:
    console.print()
    console.print(
        Panel(
            "[bold]Allow GeoLookup to access your location?[/bold]\n"
            "Used only to show the weather where you are.",
            title="Location access",
            border_style="cyan",
        )
    )
    answer = Prompt.ask("Choose", choices=["allow", "deny"])
    return answer == "allow"


def load_forecast(client: Client):
    if not ask_location_access():
        console.print("Location access denied.")
        return None
    with console.status("Finding your location..."):
        place = locate_by_ip(client)
    with console.status("Fetching the forecast..."):
        weather = fetch_weather(client, place, days=7)
    console.print(f"Using [bold]{place.label}[/bold].")
    return place, weather


def main() -> int:
    client = Client()
    place = None
    weather = None

    while True:
        console.clear()
        show_banner()
        show_menu()
        choice = Prompt.ask("Choose an option", choices=["1", "2", "3"])
        if choice == "3":
            console.print("Goodbye.")
            return 0
        if place is None or weather is None:
            try:
                loaded = load_forecast(client)
            except GeoLookupError as exc:
                console.print(f"[red]GeoLookup: {exc}[/red]")
                continue
            if loaded is None:
                continue
            place, weather = loaded
        if choice == "1":
            show_today(place, weather)
        else:
            show_week(place, weather)

        console.input("\nPress Enter to return to the menu...")


if __name__ == "__main__":
    raise SystemExit(main())
