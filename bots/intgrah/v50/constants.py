from typing import Final

from util import INF

COST_ROAD: Final[int] = 1
COST_EMPTY: Final[int] = 3
COST_UNSEEN: Final[int] = 3
COST_IMPASSABLE: Final[int] = INF

# The number of buckets used in Dial's algorithm must exceed the maximum possible increase in f-value in A*.
# f(n) = g(n) + h(n)
# We take the maximum edge cost, plus one, because the Chebyshev heuristic can change by at most one, and then plus one again, so that it is greater than this number.
DIAL_MOD: Final[int] = max(COST_ROAD, COST_EMPTY, COST_UNSEEN) + 1 + 1
