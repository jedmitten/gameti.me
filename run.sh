#!/bin/bash
set -e
if [ ! -f .env ]; then
    python3 - <<'PYEOF'
import secrets, pathlib

src = pathlib.Path('.env.example').read_text()
src = src.replace('replace_with_64_char_hex_string', secrets.token_hex(32))
src = src.replace('replace_with_strong_password', secrets.token_urlsafe(20))
pathlib.Path('.env').write_text(src)
PYEOF
    echo "Created .env with generated secrets. Edit it to configure SMTP."
fi
pip install -r requirements.txt -q

HOST="${HOST:-127.0.0.1}"
if [ "${DEV:-0}" = "1" ]; then
    uvicorn backend.main:app --reload --host "$HOST" --port 8000
else
    uvicorn backend.main:app --host "$HOST" --port 8000
fi
