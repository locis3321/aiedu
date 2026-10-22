"""策略模板库：凑十法、破十法、分数等分。"""

from aiedu_core.strategies.base import StrategyMatch, StrategyTemplate, registry
from aiedu_core.strategies.borrow_ten import borrow_ten
from aiedu_core.strategies.fraction_equal_parts import fraction_equal_parts
from aiedu_core.strategies.make_ten import make_ten

registry.register(make_ten)
registry.register(borrow_ten)
registry.register(fraction_equal_parts)

__all__ = [
    "StrategyMatch",
    "StrategyTemplate",
    "registry",
    "make_ten",
    "borrow_ten",
    "fraction_equal_parts",
]
