import datetime
import json
import logging
import sys
from dataclasses import dataclass
from time import sleep
from typing import Any

import requests

from .constants import DEFAULT_TIMEOUT

DISCORD_API_URL = "https://discord.com/api/v10"

logger = logging.getLogger(__name__)


@dataclass
class Channel:
    """Discord channel."""

    name: str
    channel_id: str


@dataclass
class Event:
    """Discord event."""

    event_id: None | str
    name: str
    description: str
    start_time: str
    end_time: str
    metadata: dict[str, str]
    privacy_level: int = 2

    def __eq__(self: "Event", other: "Event") -> bool:
        if not isinstance(other, Event):
            # don't attempt to compare against unrelated types
            return NotImplemented

        return (
            self.name == other.name
            and self.start_time == other.start_time
            and self.end_time == other.end_time
            and self.metadata == other.metadata
            and self.privacy_level == other.privacy_level
        )


class DiscordGuildError(Exception):
    """Base exception class."""


# pylint: disable=too-many-arguments
def _api_request(
    url: str,
    *,
    method: str,
    headers: None | dict = None,
    data: None | str = None,
    expected_status: None | int = 200,
    error_ok: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[int, dict]:
    """Manage API requests."""
    response = requests.request(method, url, headers=headers, data=data, timeout=timeout)
    logger.debug("API response code: %s", response.status_code)
    logger.debug("API response content: %s", response.content)

    if response.status_code == 429 and "X-RateLimit-Reset-After" in response.headers:
        seconds = float(response.headers.get("X-RateLimit-Reset-After", 0))
        logger.info("Rate limiting hit, waiting for %s seconds", seconds)
        sleep(seconds)
        return _api_request(
            url,
            method=method,
            headers=headers,
            data=data,
            expected_status=expected_status,
            error_ok=error_ok,
            timeout=timeout,
        )

    if not error_ok and response.status_code != expected_status:
        logger.error("HTTPError %s: %s", response.status_code, response.reason)

    try:
        return response.status_code, response.json()
    except requests.exceptions.JSONDecodeError:
        return response.status_code, {}


class DiscordGuild:
    """Discord guild (server) class."""

    _channels_list_ttl = 3600
    _events_list_ttl = 3600

    def __init__(self: "DiscordGuild", token: str, bot_url: str, guild_id: str) -> None:
        self.base_api_url = DISCORD_API_URL
        self.guild_id = guild_id
        self.headers = {
            "Authorization": f"Bot {token}",
            "User-Agent": f"DiscordBot ({bot_url}) Python/{sys.version_info.major}.{sys.version_info.minor} "
            f"requests/{requests.__version__}",
            "Content-Type": "application/json",
        }
        self._refresh_events()
        self._refresh_channels()

    def _refresh_events(self: "DiscordGuild") -> None:
        """Refresh the list of guild events."""
        url = f"{self.base_api_url}/guilds/{self.guild_id}/scheduled-events"
        events = []
        _, response = _api_request(url, method="GET", headers=self.headers)
        for event in response:
            events.append(
                Event(
                    event["id"],
                    event["name"],
                    description=event["description"] if event["description"] is not None else "",
                    start_time=event["scheduled_start_time"],
                    end_time=event["scheduled_end_time"],
                    metadata=event["entity_metadata"],
                ),
            )
        self._events = events
        self._events_last_pull = datetime.datetime.now().timestamp()

    def _refresh_channels(self: "DiscordGuild") -> None:
        """Refresh the list of guild channels."""

        url = f"{self.base_api_url}/guilds/{self.guild_id}/channels"
        channels = []
        _, response = _api_request(url, method="GET", headers=self.headers)
        for channel in response:
            channels.append(Channel(channel["name"], channel["id"]))
        self._channels = channels
        self._channels_last_pull = datetime.datetime.now().timestamp()

    @property
    def events(self: "DiscordGuild") -> list[Event]:
        """Returns the list of guild events."""

        if datetime.datetime.now().timestamp() - self._events_last_pull > self._events_list_ttl:
            logger.debug("TTL has expired, refreshing events list.")
            self._refresh_events()

        return self._events

    @property
    def channels(self: "DiscordGuild") -> list[Channel]:
        """Returns the list of guild channels."""

        if datetime.datetime.now().timestamp() - self._channels_last_pull > self._channels_list_ttl:
            logger.debug("TTL has expired, refreshing channels list.")
            self._refresh_channels()

        return self._channels

    def event_id_exists(self: "DiscordGuild", event_id: str) -> bool:
        """Check if a given event ID exist."""

        return event_id in [event.event_id for event in self.events]

    def get_channel_id(self: "DiscordGuild", name: str) -> str:
        """Get a channel ID from its name."""

        for channel in self.channels:
            if channel.name == name:
                return channel.channel_id

        raise DiscordGuildError(f"Channel '{name}' not found")

    def create_event(self: "DiscordGuild", event: Event) -> str:
        """Creates a guild external event."""

        url = f"{self.base_api_url}/guilds/{self.guild_id}/scheduled-events"
        data = json.dumps(
            {
                "name": event.name,
                "privacy_level": event.privacy_level,
                "scheduled_start_time": event.start_time,
                "scheduled_end_time": event.end_time,
                "description": event.description,
                "entity_metadata": event.metadata,
                "entity_type": 3,
            },
        )

        _, scheduled_event = _api_request(url, method="POST", headers=self.headers, data=data)
        self._refresh_events()
        return scheduled_event.get("id", "")

    def create_message(
        self: "DiscordGuild",
        channel: str,
        content: str,
        *,
        mention_everyone: None | bool = False,
    ) -> tuple[str, str]:
        """Create a message in a guild channel."""

        url = f"{self.base_api_url}/channels/{self.get_channel_id(channel)}/messages"
        message_data: dict[str, Any]
        message_data = {"content": content}
        if mention_everyone:
            message_data["allowed_mentions"] = {"parse": ["everyone"]}
        data = json.dumps(message_data)

        _, message = _api_request(url, method="POST", headers=self.headers, data=data)
        return message["id"], message["channel_id"]

    def create_invite(self: "DiscordGuild", channel: str, max_age: None | int = 0) -> str:
        """Create a guild invite code."""

        url = f"{self.base_api_url}/channels/{self.get_channel_id(channel)}/invites"
        data = json.dumps({"max_age": max_age})

        _, invite = _api_request(url, method="POST", headers=self.headers, data=data)
        return invite["code"]

    def delete_message(self: "DiscordGuild", channel_id: str, message_id: str) -> None:
        """Delete a message in a guild channel."""

        url = f"{self.base_api_url}/channels/{channel_id}/messages/{message_id}"
        status_code, _ = _api_request(url, method="DELETE", headers=self.headers, expected_status=204, error_ok=True)
        if status_code == 204:
            logger.info("Message %s deleted", message_id)
        elif status_code == 404:
            logger.warning("Channel or message not found")
