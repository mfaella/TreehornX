from . import expressions as expr
from . import sorts


sort_of = expr.sort_of


def is_same_sort(left: expr.Expr, right: expr.Expr) -> bool:
    """Check if two expressions have the same sort.

    Args:
        left: The left expression.
        right: The right expression.
    Returns:
        True if both expressions have the same sort, False otherwise.
    """
    return sort_of(left) is sort_of(right)


def is_arithmetic_expression(expression: expr.Expr) -> bool:
    """Check if an expression is of an arithmetic sort (Int or Real).

    Args:
        expression: The expression to check.
    Returns:
        True if the expression is of sort Int or Real, False otherwise.
    """
    return isinstance(sort_of(expression), (sorts.Int, sorts.Real))
