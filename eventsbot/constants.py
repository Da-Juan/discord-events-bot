import pathlib

DEFAULT_CHANNEL = "general"
DEFAULT_EVENT_LOCATION = "Santa Claus Village 96930 Rovaniemi, Finland"
DEFAULT_INTERVAL = "24h"
DEFAULT_MESSAGE = "A new event was added"
DEFAULT_MESSAGE_HISTORY = str(pathlib.Path.home().joinpath(".eventsbot").joinpath("history"))

DISCORD_SHORT_URL = "https://discord.gg"

ENV_PREFIX = "eventsbot_"
