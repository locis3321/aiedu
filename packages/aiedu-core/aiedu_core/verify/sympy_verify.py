"""受限 SymPy 数学核验服务。

R2 §9：SymPy parse_expr 使用 eval，外部文本必须走受限语法白名单构造；
本模块通过 AST 白名单检查后直接构造 SymPy 对象，全程不执行任意代码。
复杂符号任务应使用受限 worker 子进程 + 超时（见 math_verify），不占住 API 事件循环。
"""

import ast
import hashlib
import re

from sympy import Rational, Symbol, simplify

from aiedu_core.verify.evidence import (
    VERIFIER_VERSION,
    ClaimEvidenceData,
    VerificationRecord,
    normalize_problem,
)

# ---------------------------------------------------------------------------
# AST 白名单：只允许数字、有限变量、四则/幂/模运算、有限函数集
# ---------------------------------------------------------------------------

ALLOWED_BIN_OPS = {
    ast.Add: lambda a, b: a + b,
    ast.Sub: lambda a, b: a - b,
    ast.Mult: lambda a, b: a * b,
    ast.Div: lambda a, b: a / b,
    ast.Pow: lambda a, b: a ** b,
    ast.Mod: lambda a, b: a % b,
}
ALLOWED_UNARY_OPS = {
    ast.UAdd: lambda a: +a,
    ast.USub: lambda a: -a,
}
ALLOWED_NAMES = frozenset({"x", "y", "z", "a", "b", "c", "n", "k"})
ALLOWED_FUNCS = {
    "sqrt": lambda v: v ** Rational(1, 2),
    "abs": abs,
}


class UnsafeExpressionError(ValueError):
    """表达式包含白名单之外的语法节点。"""


# 写法归一化：× · ÷ 直接映射；x/X 仅在「数字之间」视为乘号（保留变量 x）
_MUL_BETWEEN_DIGITS = re.compile(r"(?<=\d)\s*[xX]\s*(?=\d)")


def normalize_expr_text(text: str) -> str:
    """把常见数学写法归一化为 Python/SymPy 可解析形式。

    - × · → *；÷ → /（全局映射，不改变语义）；
    - x / X 只在两侧都是数字时视为乘号（如 7x8 → 7*8），
      变量 x 出现的位置（如 x+1、3x）不受影响。
    """
    text = text.replace("×", "*").replace("·", "*").replace("÷", "/")
    return _MUL_BETWEEN_DIGITS.sub("*", text)


def _check_node(node: ast.AST) -> None:
    if isinstance(node, ast.Expression):
        _check_node(node.body)
        return
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float)):
            raise UnsafeExpressionError(f"disallowed constant: {node.value!r}")
        return
    if isinstance(node, ast.Name):
        if node.id not in ALLOWED_NAMES:
            raise UnsafeExpressionError(f"disallowed name: {node.id}")
        return
    if isinstance(node, ast.BinOp):
        if type(node.op) not in ALLOWED_BIN_OPS:
            raise UnsafeExpressionError(f"disallowed binop: {type(node.op).__name__}")
        _check_node(node.left)
        _check_node(node.right)
        return
    if isinstance(node, ast.UnaryOp):
        if type(node.op) not in ALLOWED_UNARY_OPS:
            raise UnsafeExpressionError(f"disallowed unaryop: {type(node.op).__name__}")
        _check_node(node.operand)
        return
    if isinstance(node, ast.Call):
        func = node.func
        if not isinstance(func, ast.Name) or func.id not in ALLOWED_FUNCS:
            raise UnsafeExpressionError("disallowed call")
        for arg in node.args:
            _check_node(arg)
        return
    raise UnsafeExpressionError(f"disallowed node: {type(node).__name__}")


def _to_sympy(node: ast.AST):
    """把已通过白名单检查的 AST 直接转换为 SymPy 对象（不经过 eval）。"""
    if isinstance(node, ast.Expression):
        return _to_sympy(node.body)
    if isinstance(node, ast.Constant):
        return Rational(str(node.value))
    if isinstance(node, ast.Name):
        return Symbol(node.id)
    if isinstance(node, ast.BinOp):
        op = ALLOWED_BIN_OPS[type(node.op)]
        return op(_to_sympy(node.left), _to_sympy(node.right))
    if isinstance(node, ast.UnaryOp):
        op = ALLOWED_UNARY_OPS[type(node.op)]
        return op(_to_sympy(node.operand))
    if isinstance(node, ast.Call):
        func = ALLOWED_FUNCS[node.func.id]
        return func(*[_to_sympy(arg) for arg in node.args])
    raise UnsafeExpressionError(f"disallowed node: {type(node).__name__}")


def parse_math_expr(text: str):
    """受限解析文本为 SymPy 表达式；非法输入抛 UnsafeExpressionError。"""
    tree = ast.parse(normalize_expr_text(text).strip(), mode="eval")
    _check_node(tree)
    return _to_sympy(tree)


def verify_expression(lhs_text: str, rhs_text: str) -> VerificationRecord:
    """验证 lhs == rhs（精确符号化简）；解析失败返回 requires_review。"""
    try:
        lhs = parse_math_expr(lhs_text)
        rhs = parse_math_expr(rhs_text)
        diff = simplify(lhs - rhs)
        status = "verified" if diff == 0 else "refuted"
        method = "精确符号化简"
        statement = f"{lhs_text} = {rhs_text}"
    except (UnsafeExpressionError, SyntaxError) as exc:
        status = "requires_review"
        method = f"受限解析拒绝：{exc}"
        statement = f"{lhs_text} = {rhs_text}"
    claim = ClaimEvidenceData(
        id="expr-eq", statement=statement, status=status, method=method
    )
    return VerificationRecord(
        verifier_version=VERIFIER_VERSION,
        normalized_problem_hash=hashlib.sha256(
            normalize_problem(f"{lhs_text}={rhs_text}").encode("utf-8")
        ).hexdigest(),
        assumptions=(),
        claims=(claim,),
        covered_claim_ids=("expr-eq",) if status == "verified" else (),
        result=status,
    )


def evaluate_expression(text: str):
    """受限解析并精确求值；非法输入抛 UnsafeExpressionError。"""
    return parse_math_expr(text)


def verify_arithmetic(expr_text: str) -> VerificationRecord:
    """算术式核验：受限解析并精确求值，返回核验证据。

    仅接受数学表达式文本（如 "16+8"）；自然语言题目解析由上层负责。
    答案由调用方通过 evaluate_expression(expr_text) 获取精确值。
    数值抽样不构成证明，本函数只做精确计算。
    """
    try:
        value = parse_math_expr(expr_text)
        status = "verified"
        method = "精确计算"
        statement = f"{expr_text} = {value}"
    except (UnsafeExpressionError, SyntaxError) as exc:
        status = "requires_review"
        method = f"受限解析拒绝：{exc}"
        statement = expr_text
    claim = ClaimEvidenceData(
        id="arithmetic", statement=statement, status=status, method=method
    )
    return VerificationRecord(
        verifier_version=VERIFIER_VERSION,
        normalized_problem_hash=hashlib.sha256(
            normalize_problem(expr_text).encode("utf-8")
        ).hexdigest(),
        assumptions=(),
        claims=(claim,),
        covered_claim_ids=("arithmetic",) if status == "verified" else (),
        result=status,
    )

def verify_math(expression_text: str, expected) -> VerificationRecord:
    """核验表达式精确求值等于期望值（乘除法写法归一化后）。

    expected 可为 int/float（如 56）或字符串（如 "56"）；解析失败返回
    requires_review，不猜测、不降级。
    """
    try:
        value = parse_math_expr(expression_text)
        if isinstance(expected, str):
            exp_value = parse_math_expr(expected)
        else:
            exp_value = Rational(str(expected))
        diff = simplify(value - exp_value)
        status = "verified" if diff == 0 else "refuted"
        method = "精确计算"
        statement = f"{expression_text} = {expected}"
    except (UnsafeExpressionError, SyntaxError) as exc:
        status = "requires_review"
        method = f"受限解析拒绝：{exc}"
        statement = f"{expression_text} = {expected}"
    claim = ClaimEvidenceData(
        id="arithmetic-eq", statement=statement, status=status, method=method
    )
    return VerificationRecord(
        verifier_version=VERIFIER_VERSION,
        normalized_problem_hash=hashlib.sha256(
            normalize_problem(f"{expression_text}={expected}").encode("utf-8")
        ).hexdigest(),
        assumptions=(),
        claims=(claim,),
        covered_claim_ids=("arithmetic-eq",) if status == "verified" else (),
        result=status,
    )
