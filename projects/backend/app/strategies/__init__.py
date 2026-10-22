"""策略模板库：凑十法、破十法、退位减法等。"""

from app.strategies.base import StrategyMatch, StrategyTemplate, registry
from app.strategies.make_ten import make_ten

registry.register(make_ten)

__all__ = ["StrategyMatch", "StrategyTemplate", "registry", "make_ten"]
