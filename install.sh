#!/bin/bash
sudo tee -a /etc/systemd/system/ChatGPT-DcBot.service << EOF
[Unit]
After=network.target

[Service]
User=$(whoami)
Group=$(whoami)
WorkingDirectory=$(pwd)
ExecStart=$(pwd)/update_start_Bot.py

[Install]
WantedBy=multi-user.target
EOF