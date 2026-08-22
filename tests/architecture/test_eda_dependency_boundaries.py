from __future__ import annotations

import ast
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DOMAIN_ROOT = REPOSITORY_ROOT / "src" / "ai_instrument_assistant" / "domain" / "eda"
EDA_INTERFACE_PATH = (
    REPOSITORY_ROOT
    / "src"
    / "ai_instrument_assistant"
    / "application"
    / "ports"
    / "eda_interface.py"
)


def imported_modules(path: Path) -> frozenset[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return frozenset(modules)


class EDADependencyBoundaryTests(unittest.TestCase):
    def test_domain_does_not_depend_on_protocol_or_integrations(self) -> None:
        domain_files = tuple(DOMAIN_ROOT.glob("*.py"))
        self.assertGreater(len(domain_files), 0, "EDA domain files were not found")

        for path in domain_files:
            with self.subTest(path=path.name):
                imports = imported_modules(path)
                self.assertFalse(
                    any(
                        module == "ai_instrument_assistant.protocol"
                        or module.startswith("ai_instrument_assistant.protocol.")
                        or module == "ai_instrument_assistant.integrations"
                        or module.startswith("ai_instrument_assistant.integrations.")
                        for module in imports
                    ),
                    imports,
                )

    def test_eda_interface_does_not_depend_on_adapter_or_transport_modules(self) -> None:
        self.assertTrue(EDA_INTERFACE_PATH.is_file(), "EDA interface port was not found")
        imports = imported_modules(EDA_INTERFACE_PATH)

        forbidden_roots = {
            "json",
            "websocket",
            "websockets",
            "ai_instrument_assistant.protocol",
            "ai_instrument_assistant.integrations",
        }
        self.assertFalse(
            any(
                module in forbidden_roots
                or any(module.startswith(root + ".") for root in forbidden_roots)
                for module in imports
            ),
            imports,
        )


if __name__ == "__main__":
    unittest.main()
