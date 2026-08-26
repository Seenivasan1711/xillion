"""
Markdown export for docs/strategies/<name>.md (CP6) -- the file the RAG
layer (CP8) will ingest, and the durable record of what a strategy was
supposed to do vs. what actually happened.

This module owns exactly two sections: "5. Failure log" and "6. Version
history". Everything else (the rules, backtest/paper/live results) is
written by a human at each pipeline stage and must survive re-export
byte-for-byte -- only the data ROWS of those two tables are replaced, never
the surrounding prose (e.g. the failure-modes legend line under section 5).
"""

import re
from datetime import UTC, datetime
from pathlib import Path

from xillion.db.models import StrategyVersionHistory
from xillion.engine.journal import JournalEntry

_REPO_ROOT = Path(__file__).parent.parent.parent
_TEMPLATE_PATH = _REPO_ROOT / "docs" / "strategies" / "_TEMPLATE.md"
STRATEGIES_DIR = _REPO_ROOT / "docs" / "strategies"

# Only outcomes with a real failure behind them belong in the failure log --
# a "win" or "target_hit" isn't a failure, and "still_open" isn't resolved
# yet either way.
_FAILURE_OUTCOMES = {"stopped_out", "loss", "unclassified"}


def slugify(strategy_name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", strategy_name.strip().lower()).strip("-")


def _failure_log_rows(entries: list[JournalEntry], notes: dict[tuple[str, str], dict]) -> list[str]:
    rows = []
    for e in entries:
        if e.outcome not in _FAILURE_OUTCOMES:
            continue
        note = notes.get((e.source, e.source_id), {})
        failure_mode = note.get("failure_mode") or e.outcome
        change_made = note.get("change_made") or ""
        date = (e.exit_ts or e.entry_ts or "")[:10]
        what = f"{e.symbol} {e.side or ''}: entry {e.entry_price} -> exit {e.exit_price}".replace(
            "  ", " "
        ).strip()
        rows.append(f"| {date} | {what} | {failure_mode} | {change_made} |")
    return rows


def _version_history_rows(version_rows: list[StrategyVersionHistory]) -> list[str]:
    rows = []
    for i, row in enumerate(version_rows, start=1):
        rows.append(
            f"| v{i} ({row.version}) | {row.recorded_at[:10]} | code changed | hash `{row.code_hash[:10]}` |"
        )
    return rows


def _replace_table_rows(content: str, heading: str, new_rows: list[str]) -> str:
    """Replace only the data rows of the first markdown table under
    `heading` (the header + separator row are left as-is). Raises if the
    heading or its table can't be found -- a silent no-op would be worse
    than a loud failure here."""
    # The separator-row class deliberately excludes \n (unlike \s, which
    # matches it) -- with \s in the class this would greedily swallow the
    # NEXT line too whenever it also happened to be pipes/spaces (e.g. an
    # empty placeholder data row "| | | | |"), silently merging it into the
    # "header" group instead of leaving it in the replaceable data-rows group.
    pattern = re.compile(
        rf"(^{re.escape(heading)}.*?\n\|[^\n]*\n\|[ \t\-|]+\n)((?:\|[^\n]*\n?)*)",
        re.MULTILINE | re.DOTALL,
    )
    replacement_rows = "\n".join(new_rows) + "\n" if new_rows else "| | | | |\n"

    def _sub(match: re.Match) -> str:
        return match.group(1) + replacement_rows

    new_content, count = pattern.subn(_sub, content, count=1)
    if count == 0:
        raise ValueError(f"Could not find a table under {heading!r} to replace")
    return new_content


def export_strategy_markdown(
    strategy_name: str,
    entries: list[JournalEntry],
    notes: dict[tuple[str, str], dict],
    version_rows: list[StrategyVersionHistory],
    *,
    existing_content: str | None = None,
) -> str:
    """Returns the full markdown content. Pure function (no disk I/O) so
    it's directly testable -- see write_strategy_markdown for the disk
    write and status/created-date bookkeeping."""
    content = existing_content
    if content is None:
        content = _TEMPLATE_PATH.read_text().replace("<NAME>", strategy_name)

    content = _replace_table_rows(content, "## 5. Failure log", _failure_log_rows(entries, notes))
    content = _replace_table_rows(
        content, "## 6. Version history", _version_history_rows(version_rows)
    )

    today = datetime.now(UTC).date().isoformat()
    content = re.sub(
        r"\*\*Last updated:\*\* [\d-]+|\*\*Last updated:\*\* YYYY-MM-DD",
        f"**Last updated:** {today}",
        content,
        count=1,
    )
    return content


def write_strategy_markdown(
    strategy_name: str,
    entries: list[JournalEntry],
    notes: dict[tuple[str, str], dict],
    version_rows: list[StrategyVersionHistory],
) -> Path:
    path = STRATEGIES_DIR / f"{slugify(strategy_name)}.md"
    existing = path.read_text() if path.exists() else None
    content = export_strategy_markdown(
        strategy_name, entries, notes, version_rows, existing_content=existing
    )
    path.write_text(content)
    return path
