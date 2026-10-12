"""YAML 条件只能读取 slots/context 字典，不允许执行 Python 代码。"""
import ast
import operator


def evaluate(expression: str, data: dict) -> bool:
    if len(expression) > 1000:
        raise ValueError('条件过长')
    comparisons = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Gt: operator.gt, ast.GtE: operator.ge, ast.Lt: operator.lt, ast.LtE: operator.le, ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b, ast.Is: operator.is_, ast.IsNot: operator.is_not}

    def visit(node):
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name) and node.id in {'slots', 'context'}:
            return data.get(node.id, {})
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'get' and isinstance(node.func.value, ast.Name) and node.func.value.id in {'slots', 'context'} and not node.keywords and 1 <= len(node.args) <= 2:
            return visit(node.func.value).get(*[visit(arg) for arg in node.args])
        if isinstance(node, ast.BoolOp):
            return all(visit(v) for v in node.values) if isinstance(node.op, ast.And) else any(visit(v) for v in node.values)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return not visit(node.operand)
        if isinstance(node, ast.Compare):
            left = visit(node.left)
            for op, right in zip(node.ops, node.comparators):
                target = visit(right)
                if type(op) not in comparisons or not comparisons[type(op)](left, target):
                    return False
                left = target
            return True
        if isinstance(node, (ast.List, ast.Tuple)):
            return [visit(value) for value in node.elts]
        raise ValueError('条件包含不允许的操作')
    return bool(visit(ast.parse(expression, mode='eval').body))
