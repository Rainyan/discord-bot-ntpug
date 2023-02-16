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
python -m pug
