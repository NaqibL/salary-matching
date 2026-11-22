"""Which pay period an ad's salary figures are in.

Job ads put hourly rates, daily rates and part-time or internship pay into the same two
salary fields as a full-time monthly salary. A company's "typical pay" only means something
when it is computed over one kind, so every ad gets a kind and typical pay uses ``standard``
(full-time monthly) only. The same rule is written in SQL in the ``company_stats`` view
(migration 029); ``tests/test_company_pay.py`` keeps the two in step.
"""

from __future__ import annotations

from typing import Iterable, Literal

PayKind = Literal["standard", "hourly", "daily", "part_time", "internship"]

# Amounts below these are rates, not monthly salaries (a monthly salary under $500 does not
# occur in the ads; $8-$60 an hour and $100-$400 a day do).
HOURLY_BELOW = 100
DAILY_BELOW = 500
# "$1 - $1" and the like are placeholders, not pay.
PLACEHOLDER_BELOW = 5


def pay_kind(
    salary_min: int | None, salary_max: int | None, employment_types: Iterable[str] | None
) -> PayKind | None:
    """The ad's pay kind, or None when it states no usable salary."""
    top = salary_max if salary_max is not None else salary_min
    if salary_min is None or top is None or top < PLACEHOLDER_BELOW:
        return None
    if top < HOURLY_BELOW:
        return "hourly"
    if top < DAILY_BELOW:
        return "daily"
    types = {t.strip().lower() for t in (employment_types or [])}
    # Many full-time ads tick every box, "Part Time" included; only an ad that offers no
    # full-time or permanent form is treated as part-time (or an internship).
    full_time = "full time" in types or "permanent" in types
    if not full_time and "part time" in types:
        return "part_time"
    if not full_time and any(t.startswith("internship") for t in types):
        return "internship"
    return "standard"
