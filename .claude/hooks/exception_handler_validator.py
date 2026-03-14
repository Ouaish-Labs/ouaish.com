#!/usr/bin/env python3
"""
Claude Code PreToolUse Hook: Exception Handler Validator

Detects silent failure anti-patterns in Python exception handlers:
1. Bare `except:` clauses
2. `return 0`, `return None`, `return {}`, `return []` in except blocks without logging
3. Exception swallowing without proper error handling

Hook protocol (PreToolUse on Edit|Write):
- stdin: JSON with tool_name and input (file_path, new_string or content)
- stdout: {"decision": "approve"} or {"decision": "block", "reason": "..."} (exit 2)

Exit codes:
- 0: Allow (no issues found or not applicable)
- 2: Block with error message (anti-patterns detected)
"""

import ast
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Debug logging
DEBUG_LOG = PROJECT_ROOT / ".claude" / "hooks" / "hook_debug.log"


def log_debug(message: str):
    """Append debug message to log file."""
    try:
        with open(DEBUG_LOG, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] exception_validator: {message}\n")
    except Exception:
        pass


@dataclass
class Violation:
    """Represents a detected anti-pattern violation."""

    file_path: str
    line_number: int
    violation_type: str
    message: str


class ExceptionHandlerVisitor(ast.NodeVisitor):
    """AST visitor that detects silent failure patterns in exception handlers."""

    def __init__(self, file_path: str, source_lines: list):
        self.file_path = file_path
        self.source_lines = source_lines
        self.violations: list = []

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        """Visit an except handler and check for anti-patterns."""

        # Check 1: Bare except clause
        if node.type is None:
            self.violations.append(
                Violation(
                    file_path=self.file_path,
                    line_number=node.lineno,
                    violation_type="BARE_EXCEPT",
                    message="Bare 'except:' clause catches all exceptions including KeyboardInterrupt and SystemExit. "
                    "Use 'except Exception:' or a more specific exception type.",
                )
            )

        # Check 2: Silent return patterns in except body
        self._check_silent_returns(node)

        # Continue visiting child nodes
        self.generic_visit(node)

    def _check_silent_returns(self, handler: ast.ExceptHandler) -> None:
        """Check for silent return patterns (return 0, None, {}, []) in except body."""
        for stmt in ast.walk(handler):
            if isinstance(stmt, ast.Return) and self._is_silent_return(stmt, handler):
                # Check if there's proper logging before this return
                has_proper_logging = self._has_proper_error_handling(handler, stmt)

                if not has_proper_logging:
                    return_value = self._describe_return_value(stmt)
                    self.violations.append(
                        Violation(
                            file_path=self.file_path,
                            line_number=stmt.lineno,
                            violation_type="SILENT_RETURN",
                            message=f"Silent failure: 'return {return_value}' in except block without proper error handling. "
                            "Add logger.error() before return, re-raise the exception, or call sys.exit().",
                        )
                    )

    def _is_silent_return(self, return_node: ast.Return, handler: ast.ExceptHandler) -> bool:
        """Check if this return statement returns a silent failure value (0, None, {}, [])."""
        if return_node.value is None:
            # `return` without value (returns None implicitly)
            return True

        value = return_node.value

        # Check for literal 0
        if isinstance(value, ast.Constant) and value.value == 0:
            return True

        # Check for literal None
        if isinstance(value, ast.Constant) and value.value is None:
            return True

        # Check for empty dict {} or dict()
        if isinstance(value, ast.Dict) and len(value.keys) == 0:
            return True
        if (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "dict"
            and len(value.args) == 0
            and len(value.keywords) == 0
        ):
            return True

        # Check for empty list [] or list()
        if isinstance(value, ast.List) and len(value.elts) == 0:
            return True
        return (
            isinstance(value, ast.Call)
            and isinstance(value.func, ast.Name)
            and value.func.id == "list"
            and len(value.args) == 0
            and len(value.keywords) == 0
        )

    def _has_proper_error_handling(self, handler: ast.ExceptHandler, return_node: ast.Return) -> bool:
        """
        Check if there's proper error handling in the handler before the return.

        Acceptable patterns:
        - logger.error(...), logging.error(...), self.logger.error(...)
        - Any logger.*, logging.* call (warning, critical, etc.)
        - raise
        - sys.exit(...)
        """
        # Get statements before the return in the handler body
        for stmt in handler.body:
            if stmt is return_node:
                break

            # Check for raise statement
            if isinstance(stmt, ast.Raise):
                return True

            # Check for logger/logging calls or sys.exit
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
                call = stmt.value
                if self._is_error_log_call(call) or self._is_sys_exit(call):
                    return True

            # Also check nested statements (e.g., in if blocks)
            for node in ast.walk(stmt):
                if isinstance(node, ast.Call) and (self._is_error_log_call(node) or self._is_sys_exit(node)):
                    return True
                if isinstance(node, ast.Raise):
                    return True

        return False

    def _is_error_log_call(self, call: ast.Call) -> bool:
        """Check if this is a logger.error() or logging.error() (or similar) call."""
        func = call.func

        # Check logger.error, logging.error, logger.warning, etc.
        if isinstance(func, ast.Attribute) and func.attr in ("error", "warning", "critical", "exception"):
            if isinstance(func.value, ast.Name) and func.value.id in ("logger", "logging", "log"):
                return True
            # Check self.logger.error
            if isinstance(func.value, ast.Attribute) and func.value.attr in ("logger", "log"):
                return True

        return False

    def _is_sys_exit(self, call: ast.Call) -> bool:
        """Check if this is a sys.exit() call."""
        func = call.func
        if isinstance(func, ast.Attribute) and func.attr == "exit":
            if isinstance(func.value, ast.Name) and func.value.id == "sys":
                return True
        return False

    def _describe_return_value(self, return_node: ast.Return) -> str:
        """Get a string description of the return value."""
        if return_node.value is None:
            return "None"

        value = return_node.value

        if isinstance(value, ast.Constant):
            return repr(value.value)
        if isinstance(value, ast.Dict) and len(value.keys) == 0:
            return "{}"
        if isinstance(value, ast.List) and len(value.elts) == 0:
            return "[]"
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
            if value.func.id == "dict":
                return "dict()"
            if value.func.id == "list":
                return "list()"

        return "..."


def analyze_python_file(file_path: str, content: str) -> list:
    """Analyze a Python file for exception handling anti-patterns."""
    try:
        tree = ast.parse(content, filename=file_path)
    except SyntaxError as e:
        log_debug(f"Syntax error parsing {file_path}: {e}")
        return []  # Can't analyze files with syntax errors

    source_lines = content.split("\n")
    visitor = ExceptionHandlerVisitor(file_path, source_lines)
    visitor.visit(tree)

    return visitor.violations


def format_violations(violations: list) -> str:
    """Format violations into a readable error message."""
    if not violations:
        return ""

    lines = [
        "Exception Handler Anti-Pattern(s) Detected",
        "=" * 60,
        "",
    ]

    for v in violations:
        lines.append(f"  {v.file_path}:{v.line_number}")
        lines.append(f"    Type: {v.violation_type}")
        lines.append(f"    {v.message}")
        lines.append("")

    lines.append("How to Fix:")
    lines.append("-" * 40)
    lines.append("")
    lines.append("Option 1 - Add proper error logging before return:")
    lines.append('    logger.error(f"Operation failed: {e}")')
    lines.append("    return 0  # Now acceptable")
    lines.append("")
    lines.append("Option 2 - Re-raise the exception:")
    lines.append("    raise  # Let caller handle it")
    lines.append("")
    lines.append("Option 3 - Exit on fatal errors:")
    lines.append("    sys.exit(1)")

    return "\n".join(lines)


def main():
    log_debug("Hook started")

    try:
        raw_input_data = sys.stdin.read()
        log_debug(f"Raw input length: {len(raw_input_data)}")
        input_data = json.loads(raw_input_data)
    except json.JSONDecodeError as e:
        log_debug(f"JSON parse error: {e}")
        print(f"Error parsing hook input: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        log_debug(f"Unexpected error reading stdin: {type(e).__name__}: {e}")
        sys.exit(1)

    tool_name = input_data.get("tool_name", "")
    tool_input = input_data.get("tool_input", input_data.get("input", {}))

    # Only check Edit and Write tools on Python files
    if tool_name not in ("Edit", "Write"):
        print(json.dumps({"decision": "approve"}))
        sys.exit(0)

    file_path = tool_input.get("file_path", "")
    if not file_path.endswith(".py"):
        print(json.dumps({"decision": "approve"}))
        sys.exit(0)

    log_debug(f"Checking file: {file_path}")

    # For Write tool, analyze the new content directly
    # For Edit tool, simulate the edit and analyze the result
    if tool_name == "Write":
        content = tool_input.get("content", "")
        violations = analyze_python_file(file_path, content)
    else:
        # For Edit, read current file and simulate the edit
        try:
            original_content = Path(file_path).read_text(encoding="utf-8")
        except Exception as e:
            log_debug(f"Could not read original file {file_path}: {e}")
            print(json.dumps({"decision": "approve"}))
            sys.exit(0)

        old_string = tool_input.get("old_string", "")
        new_string = tool_input.get("new_string", "")

        if old_string and old_string in original_content:
            # Simulate the edit
            if tool_input.get("replace_all", False):
                new_content = original_content.replace(old_string, new_string)
            else:
                new_content = original_content.replace(old_string, new_string, 1)
        else:
            new_content = original_content

        violations = analyze_python_file(file_path, new_content)

    if violations:
        error_message = format_violations(violations)
        reason = f"Exception handler anti-patterns detected:\n{error_message}"
        print(json.dumps({"decision": "block", "reason": reason}))
        print(f"\n{error_message}", file=sys.stderr)
        sys.exit(2)

    log_debug("No violations found")
    print(json.dumps({"decision": "approve"}))
    sys.exit(0)


if __name__ == "__main__":
    main()
