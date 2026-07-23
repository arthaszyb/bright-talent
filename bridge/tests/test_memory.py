"""Tests for the bridge's SQLite+FTS5 cross-thread memory recall.

Memory injection is a headline capability (the bridge recalls related prior
dialog from other threads in the same channel and prepends it as context).
These pin record → recall → scoping → budget behavior against a temp DB.
"""
from __future__ import annotations

from conftest import build_config_dict

from bridge.config import config_from_dict
from bridge.memory import PREFIX, Memory


def make_memory(tmp_path, **memory_overrides):
    cfg = config_from_dict(build_config_dict(tmp_path, memory=memory_overrides))
    return Memory(cfg, tmp_path / "data")


def test_recalls_matching_message_from_another_thread(tmp_path):
    mem = make_memory(tmp_path)
    mem.record("chan", "thread-B", "user", "the checkout latency spike happened at noon")
    out = mem.inject_context("chan", "thread-A", "checkout latency spike")
    assert PREFIX in out
    assert "checkout latency spike happened" in out
    assert out.rstrip().endswith("checkout latency spike")  # original message preserved at the end
    mem.close()


def test_does_not_recall_from_the_same_thread(tmp_path):
    mem = make_memory(tmp_path)
    mem.record("chan", "thread-A", "user", "checkout latency spike earlier today")
    out = mem.inject_context("chan", "thread-A", "checkout latency spike")
    assert out == "checkout latency spike"  # same thread excluded -> unchanged
    mem.close()


def test_does_not_recall_across_channels(tmp_path):
    mem = make_memory(tmp_path)
    mem.record("other-chan", "thread-B", "user", "checkout latency spike elsewhere")
    out = mem.inject_context("chan", "thread-A", "checkout latency spike")
    assert out == "checkout latency spike"
    mem.close()


def test_disabled_memory_is_passthrough(tmp_path):
    mem = make_memory(tmp_path, enabled=False)
    mem.record("chan", "thread-B", "user", "checkout latency spike happened")
    assert mem.inject_context("chan", "thread-A", "checkout latency spike") == "checkout latency spike"
    mem.close()


def test_short_message_below_min_chars_is_passthrough(tmp_path):
    mem = make_memory(tmp_path, context_min_chars=20)
    mem.record("chan", "thread-B", "user", "hello there friend")
    assert mem.inject_context("chan", "thread-A", "hello") == "hello"
    mem.close()


def test_no_match_is_passthrough(tmp_path):
    mem = make_memory(tmp_path)
    mem.record("chan", "thread-B", "user", "completely unrelated content about billing")
    out = mem.inject_context("chan", "thread-A", "kubernetes autoscaling policy")
    assert out == "kubernetes autoscaling policy"
    mem.close()


def test_max_results_caps_recalled_lines(tmp_path):
    mem = make_memory(tmp_path, context_max_results=2)
    for i in range(5):
        mem.record("chan", f"thread-{i}", "user", f"scaling review number {i} for checkout cluster")
    out = mem.inject_context("chan", "thread-A", "scaling review")
    assert PREFIX in out
    # Only the recalled dialog lines start with a "[role]" marker inside the block.
    assert out.count("[user]") <= 2
    mem.close()


def test_tiny_budget_falls_back_to_original_message(tmp_path):
    mem = make_memory(tmp_path, context_max_chars=5)
    mem.record("chan", "thread-B", "user", "scaling review for the checkout cluster today")
    out = mem.inject_context("chan", "thread-A", "scaling review")
    # No recalled line can fit a 5-char budget -> return the original message.
    assert out == "scaling review"
    mem.close()
