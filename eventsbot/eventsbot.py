import argparse
import logging
import os
import pathlib
import re
import signal
import sys
import time
from datetime import datetime, timedelta
from enum import Enum, auto
from types import FrameType
from typing import Any

import icalendar

import pytz

import recurring_ical_events

import requests

import schedule

import yaml

from .constants import (
    DEFAULT_CHANNEL,
    DEFAULT_EVENT_LOCATION,
    DEFAULT_INTERVAL,
    DEFAULT_MESSAGE,
    DEFAULT_MESSAGE_HISTORY,
    DEFAULT_TIMEOUT,
    DISCORD_SHORT_URL,
    ENV_PREFIX,
)
from .discord import DiscordGuild, Event
from .history import check_history, load_history, save_history
from .utils import duration_to_seconds

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


def get_this_week_events(url: str, default_location: str) -> list[Event]:
    """Get events happening this week from an ICS calendar."""

    ical_string = requests.get(url, timeout=DEFAULT_TIMEOUT).text
    calendar = icalendar.Calendar.from_ical(ical_string)

    now = pytz.utc.localize(datetime.utcnow())
    start_date = now - timedelta(days=now.weekday())
    end_date = start_date + timedelta(days=6)

    events = []
    for event in recurring_ical_events.of(calendar).between(now, end_date):
        location = event.decoded("location") if event.decoded("location") else default_location
        events.append(
            Event(
                event_id=None,
                name=event.get("summary"),
                description=event.get("description"),
                start_time=event.decoded("dtstart").astimezone(pytz.utc).isoformat(),
                end_time=event.decoded("dtend").astimezone(pytz.utc).isoformat(),
                metadata={"location": location},
            )
        )
    return events


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

    optional_values = {
        "default_location": DEFAULT_EVENT_LOCATION,
        "run_interval": DEFAULT_INTERVAL,
        "history_path": DEFAULT_MESSAGE_HISTORY,
    }
    for key, value in optional_values.items():
        if key not in config:
            config[key] = value

    check_history(config["history_path"])


def signal_handler(sig: int, _: FrameType) -> None:
    """Handle signal for a clean exit."""

    logger.info("Recieved signal %s, exiting.", sig)
    schedule.clear()
    sys.exit()


def send_message(guild: DiscordGuild, message: dict, event_id: str) -> tuple[str, str]:
    """Send a message to announce a new event."""

    channel = message.get("channel", DEFAULT_CHANNEL)

    content = ""
    if message.get("mention_everyone", False):
        content += "@everyone "

    content += message.get("content", DEFAULT_MESSAGE)

    if message.get("link", False):
        content += f" {DISCORD_SHORT_URL}/{guild.create_invite(channel)}?event={event_id}"

    logger.info("Sending message on channel %s.", channel)
    return guild.create_message(channel, content, mention_everyone=message.get("mention_everyone", False))


def cleanup_old_messages(guild: DiscordGuild, history: list[dict[str, str]]) -> list[dict[str, str]]:
    """Delete obsolete events messages."""

    deleted_messages = []
    for message in history:
        if not guild.event_id_exists(message["event_id"]):
            guild.delete_message(message["channel_id"], message["message_id"])
            deleted_messages.append(message)

    deleted_count = len(deleted_messages)
    if deleted_count > 0:
        logger.info("%s obsolete message%s deleted", deleted_count, "s" if deleted_count > 1 else "")
    return [message for message in history if message not in deleted_messages]


def update_events(config: dict, guild: DiscordGuild) -> None:
    """Check upcoming events and create them on Discord if needed."""

    try:
        events = get_this_week_events(config["calendar_url"], config["default_location"])
    except requests.exceptions.RequestException as exc:
        logger.error("Unable to load calendar %s\n%s", config["calendar_url"], exc)
        return

    history = load_history(config["history_path"])

    if not events:
        logger.info("No upcoming events found this week")
        history = cleanup_old_messages(guild, history)
        save_history(config["history_path"], history)
        return

    logger.info("Upcoming events this week:")
    for event in events:
        logger.info("\t- %s (%s - %s)", event.name, event.start_time, event.end_time)

    sent_messages = []

    added_events = 0
    message_config = config["discord"].get("message", {})

    for event in events:
        if event in guild.events:
            logger.debug("Event %s (%s) already exist, skipping.", event.name, event.start_time)
            continue
        logger.info("Creating new event %s (%s) on Discord.", event.name, event.start_time)
        event_id = guild.create_event(event)

        if not event_id:
            logger.error("Unable to create event on Discord, skipping.")
            continue

        added_events += 1

        if message_config:
            message_id, channel_id = send_message(guild, message_config, event_id)
            sent_messages.append({"event_id": event_id, "message_id": message_id, "channel_id": channel_id})

    if added_events == 0:
        msg = "All upcoming events already exist."
    else:
        msg = f"{added_events} new event{'s' if added_events > 1 else ''} added."

    logger.info(msg)

    history += sent_messages

    history = cleanup_old_messages(guild, history)
    save_history(config["history_path"], history)


def run(config: dict) -> None:
    """Run the main loop."""

    guild = DiscordGuild(config["discord"]["token"], config["discord"]["bot_url"], config["discord"]["server_id"])

    schedule.every(duration_to_seconds(config["run_interval"])).seconds.do(update_events, config, guild)
    # Run the job now
    schedule.run_all()

    if config["once"]:
        schedule.clear()
        return

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, signal_handler)
    while True:
        schedule.run_pending()
        time.sleep(1)


def get_from_env(variable: str, default: None | str = None) -> None | bool | str:
    """Check if variable exist in env then return its value."""

    if variable not in os.environ:
        return default

    value = None
    if variable in os.environ:
        value = os.environ.get(variable)
        if value is not None and re.search(r"^[Y|y]es|YES|[T|t]rue|TRUE|[O|o]n|ON|1$", value):
            return True
        if value is not None and re.search(r"^[N|n]o|NO|[F|f]alse|FALSE|[O|o]ff|OFF|0$", value):
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

    run(config)


if __name__ == "__main__":
    cli()
