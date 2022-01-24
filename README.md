[![PEP8](https://img.shields.io/badge/code%20style-pep8-orange.svg)](https://www.python.org/dev/peps/pep-0008/)
[![MIT](https://img.shields.io/github/license/Rainyan/discord-bot-ntpug)](LICENSE)
[![CodeQL](https://github.com/Rainyan/discord-bot-ntpug/actions/workflows/codeql-analysis.yml/badge.svg)](https://github.com/Rainyan/discord-bot-ntpug/actions/workflows/codeql-analysis.yml)
[![Pylint](https://github.com/Rainyan/discord-bot-ntpug/actions/workflows/pylint.yml/badge.svg)](https://github.com/Rainyan/discord-bot-ntpug/actions/workflows/pylint.yml)

# discord-bot-ntpug
Discord PUG bot for Neotokyo!

One day speedrun project turned into something semi-reasonable.

# Installation
For running the bot, it's recommended to use the `deploy` branch.

### Remote deployment
If you want a one-click deployment, the button below generates a Heroku app for you:

[![Deploy](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/Rainyan/discord-bot-ntpug/tree/deploy)

Otherwise, please follow the manual deployment instructions below.

### Manual deployment
```sh
git clone https://github.com/Rainyan/discord-bot-ntpug
cd discord-bot-ntpug
git switch deploy
python -m pip install --upgrade pip
pip install -r requirements.txt
python bot.py  # Edit config.yml and/or set env vars as required before running
```

# Contributing
Pull requests are welcome! Please target the `main` branch for your edits.

This project complies to [PEP 8](https://www.python.org/dev/peps/pep-0008/) and [pylint defaults](https://pypi.org/project/pylint/); it's recommended to test your final code submission:
```sh
python -m pip install --upgrade pip

# Consider virtualizing the dev environment below to keep things clean.
# Eg: https://pipenv.pypa.io/en/latest/

# Code installation
pip install -r requirements.txt

# Test tools installation
pip install pylint
pip install pycodestyle

# Test
pylint bot.py
pycodestyle bot.py
```
