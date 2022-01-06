[![PEP8](https://img.shields.io/badge/code%20style-pep8-orange.svg)](https://www.python.org/dev/peps/pep-0008/)
[![MIT](https://img.shields.io/github/license/Rainyan/discord-bot-ntpug)](LICENSE)
[![CodeQL](https://github.com/Rainyan/discord-bot-ntpug/actions/workflows/codeql-analysis.yml/badge.svg)](https://github.com/Rainyan/discord-bot-ntpug/actions/workflows/codeql-analysis.yml)
[![Pylint](https://github.com/Rainyan/discord-bot-ntpug/actions/workflows/pylint.yml/badge.svg)](https://github.com/Rainyan/discord-bot-ntpug/actions/workflows/pylint.yml)

# discord-bot-ntpug
Discord PUG bot for Neotokyo!

One day speedrun project turned into something semi-reasonable.

# Installation
Recommended to use the `main` branch.
```sh
git clone https://github.com/Rainyan/discord-bot-ntpug
python -m pip install --upgrade pip
pip install -r requirements.txt
python bot.py  # Edit config.yml as required before running
```

## Contributing
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
