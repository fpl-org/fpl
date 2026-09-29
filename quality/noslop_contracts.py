"""quality/noslop_contracts.py — import-linter contract types of the harness's own.

Registered in quality/importlinter.ini under `contract_types`; `make check` finds this module
on PYTHONPATH, which holds quality/.

`forbidden_once_present` is import-linter's `forbidden` contract for a package that does not
exist yet. The plain contract stops with "Module 'fpl.asm' does not exist." when a source
module is missing, which would fail `make check` on every tree that predates the package. This
one is kept, with a warning, while none of its source modules is in the import graph, and is
the plain contract from the moment one of them is. So a rule can stand in the root before the
first commit it applies to.

Its `source_modules` are module names, and a wildcard among them is refused: a wildcard is
never a module in the graph, so it would keep the contract for good. A wildcard needs none of
this anyway: the plain contract already keeps one that matches nothing.
"""

from typing import override

from grimp import ImportGraph
from importlinter.contracts.forbidden import ForbiddenContract
from importlinter.domain.contract import ContractCheck, InvalidContractOptions


class ForbiddenOncePresent(ForbiddenContract):
    """`forbidden`, kept while none of its source modules exists."""

    type_name = "forbidden_once_present"

    @classmethod
    @override
    def _get_field_names(cls) -> list[str]:
        """The options of `forbidden`. import-linter collects a contract's fields from its own
        class body, not from the classes it inherits, so a subclass would otherwise have none."""
        return ForbiddenContract._get_field_names()

    @override
    def validate(self) -> None:
        wildcards = [e.expression for e in self.source_modules if e.has_wildcard_expression()]
        if wildcards:
            raise InvalidContractOptions({"source_modules": f"names only: {wildcards}"})

    @override
    def check(self, graph: ImportGraph, verbose: bool) -> ContractCheck:
        sources = {expression.expression for expression in self.source_modules}
        if sources.isdisjoint(graph.modules):
            absent = ", ".join(sorted(sources))
            return ContractCheck(kept=True, warnings=[f"{absent} does not exist yet"])
        return super().check(graph, verbose)
