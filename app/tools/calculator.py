"""Safe arithmetic calculator (AST whitelist — no eval())."""

from __future__ import annotations

import ast
import math
import operator
from typing import Any, Callable

from app.models.tool_result import ErrorType, ToolResult
from app.tools.base import Tool


class CalculationError(ValueError):
    pass


_BIN_OPS: dict[type, Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPS: dict[type, Callable[[Any], Any]] = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_FUNCS: dict[str, Callable[..., Any]] = {"abs": abs, "round": round, "min": min, "max": max}
MAX_EXPR_LEN = 200
MAX_EXPONENT = 100


def safe_eval(expression: str) -> float:
    if not isinstance(expression, str) or not expression.strip():
        raise CalculationError("expression is empty")
    if len(expression) > MAX_EXPR_LEN:
        raise CalculationError(f"expression longer than {MAX_EXPR_LEN} characters")
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as e:
        raise CalculationError(f"syntax error: {e.msg}") from e
    try:
        value = _eval(tree.body)
    except ZeroDivisionError as e:
        raise CalculationError("division by zero") from e
    except OverflowError as e:
        raise CalculationError("numeric overflow") from e
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CalculationError("result is not a number")
    if not math.isfinite(value):
        raise CalculationError("result is not finite")
    return float(value)


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise CalculationError(f"unsupported constant {node.value!r}")
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
        left, right = _eval(node.left), _eval(node.right)
        if isinstance(node.op, ast.Pow) and abs(right) > MAX_EXPONENT:
            raise CalculationError("exponent too large")
        return _BIN_OPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPS:
        return _UNARY_OPS[type(node.op)](_eval(node.operand))
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _FUNCS
        and not node.keywords
        and 1 <= len(node.args) <= 10
    ):
        return _FUNCS[node.func.id](*(_eval(a) for a in node.args))
    raise CalculationError(f"unsupported syntax: {type(node).__name__}")


class CalculatorTool(Tool):
    name = "calculator"

    def _run(self, expression: str = "", **_: Any) -> ToolResult:
        try:
            value = safe_eval(expression)
        except CalculationError as e:
            return ToolResult.fail(self.name, ErrorType.INVALID_INPUT, str(e), retryable=False,
                                   expression=expression)
        return ToolResult.ok(self.name, {"expression": expression, "result": value})
