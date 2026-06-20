# Pharmacy Voice Agent — Twilio Phone Calls

A voice AI agent you can **talk to over a real phone call**. It places (or receives) a Twilio call, streams the live audio to the [Deepgram Voice Agent API](https://developers.deepgram.com/docs/voice-agent), and talks back — acting as a **pharmacy assistant** that can look up drugs, place orders, and check order status by voice.

The agent's brain is a single Deepgram WebSocket that combines speech-to-text (listen), an LLM (think), tool/function calling, and text-to-speech (speak). This project bridges Twilio's phone-call audio to that API.

> This is the **telephony** sibling of the browser/Google-Meet version in [`../Exposing_the_code_as_a_api`](../Exposing_the_code_as_a_api). Same agent and tools, but the audio comes from a phone call over Twilio instead of a browser.

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Audio transport** | Twilio Programmable Voice + Media Streams (bidirectional, over WebSocket) |
| **Bridge server** | Python `websockets` (raw async WebSocket server, no web framework) |
| **Voice AI** | Deepgram Voice Agent API (`wss://agent.deepgram.com/v1/agent/converse`) |
| **STT (listen)** | Deepgram `nova-3` |
| **LLM (think)** | OpenAI `gpt-4o-mini` (configured through Deepgram) |
| **TTS (speak)** | Deepgram `aura-2-thalia-en` |
| **Phone audio codec** | μ-law (mulaw) @ 8 kHz — Twilio's telephony format |
| **Outbound calling** | Twilio REST API + TwiML (`make_call.py`) |
| **Tooling / deps** | `uv` (pyproject.toml + uv.lock), Python 3.13 |
| **Config / secrets** | `config.json`, `.env` (python-dotenv) |

---

## How It Works

A phone call's audio can't reach Deepgram directly, so this app sits in the middle as a **bridge**:

```
   📞 Phone call
        │  μ-law 8 kHz audio
        ▼
   Twilio  ──(Media Streams over WebSocket)──►  main.py  ──►  Deepgram Voice Agent API
        ▲                                       (bridge)      (listen → think → speak)
        │  agent voice (μ-law 8 kHz)                │
        │                                           │  FunctionCallRequest
        └──────────── agent audio ◄─────────────────┤
                                                     ▼
                                            pharmacy_functions.py
                                              (runs in the bridge)
```

1. **`make_call.py`** uses the Twilio REST API to dial a number. The call's TwiML tells Twilio to `<Connect><Stream>` the audio to your public WebSocket URL.
2. Twilio opens a Media Streams WebSocket to **`main.py`** and sends the caller's audio as base64 μ-law chunks.
3. `main.py` opens a WebSocket to Deepgram, sends the `Settings` message (`config.json`), then bridges audio both ways:
   - **`twilio_receiver`** decodes incoming Twilio audio, buffers it, and queues it for Deepgram.
   - **`sts_sender`** forwards that audio to Deepgram.
   - **`sts_receiver`** receives Deepgram's output: agent voice audio is re-encoded into Twilio `media` messages and sent back to the caller; JSON events are handled.
4. **Barge-in**: when Deepgram sends `UserStartedSpeaking`, the bridge sends Twilio a `clear` event to stop the agent's current playback so the caller can interrupt.
5. **Function calling**: when Deepgram sends a `FunctionCallRequest`, the bridge runs the matching pharmacy function locally and returns a `FunctionCallResponse`.

### Function calling (the "tools")
`pharmacy_functions.py` holds an in-memory drug catalog and order store, exposing three functions wired into `FUNCTION_MAP`:
- `get_drug_info(drug_name)` — price, description, default quantity
- `place_order(customer_name, drug_name)` — creates an order, returns an order ID
- `lookup_order(order_id)` — fetches an existing order

These are declared to the LLM in `config.json` (under `agent.think.functions`) and the agent calls them autonomously during the call. **Data is in-memory only — it resets on restart.**

---

## Architecture / File Map

| File | Role |
|---|---|
| [main.py](main.py) | The bridge server. Runs a raw `websockets` server on port `5000`, accepts Twilio Media Streams, connects to Deepgram, and shuttles audio + events between them. Handles barge-in and function calls. |
| [make_call.py](make_call.py) | Places an **outbound** Twilio call via the REST API and points its audio stream at your public WebSocket URL. |
| [config.json](config.json) | The Deepgram **Settings** message: μ-law/8 kHz audio formats, STT/LLM/TTS models, the system prompt, function/tool schemas, and greeting. Tune the agent's behavior here. |
| [pharmacy_functions.py](pharmacy_functions.py) | The server-side tool implementations + `FUNCTION_MAP`. |
| [pyproject.toml](pyproject.toml) / `uv.lock` | Dependencies and lockfile (managed with `uv`). |

---

## Running the Project

### Prerequisites
- **Python 3.13** (see `.python-version`) and [`uv`](https://docs.astral.sh/uv/) installed
- A **Deepgram API key** with Voice Agent access
- A **Twilio account** with a voice-capable phone number
- A way to expose your local server to the internet (e.g. **ngrok**), since Twilio must reach your WebSocket

### 1. Install dependencies
```bash
uv sync          # creates .venv and installs from uv.lock
```

### 2. Configure secrets
Create a `.env` file in this directory:
```bash
DEEPGRAM_API_KEY=your_deepgram_api_key
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_PHONE_NUMBER=+1XXXXXXXXXX      # your Twilio number (caller ID)
PUBLIC_WS_URL=wss://<your-tunnel-host>/   # public URL of the bridge (set after step 4)
```

### 3. Start the bridge server
```bash
uv run main.py
# "Started server." → listening on ws://0.0.0.0:5000
```

### 4. Expose it publicly
Twilio needs a public `wss://` URL to stream audio to your local server:
```bash
ngrok http 5000
```
Copy the forwarding host into `PUBLIC_WS_URL` in `.env` as a `wss://...` URL (e.g. `wss://abc123.ngrok.io/`).

### 5. Place a call
```bash
uv run make_call.py +15551234567
```
Twilio dials the number; once the person answers, they're talking to the pharmacy agent.

---

## Configuration Reference

### Environment variables
| Variable | Purpose |
|---|---|
| `DEEPGRAM_API_KEY` | Deepgram Voice Agent API key. |
| `TWILIO_ACCOUNT_SID` | Twilio account SID. |
| `TWILIO_AUTH_TOKEN` | Twilio auth token. |
| `TWILIO_PHONE_NUMBER` | Your Twilio number used as the caller ID. |
| `PUBLIC_WS_URL` | Public `wss://` URL of the bridge that Twilio streams audio to. |

### Customizing the agent
Edit [config.json](config.json) to change the persona, models, or tools:
- `agent.think.prompt` — the system prompt / personality.
- `agent.think.functions` — the tool schemas the LLM can call (must match `FUNCTION_MAP` in `pharmacy_functions.py`).
- `agent.listen` / `agent.speak` — STT and TTS models.
- `agent.greeting` — the agent's opening line.

> The audio encoding (`mulaw` @ 8 kHz) is fixed by Twilio's telephony format — don't change it in `config.json` or the call audio will break.

---

## Notes & Limitations
- **In-memory data**: the drug catalog and orders reset every time the server restarts.
- **Inbound calls**: `make_call.py` only places *outbound* calls. To handle *inbound* calls, point your Twilio number's Voice webhook at a TwiML response that does the same `<Connect><Stream url="...">` to `PUBLIC_WS_URL`.
- **Tunnel required**: Twilio can't reach `localhost` — the bridge must be publicly reachable (ngrok or a deployed host) for any call to work.
- **Telephony audio quality**: phone calls are 8 kHz μ-law, so audio fidelity is lower than the browser version by design.
</content>
