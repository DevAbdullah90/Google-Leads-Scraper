"""
Crash recovery: incremental saving (JSONL) and progress checkpointing.

Log coverage:
 - Every file read/write (path, record counts, file sizes)
 - Progress saves (what changed: businesses_scraped, query state)
 - JSONL → JSON finalisation (record count, output size)
 - Any I/O errors with full context
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiofiles

from config.settings import OUTPUT_DIR, PROGRESS_FILE
from scraper.utils import sanitize_filename

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Progress management
# ─────────────────────────────────────────────────────────────────────────────

def new_progress(queries: list[str], output_file: Path | None = None) -> dict[str, Any]:
    """Create a fresh progress object for a new session."""
    prog = {
        "session_id": str(uuid.uuid4()),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "current_query": queries[0] if queries else "",
        "queries_completed": [],
        "queries_remaining": list(queries),
        "businesses_scraped": 0,
        "businesses_failed": 0,
        "last_place_id": None,
        "last_checkpoint": datetime.now(timezone.utc).isoformat(),
        # Saved so resume can find the exact same .jsonl file
        "output_file": str(output_file) if output_file else None,
    }
    logger.debug(
        "New progress created | session=%s | queries=%d",
        prog["session_id"][:8], len(queries),
    )
    return prog


async def load_progress() -> dict[str, Any] | None:
    """Load progress.json if it exists and is valid JSON."""
    if not PROGRESS_FILE.exists():
        logger.debug("No progress.json found at %s", PROGRESS_FILE)
        return None
    try:
        async with aiofiles.open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            content = await f.read()
        data = json.loads(content)
        logger.info(
            "Loaded progress.json | session=%s | query=%r | scraped=%d | failed=%d",
            data.get("session_id", "?")[:8],
            data.get("current_query", "?"),
            data.get("businesses_scraped", 0),
            data.get("businesses_failed", 0),
        )
        return data
    except json.JSONDecodeError as e:
        logger.error("progress.json is corrupted (invalid JSON): %s", e)
        logger.error("  File: %s — you may need to delete it and restart.", PROGRESS_FILE)
    except Exception as e:
        logger.error("Could not load progress.json: %s", e)
    return None


async def save_progress(progress: dict[str, Any]) -> None:
    """Atomically write progress.json (write-to-tmp then rename)."""
    progress["last_checkpoint"] = datetime.now(timezone.utc).isoformat()
    tmp = PROGRESS_FILE.with_suffix(".tmp")
    try:
        async with aiofiles.open(tmp, "w", encoding="utf-8") as f:
            await f.write(json.dumps(progress, indent=2, ensure_ascii=False))
        tmp.replace(PROGRESS_FILE)
        logger.debug(
            "Progress saved | scraped=%d | failed=%d | query=%r",
            progress.get("businesses_scraped", 0),
            progress.get("businesses_failed", 0),
            progress.get("current_query", "?"),
        )
    except Exception as e:
        logger.error("FAILED to save progress.json: %s", e)
        logger.error("  Data at risk: %s", progress)


async def clear_progress() -> None:
    """Delete progress.json on successful completion."""
    if PROGRESS_FILE.exists():
        try:
            PROGRESS_FILE.unlink()
            logger.debug("progress.json deleted (session complete).")
        except Exception as e:
            logger.warning("Could not delete progress.json: %s", e)
    else:
        logger.debug("progress.json already absent — nothing to clear.")


# ─────────────────────────────────────────────────────────────────────────────
# Incremental business saving (JSONL)
# ─────────────────────────────────────────────────────────────────────────────

def get_jsonl_path(output_file: Path) -> Path:
    return output_file.with_suffix(".jsonl")


async def append_business(output_file: Path, business_dict: dict[str, Any]) -> bool:
    """
    Append one business record as a JSONL line.
    This is the incremental save — called after every business.
    Returns True on success, False on failure.
    """
    jsonl_path = get_jsonl_path(output_file)
    try:
        jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(jsonl_path, "a", encoding="utf-8") as f:
            await f.write(json.dumps(business_dict, ensure_ascii=False) + "\n")

        # Log file size every 10 records (rough check)
        size_kb = jsonl_path.stat().st_size / 1024
        logger.debug(
            "Business appended → %s (%.1f KB total)",
            jsonl_path.name, size_kb,
        )
        return True
    except Exception as e:
        logger.error(
            "FAILED to append business %r to %s: %s",
            business_dict.get("business_name", "?"), jsonl_path, e,
        )
        logger.error("  This business will NOT be in the output — data loss occurred!")
        return False


async def load_businesses_from_jsonl(output_file: Path) -> list[dict[str, Any]]:
    """Read all business records from the JSONL temp file."""
    jsonl_path = get_jsonl_path(output_file)
    if not jsonl_path.exists():
        logger.debug("JSONL file not found: %s", jsonl_path)
        return []

    businesses: list[dict[str, Any]] = []
    bad_lines = 0
    try:
        async with aiofiles.open(jsonl_path, "r", encoding="utf-8") as f:
            async for line_no, line in _enumerate_lines(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    businesses.append(json.loads(line))
                except json.JSONDecodeError as e:
                    bad_lines += 1
                    logger.warning(
                        "Skipping malformed JSONL line %d in %s: %s",
                        line_no, jsonl_path.name, e,
                    )
    except Exception as e:
        logger.error("Could not read %s: %s", jsonl_path, e)

    logger.debug(
        "Loaded %d records from %s (bad_lines=%d)",
        len(businesses), jsonl_path.name, bad_lines,
    )
    return businesses


async def finalize_output(
    output_file: Path,
    metadata: dict[str, Any],
    *,
    delete_jsonl: bool = True,
) -> int:
    """
    Convert the JSONL temp file to a structured, pretty-printed JSON output file.
    Returns the number of businesses written.
    """
    logger.info("Finalising output → %s", output_file.name)
    businesses = await load_businesses_from_jsonl(output_file)

    if not businesses:
        logger.warning(
            "No businesses in JSONL file — output JSON will not be created. "
            "JSONL path: %s",
            get_jsonl_path(output_file),
        )
        return 0

    wrapper = {
        "metadata": {
            **metadata,
            "total_results": len(businesses),
            "exported_at": datetime.now(timezone.utc).isoformat(),
        },
        "businesses": businesses,
    }

    try:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        json_str = json.dumps(wrapper, indent=2, ensure_ascii=False)
        async with aiofiles.open(output_file, "w", encoding="utf-8") as f:
            await f.write(json_str)

        size_kb = output_file.stat().st_size / 1024
        logger.info(
            "Output written: %s | %d businesses | %.1f KB",
            output_file, len(businesses), size_kb,
        )

        if delete_jsonl:
            jsonl = get_jsonl_path(output_file)
            if jsonl.exists():
                try:
                    json.loads(output_file.read_text(encoding="utf-8"))
                except Exception:
                    logger.error(
                        "Output JSON failed validation — keeping JSONL backup! (%s)", jsonl
                    )
                    return len(businesses)
                jsonl.unlink()
                logger.debug("Temp JSONL deleted: %s", jsonl.name)
    except Exception as e:
        logger.error("FAILED to write final JSON output %s: %s", output_file, e)

    return len(businesses)


# ─────────────────────────────────────────────────────────────────────────────
# Output file naming
# ─────────────────────────────────────────────────────────────────────────────

def build_output_path(query: str, output_dir: Path | None = None) -> Path:
    safe = sanitize_filename(query.lower().replace(" ", "_"), max_len=60)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dir_ = output_dir or OUTPUT_DIR
    path = dir_ / f"{safe}_{ts}.json"
    logger.debug("Output path: %s", path)
    return path


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _enumerate_lines(f):
    """Yield (line_number, line) from an async file handle."""
    line_no = 0
    async for line in f:
        line_no += 1
        yield line_no, line
