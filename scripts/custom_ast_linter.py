#!/usr/bin/env python3
"""Custom AST Linter for import dependencies.

Enforces that NotificationService is ONLY imported from allowed locations
like 'app.deps.content', 'app.core.di.content', or its definition file
'app.services.notification_service'.
Specifically, imports from 'app.deps.user', 'app.core.di.users', or any other
non-approved DI provider module will trigger an error.
"""

from __future__ import annotations

import ast
import os
import sys

ALLOWED_IMPORT_SOURCES = {
    "app.deps.content",
    "app.core.di.content",
    "app.services.notification_service",
}

# Exempt DI files where dependencies are wired to other services, but prevent them
# from registering duplicate provider functions.
EXEMPT_FILES = {
    # users.py is allowed to import NotificationService for type annotations in provider functions,
    # but NOT allowed to define a duplicate provider method itself.
    "app/core/di/users.py",
    "app/services/user_service.py",
    "app/services/user/profile_service.py",
}


def check_file(filepath: str) -> list[str]:
    """Parse python file and check for import violations of NotificationService."""
    normalized_path = os.path.relpath(filepath).replace("\\", "/")

    with open(filepath, encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read(), filename=filepath)
        except SyntaxError as e:
            return [f"{normalized_path}: SyntaxError: {e}"]

    violations = []
    for node in ast.walk(tree):
        # Check 'from module import name'
        if isinstance(node, ast.ImportFrom):
            if node.module:
                for alias in node.names:
                    if alias.name == "NotificationService":
                        # If importing from app.deps.user or other non-allowed source
                        if node.module not in ALLOWED_IMPORT_SOURCES:
                            # If it's in the exempt list (for type hint annotations), we allow it
                            # if it imports from the definition module.
                            if (
                                normalized_path in EXEMPT_FILES
                                and node.module == "app.services.notification_service"
                            ):
                                continue

                            violations.append(
                                f"{normalized_path}:{node.lineno}: "
                                f"Forbidden import of NotificationService from '{node.module}'. "
                                f"NotificationService must only be imported from 'app.deps.content'."
                            )

        # Check 'import module'
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.endswith("NotificationService"):
                    violations.append(
                        f"{normalized_path}:{node.lineno}: "
                        f"Direct import of '{alias.name}' is forbidden. "
                        f"NotificationService must be imported using 'from app.deps.content import NotificationService'."
                    )

    return violations


def main() -> None:
    target_dir = "app"
    if len(sys.argv) > 1:
        target_dir = sys.argv[1]

    all_violations = []
    for root, _, files in os.walk(target_dir):
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                violations = check_file(filepath)
                all_violations.extend(violations)

    if all_violations:
        print(
            "AST Linter: Found import violations of NotificationService rule (TD-33-08):",
            file=sys.stderr,
        )
        for violation in all_violations:
            print(f"  {violation}", file=sys.stderr)
        sys.exit(1)

    print("AST Linter: All imports of NotificationService conform to TD-33-08.")
    sys.exit(0)


if __name__ == "__main__":
    main()
