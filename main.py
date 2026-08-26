import datetime
import json
import sqlite3
from contextlib import asynccontextmanager

import httpx
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles  # noqa: F401 — reserved for future static assets

DB_PATH = "ow_data.db"
OVERFAST_SUMMARY_URL = "https://overfast-api.tekrop.fr/players/{tag}/summary"
OVERFAST_STATS_URL = "https://overfast-api.tekrop.fr/players/{tag}/stats/summary"
TEAM_MEMBERS = ["Sipixer-2880", "George666-11942"]

# Background scheduler lives for the lifetime of the process.
scheduler = BackgroundScheduler()


def init_db() -> None:
    """Create the SQLite database and snapshots table if they do not exist."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                battle_tag TEXT,
                timestamp DATETIME,
                raw_data TEXT
            )
            """
        )
        conn.commit()


def log_scheduler_heartbeat() -> None:
    """Dummy job so we can confirm the scheduler is alive."""
    print("Scheduler is running")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the database and scheduler on startup; shut down on exit."""
    init_db()
    scheduler.add_job(log_scheduler_heartbeat, "interval", minutes=1)
    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="OW Tracker", version="1.0", lifespan=lifespan)


def format_battle_tag(battle_tag: str) -> str:
    """OverFast expects '#' in a battle tag to be replaced with '-'."""
    return battle_tag.replace("#", "-")


async def fetch_overfast_json(client: httpx.AsyncClient, url: str) -> dict:
    """GET a JSON payload from OverFast, mapping failures to HTTP exceptions."""
    try:
        response = await client.get(url)
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reach OverFast API: {exc}",
        ) from exc

    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Player not found")
    if response.status_code >= 400:
        raise HTTPException(
            status_code=500,
            detail=f"OverFast API failed with status {response.status_code}",
        )

    return response.json()


async def fetch_player_summary(battle_tag: str) -> dict:
    """Fetch a player's career summary from the OverFast API."""
    formatted_battle_tag = format_battle_tag(battle_tag)
    url = OVERFAST_SUMMARY_URL.format(tag=formatted_battle_tag)
    async with httpx.AsyncClient(timeout=30.0) as client:
        return await fetch_overfast_json(client, url)


async def fetch_player_snapshot_payload(battle_tag: str) -> dict:
    """Fetch summary and detailed stats, then combine them for storage."""
    formatted_battle_tag = format_battle_tag(battle_tag)
    summary_url = OVERFAST_SUMMARY_URL.format(tag=formatted_battle_tag)
    stats_url = OVERFAST_STATS_URL.format(tag=formatted_battle_tag)

    async with httpx.AsyncClient(timeout=30.0) as client:
        summary_data = await fetch_overfast_json(client, summary_url)
        stats_data = await fetch_overfast_json(client, stats_url)

    return {"summary": summary_data, "stats": stats_data}


def save_snapshot(battle_tag: str, payload: dict) -> None:
    """Persist a combined player snapshot to SQLite."""
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO snapshots (battle_tag, timestamp, raw_data) VALUES (?, ?, ?)",
            (battle_tag, timestamp, json.dumps(payload)),
        )
        conn.commit()


def normalize_snapshot(payload: dict) -> dict:
    """Expose summary fields at the top level while keeping nested stats."""
    if isinstance(payload, dict) and isinstance(payload.get("summary"), dict):
        return {
            **payload["summary"],
            "summary": payload["summary"],
            "stats": payload.get("stats"),
        }
    return payload


def load_latest_snapshot(battle_tag: str) -> tuple[dict, str] | None:
    """Return (normalized payload, timestamp) for the newest row, or None."""
    formatted_battle_tag = format_battle_tag(battle_tag)
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            """
            SELECT raw_data, timestamp FROM snapshots
            WHERE battle_tag = ? OR battle_tag = ?
            ORDER BY timestamp DESC
            LIMIT 1
            """,
            (battle_tag, formatted_battle_tag),
        ).fetchone()

    if row is None:
        return None

    try:
        payload = json.loads(row[0])
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="Stored snapshot is not valid JSON") from exc

    return normalize_snapshot(payload), row[1]


@app.get("/")
def root():
    """Serve the dashboard frontend."""
    return FileResponse("index.html")


@app.get("/api/data/team/latest")
def get_team_latest():
    """Return the most recent snapshot for each hardcoded team member."""
    team = []
    for battle_tag in TEAM_MEMBERS:
        latest = load_latest_snapshot(battle_tag)
        if latest is None:
            team.append({"battle_tag": battle_tag, "found": False})
            continue
        payload, timestamp = latest
        team.append(
            {
                **payload,
                "battle_tag": battle_tag,
                "found": True,
                "timestamp": timestamp,
            }
        )
    return team


@app.get("/api/data/{battle_tag}")
def get_latest_snapshot(battle_tag: str):
    """Return the most recent saved snapshot for a battle tag."""
    latest = load_latest_snapshot(battle_tag)
    if latest is None:
        raise HTTPException(status_code=404, detail="No snapshot found for this player")
    payload, _timestamp = latest
    return payload


@app.get("/api/player/{battle_tag}")
async def get_player_summary(battle_tag: str):
    """Return the live OverFast summary for a battle tag."""
    return await fetch_player_summary(battle_tag)


@app.post("/api/snapshot/team/all")
async def snapshot_team():
    """Fetch and save summary + stats for every hardcoded team member."""
    saved = []
    errors = []
    for battle_tag in TEAM_MEMBERS:
        try:
            payload = await fetch_player_snapshot_payload(battle_tag)
            save_snapshot(battle_tag, payload)
            saved.append(battle_tag)
        except HTTPException as exc:
            errors.append({"battle_tag": battle_tag, "detail": exc.detail})
    return {"status": "success", "saved": saved, "errors": errors}


@app.post("/api/snapshot/{battle_tag}")
async def create_player_snapshot(battle_tag: str):
    """Fetch summary + stats and store the combined snapshot in SQLite."""
    payload = await fetch_player_snapshot_payload(battle_tag)
    save_snapshot(battle_tag, payload)
    return {"status": "success", "saved_tag": battle_tag}
