[![MIT](https://img.shields.io/github/license/Rainyan/discord-bot-ntpug)](LICENSE)
[![PEP8](https://img.shields.io/badge/code%20style-pep8-orange.svg)](https://www.python.org/dev/peps/pep-0008/)
[![CodeQL](https://github.com/Rainyan/discord-bot-ntpug/actions/workflows/codeql-analysis.yml/badge.svg)](https://github.com/Rainyan/discord-bot-ntpug/actions/workflows/codeql-analysis.yml)
[![Pylint](https://github.com/Rainyan/discord-bot-ntpug/actions/workflows/pylint.yml/badge.svg)](https://github.com/Rainyan/discord-bot-ntpug/actions/workflows/pylint.yml)
[![JSON validation](https://github.com/Rainyan/discord-bot-ntpug/actions/workflows/validate_json.yml/badge.svg)](https://github.com/Rainyan/discord-bot-ntpug/actions/workflows/validate_json.yml)
[![Docker pulls](https://img.shields.io/docker/pulls/rainrainrainrain/discord-bot-ntpug)](https://hub.docker.com/repository/docker/rainrainrainrain/discord-bot-ntpug)

# discord-bot-ntpug
Discord bot for organizing PUGs (pick-up games). Built for [Neotokyo](https://store.steampowered.com/app/244630/NEOTOKYO/), but should work for any two-team game with even number of players total.

# Usage
### Commands
Commands are prefixed with a character defined by the config value `NTBOT_CMD_PREFIX`, by default `"!"`, so the command `pug` becomes `!pug` in the Discord chat, and so on.
* `clearpuggers` — Empty the PUG queue. Command access can be restricted by role(s) with the config value `NTBOT_PUG_ADMIN_ROLES`.
* `ping` — Bot will simply respond with "Pong". Use to test if the bot is still online and responsive.
* `ping_puggers` — Ping all the players currently in the PUG queue. Can be used to manually organize games with smaller than expected number of players. Expects a message after the command, eg: `!ping_puggers Play 4v4?`
* `pug` — Join the PUG queue if there is room.
* `puggers` — List players currently in the PUG queue.
* `scramble` — Suggest randomly scrambled teams for the last full PUG for balancing reasons. Can be repeated until a satisfactory scramble is reached.
* `unpug` — Leave the PUG queue.

### Config values
The config values have been documented as comments in the [config.yml file](config.yml) itself.

# Installation
For running the bot, it's recommended to use the `main` branch.

### Deployment options
Some common deployment options listed below, for your convenience:

#### Heroku
[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/Rainyan/discord-bot-ntpug/tree/main)

Do note that [Heroku will stop offering a free hosting tier](https://help.heroku.com/RSBRUH58/removal-of-heroku-free-product-plans-faq) by Nov 28, 2022.

#### Docker image
[![Docker](https://user-images.githubusercontent.com/6595066/187285611-b90ffa3f-80d0-4716-8bbf-837be43e31b2.png)](https://hub.docker.com/repository/docker/rainrainrainrain/discord-bot-ntpug)

The Docker image linked above (`rainrainrainrain/discord-bot-ntpug:latest`) is compatible for example with the [fly.io tutorial](https://fly.io/docs/hands-on/start/), if you're looking for a place to host. Just note that you'll have to escape the string quotes for env vars inside your fly.toml as `NTBOT_SECRET_TOKEN = "\"secret here\""`, etc. More info on this quirk in the [config.yml](config.yml) comments. The same applies for env variable input for other cloud providers.

Example fly.toml file, for [fly.io](https://fly.io) deployments:
```toml
app = "discord-bot-ntpug"
kill_signal = "SIGINT"
kill_timeout = 5
processes = []

[build]
  # https://hub.docker.com/repository/docker/rainrainrainrain/discord-bot-ntpug
  image = "rainrainrainrain/discord-bot-ntpug:latest"

[env]
  # The Discord bot secret token goes here. Don't share this value with others.
  # For info on how to generate this token, please see: https://discord.com/developers/docs
  NTBOT_SECRET_TOKEN = "\"secret-token-goes-here\""
  # Name of the Discord server channel that the bot listens to.
  # This value has to be an exact match of the channel name.
  NTBOT_PUG_CHANNEL = "\"pug-queue\""
  # Number of players, total, that are required for a PUG match.
  # For example, 10 for a 5v5. Needs to be an even number.
  NTBOT_PLAYERS_REQUIRED_TOTAL = "10"
  # Name of the puggers role. Used for pinging.
  NTBOT_PUGGER_ROLE = "\"Puggers\""
  # List of 0 or more PUG queue moderator/admin roles.
  # If any user should be able to do PUG queue admin tasks, use an empty value.
  NTBOT_PUG_ADMIN_ROLES = "[\"Admins\", \"Moderators\"]"
  # Names of each team
  NTBOT_FIRST_TEAM_NAME = "\"Jinrai\""
  NTBOT_SECOND_TEAM_NAME = "\"NSF\""

[experimental]
  allowed_public_ports = []
  auto_rollback = true

[processes]
  worker = "python bot.py"
```

#### Manual installation
Option to install and run manually in your machine/VM.

```bash
#!/usr/bin/env bash

git clone https://github.com/Rainyan/discord-bot-ntpug
cd discord-bot-ntpug
python -m pip install --upgrade pip

# Before continuing, consider virtualizing the
# environment below to keep things clean.
# https://pipenv.pypa.io/en/latest/

# Install requirements
pip install -r requirements.txt

# Edit config.yml and/or set env vars as required

# Run the bot!
python bot.py
```

# Troubleshooting
Check the [issues tab](https://github.com/Rainyan/discord-bot-ntpug/issues) to see if your problem has already been reported. If not, feel free to open a new issue.

There's also a [discussions tab](https://github.com/Rainyan/discord-bot-ntpug/discussions) in the repo for more freeform questions/suggestions.

# Contributing
Pull requests are welcome! Please target the `main` branch for your edits. Also consider tagging yourself in the relevant issue ticket, or creating a new issue for your feature if it doesn't exist yet, to avoid conflicting updates.

This project complies to [PEP 8](https://www.python.org/dev/peps/pep-0008/) and [Pylint defaults](https://pypi.org/project/pylint/); it's recommended to test your final code before submission:
```sh
python -m pip install --upgrade pip

# Consider virtualizing the dev environment
# below to keep things clean.
# Eg: https://pipenv.pypa.io/en/latest/

# Install requirements
pip install -r requirements.txt

# Test tools installation (if you're using a venv,
# you may wish to also install these tools inside
# it to ensure they can see the requirements)
pip install pylint
pip install pycodestyle

# Lint the code!
pylint bot.py
pycodestyle bot.py
```
