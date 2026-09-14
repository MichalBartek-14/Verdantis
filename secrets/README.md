# Secrets

Local-only credentials, never committed - `secrets/*` is gitignored (this README and
`.gitkeep` are the only exceptions, so the folder itself still exists in a fresh clone).

## Live sensor API key

`ingest_sensor_data.py --client <slug>` needs an API key to pull live readings from the
field-sensor infrastructure (`config.SENSOR_API_BASE_URL` - see
`data/verdantis-sensor-infra-reference.md` §6/§10 for what's on the other end). Give it
the key one of two ways, checked in this order:

1. Environment variable - `VERDANTIS_SENSOR_API_KEY_<SLUG>` (e.g.
   `VERDANTIS_SENSOR_API_KEY_DEVINSKA`), or the generic `VERDANTIS_SENSOR_API_KEY` if
   only one client ever needs one.
2. A file here named `<slug>_sensor_api_key.txt` (e.g. `devinska_sensor_api_key.txt`),
   containing nothing but the key itself (whitespace trimmed).

If neither is set, `ingest_sensor_data.py` skips the live fetch and falls back to
parsing whatever's already sitting in `sensor_uploads/<slug>/temperature/` - it never
hard-fails just because a key isn't configured.

**If a key ever leaks into a git-tracked file or a commit message, treat it as
compromised** - ask whoever runs the sensor VPS to rotate it (`openssl rand -hex 32`,
per §10 of the infra reference doc) rather than just deleting it from history.
