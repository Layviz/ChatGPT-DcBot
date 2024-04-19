#!/bin/bash
git pull
chmod +x update_start_Bot.sh
/usr/bin/python -m pipenv run python ChatGPT-DcBot.py
