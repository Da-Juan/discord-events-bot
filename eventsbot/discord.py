import datetime
import json
import logging
import sys
from dataclasses import dataclass
from typing import Any

import requests

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

    name: str
    description: str
    start_time: str
    end_time: str
    metadata: dict[str, str]
    privacy_level: int = 2

    def __eq__(self, other) -> bool:    
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


def _api_request(url: str, method: str, headers: None | dict = None, data: None | str = None):
    """Manage API requests."""
    response = requests.request(method, url, headers=headers, data=data)
    logger.debug("API response code: %s", response.status_code)
    logger.debug("API response content: %s", response.content)
    response.raise_for_status()
    assert response.status_code == 200
    return response.json()


class DiscordGuild:
    """Discord guild (server) class."""

    _channels_list_ttl = 3600
    _events_list_ttl = 3600

    def __init__(self, token: str, bot_url: str, guild_id: str) -> None:
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

    def _refresh_events(self):
        """Refresh the list of guild events."""
        url = f"{self.base_api_url}/guilds/{self.guild_id}/scheduled-events"
        events = []
        for event in _api_request(url, "GET", self.headers):
            events.append(
                Event(
                    event["name"],
                    description=event["description"] if event["description"] is not None else "",
                    start_time=event["scheduled_start_time"],
                    end_time=event["scheduled_end_time"],
                    metadata=event["entity_metadata"],
                )
            )
        self._events = events
        self._events_last_pull = datetime.datetime.now().timestamp()

    def _refresh_channels(self) -> None:
        """Refresh the list of guild channels."""

        url = f"{self.base_api_url}/guilds/{self.guild_id}/channels"
        response = []
        for channel in _api_request(url, "GET", self.headers):
            response.append(Channel(channel["name"], channel["id"]))
        self._channels = response
        self._channels_last_pull = datetime.datetime.now().timestamp()

    @property
    def events(self) -> list[Event]:
        """Returns the list of guild events."""

        if datetime.datetime.now().timestamp() - self._events_last_pull > self._events_list_ttl:
            logger.info("TTL has expired, refreshing events list")
            self._refresh_events()

        return self._events

    @property
    def channels(self) -> list[Channel]:
        """Returns the list of guild channels."""

        if datetime.datetime.now().timestamp() - self._channels_last_pull > self._channels_list_ttl:
            logger.info("TTL has expired, refreshing channels list")
            self._refresh_channels()

        return self._channels

    def get_channel_id(self, name) -> str:
        """Get a channel ID from its name."""

        for channel in self.channels:
            if channel.name == name:
                return channel.channel_id

        raise DiscordGuildError(f"Channel '{name}' not found")

    def create_event(self, event: Event) -> str:
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
            }
        )

        scheduled_event = _api_request(url, "POST", self.headers, data)
        return scheduled_event["id"]

    def create_message(self, channel: str, content: str, mention_everyone: None | bool = False) -> None:
        """Create a message in a guild channel."""

        url = f"{self.base_api_url}/channels/{self.get_channel_id(channel)}/messages"
        message_data: dict[str, Any]
        message_data = {"content": content}
        if mention_everyone:
            message_data["allowed_mentions"] = {"parse": ["everyone"]}
        data = json.dumps(message_data)

        _api_request(url, "POST", self.headers, data)

    def create_invite(self, channel: str, max_age: None | int = 0) -> str:
        """Create a guild invite code."""

        url = f"{self.base_api_url}/channels/{self.get_channel_id(channel)}/invites"
        data = json.dumps({"max_age": max_age})

        invite = _api_request(url, "POST", self.headers, data)
        return invite["code"]
