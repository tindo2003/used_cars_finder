from typing import AbstractSet, Optional


def page_did_not_advance(current_vins: AbstractSet[str], previous_vins: Optional[AbstractSet[str]]) -> bool:
    """
    True if clicking "Next" produced the exact same set of VINs as the
    prior page -- meaning the click succeeded (no exception) but the
    content didn't actually change, e.g. a dealer with only one real page
    of results but an always-clickable Next button. This is the only
    case that should stop pagination early; a page with different VINs
    (even if it overlaps partially, e.g. inventory shifted between loads)
    means real pagination is happening and should continue.

    `previous_vins` is None on the first page, which never counts as a
    stall (nothing to compare against yet). An empty `current_vins`
    (couldn't read any VINs off this page) also never counts as a stall
    -- we can't judge a stall from no data, so we let the loop's normal
    "next button" check decide instead.
    """
    if previous_vins is None:
        return False
    if not current_vins:
        return False
    return current_vins == previous_vins
