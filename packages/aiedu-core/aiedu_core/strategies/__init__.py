"""策略模板库：凑十法、破十法、分数等分、和差倍、鸡兔同笼、等差数列。"""

from aiedu_core.strategies.arithmetic_sequence import arithmetic_sequence
from aiedu_core.strategies.base import StrategyMatch, StrategyTemplate, registry
from aiedu_core.strategies.chicken_rabbit import chicken_rabbit
from aiedu_core.strategies.sum_diff import sum_diff
from aiedu_core.strategies.borrow_ten import borrow_ten
from aiedu_core.strategies.fraction_equal_parts import fraction_equal_parts
from aiedu_core.strategies.make_ten import make_ten

registry.register(make_ten)
registry.register(borrow_ten)
registry.register(fraction_equal_parts)
registry.register(sum_diff)
registry.register(chicken_rabbit)
registry.register(arithmetic_sequence)

__all__ = [
    "StrategyMatch",
    "StrategyTemplate",
    "registry",
    "make_ten",
    "borrow_ten",
    "fraction_equal_parts",
    "sum_diff",
    "chicken_rabbit",
    "arithmetic_sequence",
]
