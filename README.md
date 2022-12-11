# Discord events bot

This bot imports automatically events from an iCal calendar into Discord and, optionally, sends a message to inform the server's users about the event.
It also automatically deletes the messages posted about finished events.

## Pre-requisites

### Discord bot settings

* Go to Discord Developer Portal: https://discord.com/developers/
* Create an APP `events-bot`
* In this APP, create a Bot `events-bot`
* Uncheck **Public BOT**
* Click **Save**
* Then click **Reset Token** and save the token in a secure place
* Got to **OAuth2** -> **URL Generator**
* In Scopes select `bot`
* In Bot Permissions select:
  * `Create Instant Invite`
  * `Manage Events`
  * `Send Messages`
  * `Mention Everyone`
* Copy the URL at the bottom of the page
* Visit the link in your browser
* Select your server then click **Authorize**
* Keep this URL, you will need it to configure the bot script

Finally, fetch your guild ID by navigating to the server where you installed your app. Copy the first number in the URL after channels/ (for example, in the URL https://discord.com/channels/12345/678910, the guild ID would be 12345)

### Docker
You also need a way to run a Docker container see [Docker's official documentation](https://docs.docker.com/engine/install/#server)

### Calendar URL
The bot reads a calendar in iCal format, here are the steps to get the URL for a Google Calendar:

* Go to Google Calendar
* Go to **Settings** -> **Settings for my calendars**
* Click on the calendar you want to use
* Here you have 2 options, either you make a public calendar or you keep it private:
  * If you keep your calendar private :
    * Click on **Integrate calendar**
    * Copy the **Secret address in iCal format**
  * If you want to make your calendar public:
    * Click on **Access permissions for events**, check **Make available to public** and select `See all event details`
    * Then click **Integrate calendar**
    * Copy the **Public address in iCal format**

## Usage

Copy `example_config.yaml` as `config.yaml` and adapt it with your settings.  

Only on the first run, create the Docker volume and set its permissions:
```
docker run --rm --user 0 --mount type=volume,source=eventsbot,target=/home/bot/.eventsbot --entrypoint /bin/chown nrouanet/eventsbot 1000:1000 /home/bot/.eventsbot
```

Then, run the bot with Docker:

```bash
docker run -d --name eventsbot --mount type=bind,source=<absolute_path_to_config.yaml>,target=/config.yaml,readonly --mount type=volume,source=eventsbot,target=/home/bot/.eventsbot nrouanet/eventsbot
```

## References

### CLI

```
usage: eventsbot [-h] [-d] [-v] [-1] config

positional arguments:
  config         Path to YAML configuration file

options:
  -h, --help     show this help message and exit
  -d, --debug    Run in debug mode
  -v, --verbose  Verbose output
  -1, --once     Run only once
```

### Serverless function

This is an early test feature.  
`handler.handle` can be used as a serverless function, the table below shows the environment variables to set.

| Environment variable         | Corresponding YAML config          |
|------------------------------|------------------------------------|
| `eventsbot_default_location` | `default_location`                 |
| `eventsbot_calendar_url`     | `calendar_url`                     |
| `eventsbot_run_interval`     | `run_interval`                     |
| `eventsbot_history_path`     | `history_path`                     |
| `eventsbot_token`            | `discord.token`                    |
| `eventsbot_bot_url`          | `discord.bot_url`                  |
| `eventsbot_server_id`        | `discord.server_id`                |
| `eventsbot_content`          | `discord.message.content`          |
| `eventsbot_channel`          | `discord.message.channel`          |
| `eventsbot_link`             | `discord.message.link`             |
| `eventsbot_mention_everyone` | `discord.message.mention_everyone` |

The code and its dependencies need to be packaged in a zip file using the following commands:
```
mkdir package
pipenv lock -r | pip install --target package --requirement=/dev/stdin && pip install --target package .
zip -r9 eventsbot.zip handler.py package
```
