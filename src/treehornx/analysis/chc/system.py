from collections import defaultdict
from dataclasses import dataclass, field
import shutil
import tempfile
from typing import IO, Iterable

from treehornx.symbolic_tree import Edge, SymbolicTree
from treehornx.analysis.commons.ConstrTLab import ConstrTLab
from treehornx.analysis.constraints.symbols import Parent, Slot, Symbol
from treehornx.enum_models.labels import get_tlab_id
from treehornx.smt.sexpr import Application, Clause, Predicate


def write_horn(clauses: Iterable[Clause], out: IO[str]) -> None:
    """Writes the HORN script of `clauses`, declaring the predicates they use.

    The clauses are consumed once: each one is spooled to a temporary file while the used predicates are
    collected, then copied after the declarations, so a lazily generated system is never held in memory."""
    used: dict[str, Predicate] = {}
    with tempfile.TemporaryFile("w+") as spool:
        for clause in clauses:
            for app in clause.applications():
                used.setdefault(app.predicate.name, app.predicate)
            spool.write(clause.to_smt())
            spool.write("\n")

        out.write("(set-logic HORN)\n")
        for name in sorted(used):
            out.write(used[name].smt_declaration())
            out.write("\n")
        out.write("\n")
        spool.seek(0)
        shutil.copyfileobj(spool, out)
        out.write("(check-sat)\n")


@dataclass
class CHCSystem:
    predicates: list[Predicate] = field(default_factory=list[Predicate])
    clauses: list[Clause] = field(default_factory=list[Clause])

    def queries(self) -> list[Clause]:
        """The clauses with head False, in order."""
        return [clause for clause in self.clauses if clause.head is False]

    def write(self, out: IO[str]) -> None:
        write_horn(self.clauses, out)

    def to_smt(self) -> str:
        """The SMT-LIB script of the system, only the predicates used by some clause are declared."""
        clauses = self.clauses
        lines = ["(set-logic HORN)"]
        used = {app.predicate.name: app.predicate for clause in clauses for app in clause.applications()}
        lines += [used[name].smt_declaration() for name in sorted(used)]
        lines.append("")
        lines += [clause.to_smt() for clause in clauses]
        lines.append("(check-sat)")
        return "\n".join(lines) + "\n"

    @staticmethod
    def from_tree(tree: SymbolicTree[ConstrTLab]) -> "CHCSystem":
        """The CHC system of `tree`. Every label L has the predicates `THX<id>_<n>` (n = 0 .. arity): the
        arguments of L and the error flag after its first n children are collected (`ConstrTLab.apply`).

        * base, L with children: `constraints(L) ∧ e0 = error(L) → THX<L>_0`;
        * leaf L: `constraints(L) ∧ e<a> = error(L) → THX<L>_<a>`, a = arity;
        * edge (P, C, j): `THX<P>_j ∧ THX<C>_<a> ∧ consistency(P, C, j) ∧ p_e<j+1> = (or p_e<j> c<j>_e<a>
          error(P, C, j)) → THX<P>_<j+1>`;
        * query, root R: `THX<R>_<a> ∧ e<a> → false`.

        sat = no error is reachable."""
        arity = tree.arity
        labels = sorted(tree.labels, key=lambda label: get_tlab_id(label.tlab))
        ids: dict[ConstrTLab, int] = {label: i for i, label in enumerate(labels)}

        children: defaultdict[ConstrTLab, defaultdict[int, list[ConstrTLab]]] = defaultdict(
            lambda: defaultdict(list[ConstrTLab])
        )
        for edge in tree.edges:
            children[edge.parent][edge.j].append(edge.child)

        def apply(label: ConstrTLab, n: int, role: Parent | Slot | None = None) -> Application:
            return label.apply(role, f"{ids[label]}_{n}")

        def edge_clause(edge: Edge[ConstrTLab]) -> Clause:
            parent, child, j = edge.parent, edge.child, edge.j
            body = [
                apply(parent, j, Parent()),
                apply(child, arity, Slot(j)),
                *ConstrTLab.consistency_constraints(parent, child, j),
                *ConstrTLab.edge_error_constraints(parent, child, j),
            ]
            return Clause.make(head=apply(parent, j + 1, Parent()), body=body)

        clauses: list[Clause] = []
        for label in labels:
            start = arity if label in tree.leaves else 0
            body = [*label.constraints(), *label.error_constraints(start)]
            clauses.append(Clause.make(head=apply(label, start), body=body))
            by_slot = children.get(label)
            if by_slot is None:
                continue
            for j in range(arity):
                for child in sorted(by_slot[j], key=ids.__getitem__):
                    clauses.append(edge_clause(Edge(label, child, j)))

        for root in labels:
            if root in tree.roots:
                body = [apply(root, arity), Symbol.error(arity)]
                clauses.append(Clause.make(head=False, body=body))

        predicates = {app.predicate.name: app.predicate for clause in clauses for app in clause.applications()}
        return CHCSystem(predicates=list(predicates.values()), clauses=clauses)
