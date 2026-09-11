# MCPanel backend

## Authentication configuration

MCPanel uses a signed, seven-day HttpOnly cookie for identity. The signed payload contains the display name, normalized identity, and server-determined admin flag. It is tamper-evident but not encrypted, so no secrets are placed in it.

Install backend dependencies, then generate the admin Argon2id hash from a hidden password prompt:

```sh
cd /opt/mcpanel/backend
source .venv/bin/activate
python -c 'from argon2 import PasswordHasher; import getpass; print(PasswordHasher().hash(getpass.getpass("Admin password: ")))'
```

Generate an independent session signing secret:

```sh
python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Copy `backend/.env.example` to the deployment's ignored `backend/.env`, then replace the placeholders:

```dotenv
ADMIN_USERNAME=kenek
ADMIN_PASSWORD_HASH=<generated Argon2id hash>
SESSION_SECRET=<generated random secret>
SESSION_MAX_AGE_SECONDS=604800
SESSION_COOKIE_SECURE=false
SESSION_COOKIE_SAMESITE=lax
```

Keep the existing `RCON_HOST`, `RCON_PORT`, and `RCON_PASSWORD` values. Restart the FastAPI service after installing dependencies and updating the environment.

### Cookie settings and development origins

`SameSite=Lax` is appropriate when the frontend and API are same-site. During `astro dev`, MCPanel's development-only Vite proxy forwards same-origin browser requests from `/api` to the `PUBLIC_API_URL` homelab backend. This allows the current HTTP development topology to use an HttpOnly Lax cookie without exposing it cross-site. Keep `PUBLIC_API_URL` set to the existing Tailscale backend URL; the proxy target is read from that variable and is not hardcoded.

Static production builds use `PUBLIC_API_URL` directly. Browsers do not send Lax cookies on cross-site `fetch` requests. An HTTP frontend and HTTP API on different sites cannot provide reliable secure cookie authentication because browsers require `Secure` for `SameSite=None` cookies.

For direct cross-origin browser requests, expose both services over HTTPS and set:

```dotenv
SESSION_COOKIE_SECURE=true
SESSION_COOKIE_SAMESITE=none
```

Prefer the same-site deployment where possible. `SameSite=None` removes the cookie's built-in cross-site request protection and should be paired with explicit CSRF protection before exposing MCPanel beyond the trusted homelab/Tailscale environment.

Alternatively, serve/proxy the API from the same site as the frontend and retain `SameSite=Lax`. CORS remains restricted to the existing localhost development origins and credentials are enabled; do not use a wildcard origin with credentialed requests.

## Tests

Install development dependencies and run tests without touching the real Minecraft service:

```sh
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest -q
```

The control tests mock `minecraft_command`; they never invoke `systemctl`.
