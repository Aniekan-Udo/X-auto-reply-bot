# test_dedup.py

import time
import pytest
from queue_dedup.dedup import MemoryDedup


@pytest.fixture
def dedup():
    return MemoryDedup()


class TestMemoryDedup:

    def test_new_tweet_is_not_duplicate(self, dedup):
        assert dedup.is_duplicate("1001") is False

    def test_seen_tweet_is_duplicate(self, dedup):
        dedup.mark_seen("1001")
        assert dedup.is_duplicate("1001") is True

    def test_different_ids_are_independent(self, dedup):
        dedup.mark_seen("1001")
        assert dedup.is_duplicate("1002") is False

    def test_check_and_mark_returns_false_for_new(self, dedup):
        assert dedup.check_and_mark("1001") is False

    def test_check_and_mark_returns_true_for_duplicate(self, dedup):
        dedup.check_and_mark("1001")
        assert dedup.check_and_mark("1001") is True

    def test_check_and_mark_marks_on_first_call(self, dedup):
        dedup.check_and_mark("1001")
        assert dedup.is_duplicate("1001") is True

    def test_expired_entry_is_treated_as_new(self, dedup):
        dedup._seen["1001"] = time.time() - 1  # already expired
        assert dedup.is_duplicate("1001") is False

    def test_eviction_removes_expired_entries(self, dedup):
        dedup._seen["1001"] = time.time() - 1   # expired
        dedup._seen["1002"] = time.time() + 10  # still valid
        dedup._evict_expired()
        assert "1001" not in dedup._seen
        assert "1002" in dedup._seen

    def test_multiple_unique_ids(self, dedup):
        ids = ["1001", "1002", "1003"]
        for tweet_id in ids:
            assert dedup.check_and_mark(tweet_id) is False
        for tweet_id in ids:
            assert dedup.check_and_mark(tweet_id) is True
