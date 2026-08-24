"""
Markdown export (CP6): only sections 5 (Failure log) and 6 (Version
history) are ever touched. Everything else -- rules, backtest/paper/live
results, the failure-modes legend line -- must survive re-export
byte-for-byte, since a human wrote it and it's not this module's to lose.
"""
from datetime import datetime, timezone
from types import SimpleNamespace

from xillion.engine.journal import JournalEntry
from xillion.engine.strategy_export import _TEMPLATE_PATH, export_strategy_markdown, slugify


def _entry(outcome: str, symbol="TEST", side="BUY", entry_price=100.0, exit_price=95.0, exit_ts="2026-06-15T00:00:00") -> JournalEntry:
    return JournalEntry(
        source="signal_log", source_id="1", strategy_name="Test Strategy",
        strategy_instance_id="inst-1", symbol=symbol, side=side,
        entry_price=entry_price, exit_price=exit_price,
        entry_ts="2026-06-14T00:00:00", exit_ts=exit_ts,
        pnl=None, target_price=110.0, stop_loss_price=95.0,
        outcome=outcome, tag="setup_1",
    )


def _version_row(version: str, code_hash: str, recorded_at="2026-06-01T00:00:00"):
    return SimpleNamespace(version=version, code_hash=code_hash, recorded_at=recorded_at)


def test_slugify():
    assert slugify("RSI Threshold") == "rsi-threshold"
    assert slugify("  Condition Strategy!! ") == "condition-strategy"


def test_export_from_template_fills_failure_log_and_version_history():
    entries = [_entry("stopped_out")]
    notes = {}
    versions = [_version_row("1.0.0", "abcdef1234567890")]

    content = export_strategy_markdown("Test Strategy", entries, notes, versions)

    assert "# Strategy: Test Strategy" in content
    assert "stopped_out" in content
    assert "TEST BUY: entry 100.0 -> exit 95.0" in content
    assert "v1 (1.0.0)" in content
    assert "hash `abcdef1234`" in content


def test_prose_and_legend_line_survive_untouched():
    entries = [_entry("stopped_out")]
    content = export_strategy_markdown("Test Strategy", entries, {}, [])

    # The failure-modes legend and every other section's prose must still be there.
    assert "Failure modes: `stopped_out` · `target_missed` · `late_entry`" in content
    assert "## 1. The rules (plain language)" in content
    assert "State it so someone with no context could trade it manually." in content
    assert "## 2. Backtest results (Stage 2)" in content
    assert "**Parameter sensitivity:** does it survive" in content


def test_template_placeholder_row_is_actually_removed():
    """Regression: the separator-row regex used \\s (which matches \\n) in
    its character class, so it silently swallowed the template's empty
    placeholder data row "| | | | |" into the "header" group instead of the
    replaceable "data rows" group -- real rows got appended after it rather
    than replacing it. Caught only by inspecting actual export output in a
    browser, not by earlier assertions here that just checked new content
    was present without checking the placeholder was gone."""
    entries = [_entry("stopped_out")]
    content = export_strategy_markdown("Test Strategy", entries, {}, [])
    section = content[content.index("## 5"):content.index("## 6")]
    assert "| | | | |" not in section


def test_wins_and_open_signals_are_excluded_from_failure_log():
    entries = [
        _entry("target_hit"),  # not a failure
        JournalEntry(
            source="signal_log", source_id="2", strategy_name="Test Strategy",
            strategy_instance_id="inst-1", symbol="TEST", side="BUY",
            entry_price=100.0, exit_price=None, entry_ts="2026-06-14T00:00:00", exit_ts=None,
            pnl=None, target_price=110.0, stop_loss_price=95.0, outcome="still_open", tag="setup_2",
        ),
        _entry("stopped_out"),  # this one should show up
    ]
    content = export_strategy_markdown("Test Strategy", entries, {}, [])
    # Only the stopped_out row's failure log line should be present -- an
    # empty placeholder row means "no entries matched" in this table shape.
    assert content.count("| 2026-06-15 |") == 1


def test_manual_note_overrides_failure_mode_and_adds_change_made():
    entries = [_entry("unclassified")]
    notes = {("signal_log", "1"): {"failure_mode": "late_entry", "change_made": "tightened entry filter"}}
    content = export_strategy_markdown("Test Strategy", entries, notes, [])
    assert "late_entry" in content
    assert "tightened entry filter" in content


def test_reexport_on_existing_content_is_idempotent_and_updates_in_place():
    entries = [_entry("stopped_out")]
    versions = [_version_row("1.0.0", "hash1")]

    first = export_strategy_markdown("Test Strategy", entries, {}, versions)
    # A second export, fed the FIRST export's content as existing_content,
    # with a new version added -- must replace the old row set, not append
    # to it or duplicate the legend/prose again.
    second = export_strategy_markdown(
        "Test Strategy", entries, {}, versions + [_version_row("1.0.1", "hash2")],
        existing_content=first,
    )
    assert second.count("Failure modes: `stopped_out`") == 1
    assert second.count("## 1. The rules") == 1
    assert "v1 (1.0.0)" in second
    assert "v2 (1.0.1)" in second


def test_last_updated_is_bumped_to_today():
    content = export_strategy_markdown("Test Strategy", [], {}, [])
    today = datetime.now(timezone.utc).date().isoformat()
    assert f"**Last updated:** {today}" in content
    assert "Last updated:** YYYY-MM-DD" not in content


def test_template_file_actually_has_the_sections_this_module_assumes():
    """Guards against the template being edited in a way that silently
    breaks the section-matching regex -- fails loud here instead of at
    export time in the app."""
    text = _TEMPLATE_PATH.read_text()
    assert "## 5. Failure log" in text
    assert "## 6. Version history" in text
