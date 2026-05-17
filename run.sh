#!/bin/bash
set -e
if [ ! -f .env ]; then
    SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    SITE_ADMIN_SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(20))")
    cp .env.example .env
    sed -i "s/replace_with_64_char_hex_string/$SECRET_KEY/" .env
    sed -i "s/replace_with_strong_password/$SITE_ADMIN_SECRET/" .env
    echo "Created .env with generated secrets. Edit it to configure SMTP."
fi
pip install -r requirements.txt -q
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
