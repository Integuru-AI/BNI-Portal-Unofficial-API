# BNI Portal Unofficial API

Unofficial Python integrations for BNI Portal.

## Integrations

- `bni_portal_list_contacts.py` - `list_contacts`.
- `bni_portal_list_companies.py` - `list_companies`.

## Usage

Each file exposes a `run(input, context)` or `run(headers, input)` style entrypoint, matching the source integration runtime.
Authenticated request headers/cookies are expected to be supplied by the caller when required.

Install dependencies:

```bash
pip install -r requirements.txt
```

## Info

This unofficial API is built by [Integuru.ai](https://integuru.ai/).

For custom requests or hosted authentication, contact richard@taiki.online.

See the [complete list of APIs by Integuru](https://github.com/Integuru-AI/APIs-by-Integuru).
