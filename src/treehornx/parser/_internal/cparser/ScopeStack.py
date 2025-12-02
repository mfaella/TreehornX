from collections import defaultdict, deque
from dataclasses import dataclass, field

from ir.expressions import Var
from ir.sorts import Sort


@dataclass
class ScopeStack:
    stack: deque[dict[str, Var]] = field(init=False, default_factory=lambda: deque())
    vars_counters: defaultdict[str, int] = field(init=False, default_factory=lambda: defaultdict(int))
    vars: set[Var] = field(init=False, default_factory=lambda: set())

    def push_scope(self) -> None:
        self.stack.append({})

    def pop_scope(self) -> None:
        if not self.stack:
            raise RuntimeError("Cannot pop from an empty scope stack.")
        self.stack.pop()

    def get_variable(self, name: str) -> Var:
        for scope in reversed(self.stack):
            if name in scope:
                return scope[name]

        raise KeyError(f"Variable '{name}' not found in any scope.")

    def declare_variable(self, name: str, sort: Sort) -> None:
        assert self.stack, "No scope available to declare a variable."

        current_scope = self.stack[-1]
        if name in current_scope:
            raise KeyError(f"Variable '{name}' already declared in the current scope.")
        mangled_name = f"{name}_{self.vars_counters[name]}"
        self.vars_counters[name] += 1
        var = Var(name=mangled_name, sort=sort)
        current_scope[name] = var
        self.vars.add(var)

    def is_variable_declared(self, name: str) -> bool:
        for scope in reversed(self.stack):
            if name in scope:
                return True
        return False

    def clear(self) -> None:
        self.stack.clear()
        self.vars_counters.clear()
        self.vars.clear()
