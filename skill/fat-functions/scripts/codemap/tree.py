"""Arrange measured files into the folder → file → function map."""

from __future__ import annotations

from collections.abc import Iterable

from codemap.measure import FileRecord, FunctionRecord

ROOT_NAME = "<root>"
MODULE_NAME = "<module>"


def build_tree(files: Iterable[FileRecord]) -> dict:
    """Return the map as nested dicts, ready for report.json.

    Every node has a `value`: the lines of code it covers on the map, and a
    folder's or file's value is the sum of its children's. A file's children
    are its functions, nested ones included, then a `<module>` block for the
    code outside any function. Run score() first so functions have a status.
    """
    root = _folder(ROOT_NAME, "")
    folders = {"": root}
    for record in sorted(files, key=lambda r: r.file):
        parent = root
        parts = record.file.split("/")
        for depth in range(1, len(parts)):
            path = "/".join(parts[:depth])
            if path not in folders:
                folders[path] = _folder(parts[depth - 1], path)
                parent["children"].append(folders[path])
            parent = folders[path]
        parent["children"].append(_file_node(record))
    _add_up(root)
    return root


def own_lines(functions: Iterable[FunctionRecord]) -> dict[str, int]:
    """Return, by id, the lines of code each function covers on its own.

    lizard leaves a nested function's body out of the outer function's count,
    but counts the line where the nested function starts in both. So each
    outer function gives up the start lines of the functions directly inside it.
    """
    functions = sorted(functions, key=lambda f: (f.start_line, -f.end_line, f.id))
    child_starts: dict[str, set[int]] = {f.id: set() for f in functions}
    enclosing: list[FunctionRecord] = []
    for function in functions:
        while enclosing and enclosing[-1].end_line < function.start_line:
            enclosing.pop()
        if enclosing and function.end_line <= enclosing[-1].end_line:
            child_starts[enclosing[-1].id].add(function.start_line)
        enclosing.append(function)
    return {f.id: max(0, f.loc - len(child_starts[f.id])) for f in functions}


def _folder(name: str, path: str) -> dict:
    return {"type": "folder", "name": name, "path": path, "value": 0, "children": []}


def _file_node(record: FileRecord) -> dict:
    sizes = own_lines(record.functions)
    children = [_function_node(f, sizes[f.id]) for f in record.functions]
    module = record.loc - sum(sizes.values())
    if module > 0:
        children.append({"type": "module", "name": MODULE_NAME, "value": module})
    return {
        "type": "file",
        "name": record.file.rsplit("/", 1)[-1],
        "path": record.file,
        "language": record.language,
        "value": sum(child["value"] for child in children),
        "children": children,
    }


def _function_node(function: FunctionRecord, value: int) -> dict:
    return {
        "type": "function",
        "id": function.id,
        "name": function.name,
        "value": value,
        "start_line": function.start_line,
        "end_line": function.end_line,
        "loc": function.loc,
        "complexity": function.complexity,
        "params": function.params,
        "forgiven": function.forgiven,
        "status": function.status,
    }


def _add_up(node: dict) -> int:
    """Set every folder's value to the sum of its children's; return it."""
    if node["type"] == "folder":
        node["value"] = sum(_add_up(child) for child in node["children"])
    return node["value"]
