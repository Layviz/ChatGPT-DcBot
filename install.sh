sudo tee -a /etc/systemd/system/ChatGPT-DcBot.service << EOF
[Unit]
After=network.target

[Service]
User=$(whoami)
Group=$(whoami)
WorkingDirectory=$(pwd)
ExecStart=/usr/bin/python -m pipenv run $(pwd)/ChatGPT-DcBot.py

[Install]
WantedBy=multi-user.target
EOF