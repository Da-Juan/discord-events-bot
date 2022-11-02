import argparse
import logging
import os
import pathlib
import re
import signal
import sys
import time
from enum import Enum, auto
from typing import Any

import arrow

import ics

import requests

import schedule

import tatsu

import yaml

from .discord import DiscordGuild, Event
from .utils import duration_to_seconds

DEFAULT_CHANNEL = "general"
DEFAULT_EVENT_LOCATION = "Sanata Claus Village 96930 Rovaniemi, Finland"
DEFAULT_INTERVAL = "24h"
DEFAULT_MESSAGE = "A new event was added"

DISCORD_SHORT_URL = "https://discord.gg"

ENV_PREFIX = "eventsbot_"

# We cannot access return values from a scheduled function
# The solution is to use a global variable
added_events = 0

logger = logging.getLogger()
logger.setLevel(logging.WARN)
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s %(name)s/%(module)s [%(levelname)s]: %(message)s", "%Y-%m-%d %H:%M:%S")
handler.setFormatter(formatter)
logger.addHandler(handler)


class ConfigMode(Enum):
    """Configuration modes."""

    ENV = auto()
    CLI = auto()


def get_this_week_events(url: str) -> list[ics.Event]:
    """Get events happening this week from an ICS calendar."""
    calendar = ics.Calendar(requests.get(url).text)
    now = arrow.utcnow()
    events = []
    for event in calendar.timeline.start_after(now):
        if event.begin.is_between(*now.span("week")):
            events.append(event)
    return events


def ics_to_discord(event: ics.Event, default_location: str) -> Event:
    """Convert an ICS event to Discord event."""
    location = event.location if event.location else default_location
    return Event(
        event.name,
        event.description,
        event.begin.isoformat(),
        event.end.isoformat(),
        {"location": location},
    )


def check_config(config: dict, mode: ConfigMode) -> None:
    """Validate the configuration dict."""

    mandatory_options = {"root": ["calendar_url"], "discord": ["token", "bot_url", "server_id"]}
    for key, options in mandatory_options.items():
        if key != "root" and key not in config:
            if mode == ConfigMode.CLI:
                msg = f"Missing '{key}' in configuration file."
            else:
                msg = f"Missing '{ENV_PREFIX + key}' environment variable."
            raise KeyError(msg)

        for option in options:
            search_dict = config
            if key != "root":
                search_dict = config[key]
            if option not in search_dict:
                if mode == ConfigMode.CLI:
                    msg = f"Missing '{key}.{option}' in configuration file."
                else:
                    msg = f"Missing '{ENV_PREFIX + option}' environment variable."
                raise KeyError(msg)
    optional_values = {"default_location": DEFAULT_EVENT_LOCATION, "run_interval": DEFAULT_INTERVAL}
    for key, value in optional_values.items():
        if key not in config:
            config[key] = value


def load_config(config_path: pathlib.Path) -> dict:
    """Load and validate the configuration file."""

    with open(config_path, "r", encoding="utf-8") as config_file:
        config = yaml.safe_load(config_file)

    mandatory_options = {"root": ["calendar_url"], "discord": ["token", "bot_url", "server_id"]}
    for key, options in mandatory_options.items():
        if key != "root" and key not in config:
            raise KeyError(f"Missing '{key}' in the configuration file")
        for option in options:
            search_dict = config
            if key != "root":
                search_dict = config[key]
            if option not in search_dict:
                raise KeyError(
                    f"""Missing '{option}' in {"'"+key+"' section of " if key != "root" else ""}"""
                    f"""the configuration file"""
                )
    optional_values = {"default_location": DEFAULT_EVENT_LOCATION, "run_interval": DEFAULT_INTERVAL}
    for key, value in optional_values.items():
        if key not in config:
            config[key] = value
    return config


def signal_handler(sig: int, _) -> None:
    """Handle signal for a clean exit."""
    logger.info("Recieved signal %s, exiting.", sig)
    schedule.clear()
    sys.exit()


def send_message(guild: DiscordGuild, message: dict, event_id: str) -> None:
    """Send a message to announce a new event."""

    channel = message.get("channel", DEFAULT_CHANNEL)

    content = ""
    if message.get("mention_everyone", False):
        content += "@everyone "

    content += message.get("content", DEFAULT_MESSAGE)

    if message.get("link", False):
        content += f" {DISCORD_SHORT_URL}/{guild.create_invite(channel)}?event={event_id}"

    logger.info("Sending message on channel %s.", channel)
    guild.create_message(channel, content, message.get("mention_everyone", False))


def update_events(config: dict, guild: DiscordGuild) -> None:
    """Check upcoming events and create them on Discord if needed."""

    global added_events
    added_events = 0
    try:
        events = get_this_week_events(config["calendar_url"])
    except (requests.exceptions.RequestException, tatsu.exceptions.ParseException) as exc:
        logger.error("Unable to load calendar %s\n%s", config["calendar_url"], exc)
        return

    if not events:
        logger.info("No upcoming events found this week")
        return

    logger.info("Upcoming events this week:")
    for event in events:
        logger.info("\t- %s (%s - %s)", event.name, event.begin.isoformat(), event.end.isoformat())

    for event in events:
        new_event = ics_to_discord(event, config["default_location"])
        if new_event in guild.events:
            logger.debug("Event %s (%s) already exist, skipping.", event.name, event.begin.isoformat())
            continue
        logger.info("Creating new event %s (%s) on Discord.", event.name, event.begin.isoformat())
        event_id = guild.create_event(new_event)
        added_events += 1

        message = config["discord"].get("message", {})
        if message:
            send_message(guild, message, event_id)


def run(config: dict) -> int:
    """Run the main loop."""

    guild = DiscordGuild(config["discord"]["token"], config["discord"]["bot_url"], config["discord"]["server_id"])

    schedule.every(duration_to_seconds(config["run_interval"])).seconds.do(update_events, config, guild)
    # Run the job now
    schedule.run_all()

    if config["once"]:
        schedule.clear()
        return added_events

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, signal_handler)
    while True:
        schedule.run_pending()
        time.sleep(1)

    return added_events


def get_from_env(variable: str, default: None | str = None) -> None | bool | str:
    """Check if variable exist in env then return its value."""

    if variable not in os.environ:
        return default

    value = None
    if variable in os.environ:
        value = os.environ.get(variable)
        if value is not None and re.search(r"^[Y|y]es|YES|[T|t]rue|TRUE|[O|o]n|ON|1$", value):
            return True
        elif value is not None and re.search(r"^[N|n]o|NO|[F|f]alse|FALSE|[O|o]ff|OFF|0$", value):
            return False
    return value


def setup_from_env() -> dict:
    """Setup the bot using environment variables."""

    config: dict[str, Any] = {"discord": {"message": {}}}
    root_variables = [
        ("default_location", DEFAULT_EVENT_LOCATION),
        ("calendar_url", None),
        ("run_interval", DEFAULT_INTERVAL),
    ]
    discord_variables = ["token", "bot_url", "server_id"]
    message_variables = ["content", "channel", "link", "mention_everyone"]

    for variable, default in root_variables:
        if (value := get_from_env(ENV_PREFIX + variable, default)) is not None:
            config[variable] = value

    for variable in discord_variables:
        if (value := get_from_env(ENV_PREFIX + variable)) is not None:
            config["discord"][variable] = value

    for variable in message_variables:
        if (value := get_from_env(ENV_PREFIX + variable)) is not None:
            config["discord"]["message"][variable] = value

    try:
        check_config(config, ConfigMode.ENV)
    except KeyError as exc:
        logger.error("Invalid configuration: %s", exc.args[-1])
        return {}

    return config


def setup_from_cli() -> dict:
    """Setup the bot using CLI."""

    parser = argparse.ArgumentParser()
    parser.add_argument("config", type=pathlib.Path, help="Path to YAML configuration file")
    parser.add_argument("-d", "--debug", action="store_true", help="Run in debug mode")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    parser.add_argument("-1", "--once", action="store_true", help="Run only once")

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.INFO)

    if args.debug:
        logger.setLevel(logging.DEBUG)
        logger.debug("Starting in debug mode...")

    try:
        with open(args.config, "r", encoding="utf-8") as config_file:
            config = yaml.safe_load(config_file)
        check_config(config, ConfigMode.CLI)
    except (KeyError, OSError) as exc:
        logger.error("Unable to load configuration file %s: %s", args.config, exc.args[-1])
        return {}

    config["once"] = args.once

    return config


def cli() -> None:
    """Run the bot from CLI."""
    config = setup_from_cli()
    if not config:
        sys.exit(1)
    count = run(config)
    if count == 0:
        msg = "All upcoming events already exist."
    else:
        msg = f"{count} new event{'s' if count > 1 else ''} added."
    logger.info(msg)


if __name__ == "__main__":
    cli()
