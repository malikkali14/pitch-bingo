# Pitch Bingo

Pitch Bingo turns a football match into a game you can only win by watching. A synthetic match plays out as moving dots on a pitch while a running feed explains each moment. Fans play a 5x5 bingo card: some squares close at set minutes, some open the instant something first happens, and five are written live from the match's most unusual moments. Every answer window lasts 20 seconds and faster answers score more. Normal mode teaches new fans the rules as they play; advanced mode adds xG and tactical stats, in English or French, around a favorite club and player. Six LLM agents on Microsoft Foundry models write the feed lines, live questions, explanations and recaps, coordinated by Microsoft Agent Framework workflows; code computes every answer and score, and a verifier checks every number and name before AI text reaches the screen. It runs on Azure Container Apps.

Built for the Microsoft x Premier League "Inside the Game" hackathon.

- Live demo: https://pitchbingo.kindsand-e4fe2d42.eastus.azurecontainerapps.io
- Video: VIDEO_LINK_HERE

The live app scales to zero when idle, so the first visit after a quiet spell takes a few seconds to start.

## The problem

Casual and new fans drift during quiet stretches of a match and often don't understand the calls they see. Pitch Bingo gives them a reason to watch every minute, and explains what happened once they have answered.

## How to play

- Pick a mode (normal or advanced), an optional favorite club and focus player, and a language, then kick off.
- Deadline squares (clock icon) open at their minute, for example "How many corners by 30'?". First-to-happen squares (lightning icon), for example "Who commits the first foul?", open silently the moment the event happens; answering before it happens counts as wrong.
- Every window lasts 20 seconds of real time at any replay speed. One answer per square; answers within 3 seconds earn full points, falling to 30% at 20 seconds.
- Five live squares land in the dashed blanks during the match. A live square answered correctly becomes a wildcard you can drag (or move with the keyboard) onto a waiting square to complete a line.
- Five correct squares in a row, column or diagonal score a line; a scored line freezes. You play against 20 simulated fans on a leaderboard for your mode.

## How it works

### The five stages

| Stage | What it does | Where |
| --- | --- | --- |
| Ingest | Replays a seeded synthetic match (events plus 10 Hz player tracking) at 1x, 5x or 10x through one `EventSource` interface | `backend/app/engine/` |
| Interpret | Running stats, pass difficulty, xG, control vs. chaos, pressure, rhythm, momentum, milestones and a significance score per event | `backend/app/stats/` |
| Explain | Template lines at once, then AI lines from the narrator, rules tutor and recap agents, checked by the verifier | `backend/app/agents/`, `backend/app/verify/` |
| Render | One WebSocket per viewer: frames, events, stats, card updates, feed lines. React and SVG in the browser | `backend/app/session.py`, `frontend/src/` |
| Personalize | Mode, favorite club, focus player, language (English or French), units and "my metric" change the card, the feed and the recaps | `backend/app/agents/personalizer.py`, `backend/app/game/` |

### Code vs. LLM

Nothing that affects a viewer's score waits on an LLM.

| Component | Built with | Produces |
| --- | --- | --- |
| Match engine, stats engine | Code | Events, frames, stats, patterns, significance |
| Card builder, scorekeeper, masks | Code | The card, windows, correct answers, points, lines, hidden stats and held-back feed lines |
| Live-square producer | Code | Which five moments become live squares, and their correct answers |
| Strategist optimizer | Code | Monte Carlo over 2,000 simulated endings to pick moves for blanks and wildcards |
| Simulated fans | Code | 20 fans per mode for the leaderboard |
| Verifier | Code | Pass or a list of errors for every piece of AI text |
| Narrator | LLM | A language-neutral insight for each moment with significance 40 or more, or a pattern trigger |
| Personalizer | LLM | The final feed line for the viewer's mode, club, focus player, language, units and metric |
| Square writer | LLM | Wording and option labels for the five live squares (never the answer) |
| Strategist reason | LLM | One line on why the optimizer's move helps |
| Rules tutor | LLM | One or two lines explaining a call when a window closes (normal mode), and definitions of tapped stats |
| Recap | LLM | Half-time, full-time and catch-up recaps |

In advanced mode the narrator's voice explains the moment behind a closed window instead of the rules tutor.

### The four workflows

Each is a Microsoft Agent Framework workflow built with `WorkflowBuilder`, with code steps as `Executor` subclasses (`backend/app/agents/workflows.py`):

```text
Moment        Router -> Narrator -> Verifier -> Personalizer -> Publisher
              Router -> Square writer -> Verifier -> Publisher        (live squares)
Window close  Scorekeeper result -> Rules tutor (normal) or Narrator context (advanced)
              -> Verifier -> Personalizer -> Publisher
Strategy      Optimizer -> Strategist reason -> Publisher
Recap         State summary -> Recap -> Verifier -> Personalizer -> Publisher
```

The Publisher writes to the viewer's session, which pushes WebSocket messages. Each run sits inside a `producer.route` OpenTelemetry span and writes one JSON log line (agent, AI or fallback, latency, moment id; never prompts or replies).

### The verifier

Every AI output is checked against that agent's input before it is shown (`backend/app/verify/verifier.py`):

- Numbers: every number in the text must match one in the input. Counts and minutes exactly, percentages to 1 point, values under 1 (xG) to 0.01, other measures to 0.5. "0.15" and "0,15" read the same.
- Names: every player or club named must be in the match and in the moment; a capitalised word that is neither a known name nor an ordinary word counts as an invented name.
- Timing: words such as "half-time", "late on" or "early" (and their French equivalents) must fit the moment's clock.
- Length limits by mode (140 characters in normal mode, 220 in advanced) and a blocklist of betting words in English and French.
- Live squares: unique options from the template's set, exactly one equal to the answer computed by code, and a question that doesn't give the answer away.

On a failure the agent retries once with the error list added to the prompt. Agent output also has to match a strict JSON schema.

### Fallbacks, timeouts and the circuit breaker

- A template line always posts first; the AI version replaces it in place when it passes the verifier.
- Every call has a timeout per attempt: narrator 3 s, personalizer 2 s, square writer 2 s, strategist, rules tutor and definitions 3 s, recap 20 s. These were set from measured calls against the real endpoint.
- A second verifier failure, a timeout or an error keeps the template. French viewers keep the French template; they never fall back to English.
- Circuit breaker per agent: three failures in 60 seconds send that agent's work to its fallback for 60 seconds, then one trial call decides whether it has recovered.
- The dev panel has a failure switch that forces the narrator's breaker open, to show the feed carrying on with template lines. It also shows per-agent latency, calls per minute, AI vs. fallback counts and breaker state.
- With no Foundry endpoint configured, every agent uses its fallback and the game plays the same with template text.

## Microsoft technologies

| Product | How it is used |
| --- | --- |
| Microsoft Foundry | One Foundry resource and project with two model deployments: `gpt-4.1-mini` for the narrator, personalizer, square writer, strategist and rules tutor, and `gpt-5-mini` for recaps. Agents request strict structured outputs (JSON schema). |
| Microsoft Agent Framework | `FoundryChatClient` per deployment, one `Agent` per agent role, the four workflows built with `WorkflowBuilder` and `Executor` steps, and Agent Framework's OpenTelemetry instrumentation behind `ENABLE_INSTRUMENTATION`. Package versions are pinned to those tested. |
| Azure Container Apps | One container serves the FastAPI backend, the WebSocket and the built React frontend. External HTTPS ingress, 0.5 CPU and 1 GiB, minimum 0 and maximum 1 replica. Sessions live in memory, so it never runs more than one replica. |
| Managed identity | The container app has a system-assigned managed identity with the Foundry User role on the Foundry resource. The backend authenticates to Foundry with `DefaultAzureCredential` (managed identity in Azure, `az login` locally), so there are no Foundry API keys anywhere: not in the code, the repo or the app's settings. The only stored credential is the registry pull password that `az containerapp up` keeps as a Container Apps secret. |
| Azure Container Registry | Basic SKU, holds the image. |
| Log Analytics | Collects the container's console logs, including the per-moment JSON lines. |

Cosmos DB and Application Insights are not used in this deployment. Sessions and the leaderboard are in memory (`STORAGE=memory`). The telemetry code exports to Application Insights when `APPLICATIONINSIGHTS_CONNECTION_STRING` is set, but the live app doesn't set it.

## Synthetic data

All match data is synthetic and every club, player, referee and fan name is invented. A seeded Python generator (`backend/app/generator/`) produces each match from scratch, with no LLM: metadata, an event log of about 2,000 events and 10 Hz tracking for 22 players and the ball. The same seed always gives byte-identical files. Four matches ship in `data/matches/` (seeds 2610, 1107, 4242 and 9001; 2610 is the demo), each with five planted unusual moments, one per live-square segment.

- Schemas: `schemas/match.schema.json`, `schemas/event.schema.json`, described in `docs/schema.md`.
- Movement: players move toward ball-shifted formation spots with capped speed and acceleration, receivers run onto passes, and every event's position is rewritten to the acting player's tracked position, so events and tracking agree within 0.5 m.
- Validation: `python -m app.generator.validate --seeds 50 --chart docs/validation.png` checks that the means over 50 seeds sit inside realistic ranges (passes, shots, goals, xG, fouls, cards, corners, offsides, possession, ball in play, distance covered, top speed). The chart is in `docs/validation.png`.

## Match intelligence

Implemented in `backend/app/stats/`; the formulas are in `docs/SPEC.md` section 7.

- Possession as the share of in-play time on the ball; pass accuracy; shots and shots on target.
- Pass difficulty from a completion model (length, pressure, opponents bypassed, pass type and height); xG from shot distance and angle, header, assisted chance and pressure.
- Control vs. chaos (0 to 100) from possession changes, duels, pass completion and how often moves reach five passes, calibrated on generated matches; pressure as PPDA and field tilt; rhythm and tempo; momentum from recent threat.
- Milestones (for example 50 passes, a fifth save) and a significance score per event that decides whether it gets an AI line or becomes a live-square candidate.

## Responsible AI and limitations

- Every AI-written feed line, explanation and recap carries an "AI" label.
- Agents only see facts from the match state, with masked stats left out so a line can't reveal an open square's answer. The verifier blocks invented numbers, unknown names and timing words that don't fit the clock.
- Prompts and replies are never written to logs. `ENABLE_SENSITIVE_DATA` is false in the deployment.
- Points have no cash value and there is no betting language. Viewers are anonymous; no personal data is collected.
- Limits: the data is synthetic; the xG and pass models are simple formulas tuned to that data; the commentary is generated and can still get a role wrong (for example who blocked a shot), which the verifier cannot detect. At high replay speed several agents can fire at once, and an occasional call times out and keeps its template.

## Run locally

Requires Python 3.12 and Node 20.

```bash
# backend
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/uvicorn app.main:app --port 8000

# frontend, in a second terminal
cd frontend
npm install
npm run dev        # http://localhost:5173, proxies /api and /ws to port 8000
```

Without a Foundry endpoint the app runs entirely on template text. To use Foundry, sign in with `az login`, copy `.env.example` to `.env` at the repo root and set `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_MODEL_FAST` and `FOUNDRY_MODEL_QUALITY` to your project endpoint and deployment names. Your account needs the Foundry User role on the Foundry resource.

To regenerate a match: `backend/.venv/bin/python -m app.generator --seed 2610 --out data/matches` from the repo root.

## Deploy

The `Dockerfile` builds the frontend, then runs the backend with the built files. The live app was deployed with Azure Container Apps:

```bash
# image (cloud builds were unavailable on this subscription, so it is built locally)
docker buildx build --platform linux/amd64 -t $REGISTRY.azurecr.io/pitchbingo:$TAG --load .
az acr login --name $REGISTRY
docker push $REGISTRY.azurecr.io/pitchbingo:$TAG

# app, identity and settings
az containerapp up --name pitchbingo --resource-group $RG --location $LOC \
  --environment pitchbingo-env --image $REGISTRY.azurecr.io/pitchbingo:$TAG \
  --registry-server $REGISTRY.azurecr.io --ingress external --target-port 8000
az containerapp identity assign --name pitchbingo --resource-group $RG --system-assigned
az role assignment create --role "53ca6127-db72-4b80-b1b0-d745d6d5456d" \
  --assignee-object-id <app principal id> --assignee-principal-type ServicePrincipal \
  --scope <Foundry resource id>
az containerapp update --name pitchbingo --resource-group $RG \
  --cpu 0.5 --memory 1.0Gi --min-replicas 0 --max-replicas 1 \
  --set-env-vars FOUNDRY_PROJECT_ENDPOINT=<endpoint> FOUNDRY_MODEL_FAST=gpt-4.1-mini \
    FOUNDRY_MODEL_QUALITY=gpt-5-mini STORAGE=memory LANGUAGES=en,fr DEV_PANEL=true
```

Where cloud builds are allowed, `az containerapp up --source .` builds and deploys in one step.

## Tests and CI

- Backend: 527 tests (`cd backend && .venv/bin/pytest`), plus `ruff check .` and `mypy app`. They cover the generator, stats, every game rule in spec section 4 (card, windows, scoring, lines, moves, masks, live squares, strategist, fans), the verifier, the agents, the workflows, French, and WebSocket round trips.
- Frontend: 103 tests (`cd frontend && npm test`) for the card state, move rules (mirroring the backend's table), components, French strings and the setup screen.
- No test calls Azure. Agent tests use an in-process `FakeChatClient`, and the test setup blanks the Foundry endpoint so a local `.env` can't leak in.
- GitHub Actions (`.github/workflows/ci.yml`) runs the backend checks and the frontend build and tests on every push and pull request.

## Repository layout

```text
pitch-bingo/
  Dockerfile              builds the frontend, then runs the backend
  .env.example            settings for local runs (no secrets)
  .github/workflows/      ci.yml
  backend/
    pyproject.toml
    app/
      main.py             FastAPI app: API routes, WebSocket, static files
      session.py          one MatchSession per viewer: replay, game, agents, fans
      config.py           settings from the environment
      telemetry.py        spans, metrics and the per-moment log line
      models.py           WebSocket and API messages
      engine/             replay clock and ReplaySource
      generator/          synthetic match generator and validation
      stats/              running stats, xG, passes, patterns, significance
      game/               card builder, question bank, scorekeeper, live squares,
                          masks, strategist, simulated fans, English and French text
      agents/             Foundry clients, agents, workflows, breaker, fake client
      verify/             verifier
    tests/
  frontend/
    src/                  App, WebSocket client, Pitch, Feed, Metrics, Card, Leaderboard,
                          Setup, FullTime, DevPanel
    src/i18n/             en.json and fr.json
  data/matches/{seed}/    match.json, events.jsonl, tracking.npz, summary.json
  schemas/                JSON Schemas for matches and events
  docs/                   SPEC.md, schema.md, validation.png
```

## Not built yet

The Studio tab and overlay export, the settings drawer, the incident-replay inset, Cosmos DB storage, the focus player's ring and stats card, and changing language mid-match. These are described in `docs/SPEC.md`.

## Roadmap

- One shared live clock per real match for all viewers through Azure Web PubSub, with session state in a shared store.
- A live data source fed by Azure Event Hubs, and events detected from match video.
- Points toward Premier League merch (points have no cash value today), and a mobile app.

## Built with

Python, FastAPI, NumPy, React, TypeScript and Vite. Developed with the help of Claude Code. The full build spec is in `docs/SPEC.md`.

## License

MIT. See `LICENSE`.
