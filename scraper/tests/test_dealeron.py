from typing import Any, List, Optional

from providers.dealeron import _scroll_until_stable


class FakePage:
    """
    Stands in for a Playwright Page for _scroll_until_stable(), which
    only ever calls .evaluate() (for the scrollTo no-op and the card
    count) and .wait_for_timeout(). `card_counts` is the sequence of
    counts returned on each successive querySelectorAll evaluate call
    (the first call is the initial pre-loop read).
    """

    def __init__(self, card_counts: List[int]):
        self._card_counts = iter(card_counts)
        self._last_count = 0
        self.wait_calls = 0

    def evaluate(self, script: str) -> Optional[int]:
        if "querySelectorAll" in script:
            self._last_count = next(self._card_counts, self._last_count)
            return self._last_count
        return None

    def wait_for_timeout(self, ms: int) -> None:
        self.wait_calls += 1


def test_scroll_until_stable_stops_after_one_scroll_when_count_does_not_grow():
    page: Any = FakePage(card_counts=[4, 4])

    _scroll_until_stable(page)

    assert page.wait_calls == 1


def test_scroll_until_stable_keeps_scrolling_while_the_count_grows():
    page: Any = FakePage(card_counts=[4, 10, 20, 24, 24])

    _scroll_until_stable(page)

    assert page.wait_calls == 4


def test_scroll_until_stable_is_bounded_by_max_attempts():
    # A count that never stops growing (real cap: 56 vehicles, but the
    # function shouldn't need to know that) must not loop forever.
    page: Any = FakePage(card_counts=list(range(0, 1000, 4)))

    _scroll_until_stable(page, max_attempts=3)

    assert page.wait_calls == 3
