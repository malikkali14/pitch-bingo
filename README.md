# Pitch Bingo

A football match viewer where you only win by watching. A synthetic match plays out as live dots on a pitch, a running feed explains why each moment matters, and a 5x5 bingo card rewards attention and speed.

Built for the Microsoft x Premier League "Inside the Game" hackathon, using Microsoft Foundry, Microsoft Agent Framework and Azure Container Apps.

Status: work in progress. The full build spec is in docs/SPEC.md.

## Run locally

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e "backend[dev]"
cp .env.example .env   # fill in the Foundry values; STORAGE=memory needs no Azure
cd backend && uvicorn app.main:app --reload --port 8000
# second terminal
cd frontend && npm install && npm run dev
```

Checks: `cd backend && ruff check . && mypy app && pytest`, and `cd frontend && npm test`.
