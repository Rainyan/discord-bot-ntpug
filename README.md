[![PEP8](https://img.shields.io/badge/code%20style-pep8-orange.svg)](https://www.python.org/dev/peps/pep-0008/)
[![MIT](https://img.shields.io/github/license/Rainyan/discord-bot-ntpug)](LICENSE)
[![CodeQL](https://github.com/Rainyan/discord-bot-ntpug/actions/workflows/codeql-analysis.yml/badge.svg)](https://github.com/Rainyan/discord-bot-ntpug/actions/workflows/codeql-analysis.yml)
[![Pylint](https://github.com/Rainyan/discord-bot-ntpug/actions/workflows/pylint.yml/badge.svg)](https://github.com/Rainyan/discord-bot-ntpug/actions/workflows/pylint.yml)

# discord-bot-ntpug
Discord bot for organizing PUGs (pick-up games). Built for Neotokyo, but should work for any two-team game with even number of players total.

# Usage
### Commands
Commands are prefixed with a character defined by the config value `command_prefix`, by default `"!"`, so the command `pug` becomes `!pug` in the Discord chat, and so on.
* `ping` — Bot will simply respond with "Pong". Use to test if the bot is still online and responsive.
* `pug` — Join the PUG queue if there is room.
* `unpug` — Leave the PUG queue.
* `puggers` — List players currently in the PUG queue.
* `scramble` — Suggest randomly scrambled teams for the last full PUG for balancing reasons. Can be repeated until a satisfactory scramble is reached.
* `clearpuggers` — Empty the PUG queue. Command access can be restricted by role(s) with the config value `pug_admin_role_name`.
* `ping_puggers` — Ping all the players currently in the PUG queue. Can be used to manually organize games with smaller than expected number of players. Expects a message after the command, eg: `!ping_puggers Play 4v4?`

### Config values
The config values have been documented as comments in the [config.yml file](config.yml) itself.

# Installation
For running the bot, it's recommended to use the `deploy` branch.

### Remote deployment
If you want a one-click deployment, the button below generates a Heroku app for you:

[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/Rainyan/discord-bot-ntpug/tree/deploy)

Otherwise, please follow the manual installation instructions below.

### Manual installation
```sh
git clone https://github.com/Rainyan/discord-bot-ntpug
cd discord-bot-ntpug
git switch deploy
python -m pip install --upgrade pip

# Before continuing, consider virtualizing the
# environment below to keep things clean.
# https://pipenv.pypa.io/en/latest/

# Install requirements
pip install -r requirements.txt

# Edit config.yml and/or set env vars as required
python bot.py
```

# Troubleshooting
Check the issues to see if your problem has already been reported. If not, feel free to open a new issue.

# Contributing
Pull requests are welcome! Please target the `main` branch for your edits.

This project complies to [PEP 8](https://www.python.org/dev/peps/pep-0008/) and [pylint defaults](https://pypi.org/project/pylint/); it's recommended to test your final code submission:
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
