import ast
import os
from collections import defaultdict
from typing import List, Tuple, Dict


CODE_DIRS = [
    os.path.join(os.getcwd(), "app"),
    os.path.join(os.getcwd(), "scripts"),
]


class FunctionCollector(ast.NodeVisitor):
    def __init__(self, source: str, filepath: str):
        self.source = source
        self.filepath = filepath
        self.stack: List[str] = []
        self.results: List[Tuple[str, str, ast.AST, int, int]] = []

    def visit_ClassDef(self, node: ast.ClassDef):
        # Enter class scope
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        # Enter function scope, collect, then visit children (for nested defs)
        self.stack.append(node.name)
        self._collect(node)
        self.generic_visit(node)
        self.stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        # Enter async function scope
        self.stack.append(node.name)
        self._collect(node)
        self.generic_visit(node)
        self.stack.pop()

    def _collect(self, node: ast.AST):
        # Build a body-only AST representation to ignore function name/decorators
        mod = ast.Module(body=node.body, type_ignores=[])
        body_dump = ast.dump(mod, include_attributes=False)

        # Determine qualname
        qualname = ".".join(self.stack) if self.stack else getattr(node, "name", "<lambda>")

        # Compute line span
        try:
            start = getattr(node, "lineno", None)
            end = getattr(node, "end_lineno", None)
        except Exception:
            start = end = None

        # Fallback for end lineno (older Python)
        if start is not None and end is None:
            # Best-effort: count lines in source segment
            segment = ast.get_source_segment(self.source, node) or ""
            end = start + segment.count("\n")

        self.results.append((
            self.filepath,
            qualname,
            mod,
            start or -1,
            end or -1,
        ))


def list_python_files(paths: List[str]) -> List[str]:
    files: List[str] = []
    for base in paths:
        if not os.path.isdir(base):
            continue
        for root, _dirs, filenames in os.walk(base):
            for name in filenames:
                if name.endswith('.py'):
                    # Skip obvious caches
                    if "__pycache__" in root:
                        continue
                    files.append(os.path.join(root, name))
    return files


def main():
    files = list_python_files(CODE_DIRS)
    by_key: Dict[str, List[Tuple[str, str, int, int]]] = defaultdict(list)
    parse_errors: List[Tuple[str, str]] = []

    for f in files:
        try:
            with open(f, 'r', encoding='utf-8') as fh:
                src = fh.read()
        except Exception:
            # Retry with latin-1 as a fallback
            try:
                with open(f, 'r', encoding='latin-1') as fh:
                    src = fh.read()
            except Exception as e:
                parse_errors.append((f, f"read_error: {e}"))
                continue

        try:
            tree = ast.parse(src, filename=f)
        except Exception as e:
            parse_errors.append((f, f"syntax_error: {e}"))
            continue

        collector = FunctionCollector(src, f)
        collector.visit(tree)
        for (path, qualname, body_mod, lineno, end_lineno) in collector.results:
            key = ast.dump(body_mod, include_attributes=False)
            by_key[key].append((path, qualname, lineno, end_lineno))

    # Print report
    dup_groups = [items for items in by_key.values() if len(items) > 1]
    print(f"Total python files scanned: {len(files)}")
    print(f"Functions analyzed: {sum(len(v) for v in by_key.values())}")
    print(f"Duplicate groups (exact body match): {len(dup_groups)}\n")

    for idx, group in enumerate(sorted(dup_groups, key=lambda g: len(g), reverse=True), 1):
        print(f"== Group {idx} (count={len(group)}) ==")
        for (path, qualname, lineno, end_lineno) in group:
            span = f"L{lineno}-{end_lineno}" if lineno != -1 and end_lineno != -1 else "L?"
            print(f"- {path} :: {qualname} ({span})")
        print()

    if parse_errors:
        print("Parse/Read issues:")
        for f, err in parse_errors[:20]:
            print(f"- {f}: {err}")
        if len(parse_errors) > 20:
            print(f"... and {len(parse_errors) - 20} more")


if __name__ == "__main__":
    main()
