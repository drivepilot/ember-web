# Ember Web

> [!CAUTION]
> **This project is very much a work in progress and is nowhere near working properly yet.** Expect broken features, incomplete functionality, and rough edges. Use at your own risk.

This project would not have been possible without the excellent reverse-engineering work done in [pyephember](https://github.com/ttroy50/pyephember) by [@ttroy50](https://github.com/ttroy50). The API endpoints, MQTT protocol details, and binary data encoding used here are all derived from that project's documentation and source code.

---

A web-based dashboard for controlling EPH Controls Ember heating systems from a desktop browser. Communicates with the same cloud APIs as the official iOS Ember app, giving you full control of your heating zones without needing your phone.

Built for the Ember PS (Programmer System) with GW01/GW04 gateway.

## Features

- **Zone Control** — Set target temperatures, switch modes (Off / Auto / On / Override), activate boost, and advance schedules
- **Real-time Updates** — MQTT subscription pushes changes to the browser instantly via WebSocket
- **Schedule View** — Weekly heating schedule displayed per zone with time period breakdowns
- **Multi-zone Support** — Works with multiple zones (e.g. Hot Water and Radiators)
- **Responsive UI** — Clean dashboard that works on desktop and tablet screens

## Screenshots

The dashboard displays zone cards with current/target temperature, mode controls, boost options, and the weekly schedule.

## Architecture

```
Browser (HTML/CSS/JS)
    ↕ REST + WebSocket
FastAPI Backend (Python)
    ↕ HTTPS          ↕ MQTT (TLS)
    EPH Cloud API    EPH MQTT Broker
```

- **Frontend** — Vanilla HTML/CSS/JavaScript. No build step required.
- **Backend** — Python FastAPI server that proxies requests to the EPH Controls cloud API and maintains an MQTT connection for real-time updates and commands.

## Requirements

- Python 3.13
- An EPH Controls Ember account (same credentials as the iOS/Android app)

## Setup

```bash
# Clone the repository
git clone https://github.com/drivepilot/ember-web.git
cd ember-web

# Create a virtual environment
python3.13 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt

# Run the server
uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000
```

Then open http://localhost:8000 and log in with your Ember account credentials.

## Running Tests

```bash
source venv/bin/activate
pytest
```

The test suite covers:

| File | Tests | Coverage |
|------|-------|----------|
| `test_models.py` | 18 | Pydantic model validation and serialization |
| `test_ember_client.py` | 13 | HTTP API client and zone data parsing |
| `test_mqtt_client.py` | 17 | MQTT command encoding and client behaviour |
| `test_api_routes.py` | 14 | FastAPI route integration |

## Project Structure

```
ember-web/
├── backend/
│   ├── app.py              # FastAPI server, routes, WebSocket
│   ├── ember_client.py     # HTTP client for EPH cloud API
│   ├── models.py           # Pydantic models
│   ├── mqtt_client.py      # MQTT client for real-time updates/commands
│   └── requirements.txt
├── frontend/
│   ├── css/style.css
│   ├── js/
│   │   ├── api.js          # Fetch-based API client
│   │   └── app.js          # Dashboard logic
│   ├── index.html          # Dashboard
│   └── login.html          # Login page
├── tests/
│   ├── conftest.py         # Shared fixtures
│   ├── test_api_routes.py
│   ├── test_ember_client.py
│   ├── test_models.py
│   └── test_mqtt_client.py
└── pytest.ini
```

## Known Issues

- HTTP write commands to the EPH cloud API (`setTargetTemperature`, `setModel`) return 500 errors despite correct payloads. MQTT-based commands are being used as an alternative path.
- Hot water zones may display a near-zero target temperature when the API returns minimal raw values.

## Acknowledgements

- [pyephember](https://github.com/ttroy50/pyephember) — Community-maintained Python library for the EPH Ember API, used as reference for reverse-engineering the cloud API and MQTT protocol.
- EPH Controls Ltd, Cork, Ireland — manufacturer of the Ember heating control system.

## License

This project is for personal use. The Ember API is not publicly documented; usage is based on community reverse-engineering efforts.
