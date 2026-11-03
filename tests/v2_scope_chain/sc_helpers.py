"""Helpers for the v2_scope_chain tests (never imported by the runtime).

Everything here reads Git objects or parses text that was read from Git. Nothing reads the working tree, writes a file,
uses a clock or randomness, or touches the network. Sockets are disabled on import, as in the other test packages.
The only process started is `git` with a read-only subcommand (READ_ONLY_GIT).
"""
import ast
import os
import socket
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))

READ_ONLY_GIT = frozenset({"cat-file", "ls-tree", "show", "diff", "rev-parse", "merge-base"})


class _BlockedSocket(object):
    def __init__(self, *args, **kwargs):
        raise AssertionError("network access is disabled in the tests")


def _blocked(*args, **kwargs):
    raise AssertionError("network access is disabled in the tests")


socket.socket = _BlockedSocket
socket.create_connection = _blocked


def git(*args):
    """Run one read-only git command in the repository root. Returns the CompletedProcess (text mode)."""
    assert args and args[0] in READ_ONLY_GIT, args
    return subprocess.run(("git", "-C", ROOT) + args, capture_output=True, text=True, timeout=60)


def commit_exists(sha):
    return git("cat-file", "-e", sha + "^{commit}").returncode == 0


def is_ancestor(older, newer):
    return git("merge-base", "--is-ancestor", older, newer).returncode == 0


def show(rev, path):
    """The text of path at rev (None when there is no such blob)."""
    out = git("show", "%s:%s" % (rev, path))
    return out.stdout if out.returncode == 0 else None


def list_files(rev, prefix):
    out = git("ls-tree", "-r", "--name-only", rev, prefix)
    return out.stdout.split("\n")[:-1] if out.returncode == 0 else []


def blob_id(rev, path):
    out = git("rev-parse", "%s:%s" % (rev, path))
    return out.stdout.strip() if out.returncode == 0 else None


# ---------------------------------------------------------------------------------------------- source structure

def top_level(tree):
    """{name: node} for the top-level classes, functions and single-name assignments."""
    found = {}
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef)):
            found[node.name] = node
        elif isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            found[node.targets[0].id] = node
    return found


def node_lines(node):
    """The 0-based [first, last) line span of a top-level node."""
    return node.lineno - 1, node.end_lineno


def lines_of(text, nodes):
    """The non-blank lines of text outside the spans of the given nodes."""
    skip = set()
    for node in nodes:
        first, last = node_lines(node)
        skip.update(range(first, last))
    return [line for i, line in enumerate(text.splitlines()) if i not in skip and line.strip()]


def node_text(text, node):
    first, last = node_lines(node)
    return text.splitlines()[first:last]


def is_import_io(node):
    return isinstance(node, ast.Import) and [a.name for a in node.names] == ["io"]


def test_method_names(tree):
    """Ordered 'Class.method' names of the test methods."""
    names = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name.startswith("test"):
                    names.append("%s.%s" % (node.name, item.name))
    return names


def count_calls(tree, prefix=None, exact=None):
    """The number of method calls whose attribute name starts with prefix (or equals exact)."""
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            name = node.func.attr
            if (prefix is not None and name.startswith(prefix)) or (exact is not None and name == exact):
                count += 1
    return count


# ---------------------------------------------------------------------------------------------- range tests

def _assigned(tree, name):
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) \
                and node.targets[0].id == name:
            return node.value
    return None


def _module_aliases(tree):
    aliases = {}
    for node in tree.body:
        if isinstance(node, ast.Import):
            for a in node.names:
                aliases[a.asname or a.name] = a.name
    return aliases


def read_constant(tree, name, directory, rev):
    """The value of a top-level `name = "<sha>"` / `name = None` / `name = alias.CONST` (the helper's constant is read
    from the helper file at rev). Returns (found, value)."""
    value = _assigned(tree, name)
    if value is None:
        return False, None
    if isinstance(value, ast.Constant):
        return True, value.value
    if isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name):
        module = _module_aliases(tree).get(value.value.id)
        if module:
            text = show(rev, "%s/%s.py" % (directory, module))
            if text is not None:
                inner = _assigned(ast.parse(text), value.attr)
                if isinstance(inner, ast.Constant):
                    return True, inner.value
    return True, "<unresolved>"


def range_tests(rev):
    """Every range test at rev: a tests/**/test_*.py with a top-level START and a class FilesChanged. Returns rows
    {path, start, end} in path order; end is None for an open range (END = None)."""
    rows = []
    for path in sorted(list_files(rev, "tests")):
        if not (path.endswith(".py") and os.path.basename(path).startswith("test_")):
            continue
        text = show(rev, path)
        if text is None or "FilesChanged" not in text or "START" not in text:
            continue
        tree = ast.parse(text)
        if "FilesChanged" not in top_level(tree) or not isinstance(top_level(tree)["FilesChanged"], ast.ClassDef):
            continue
        directory = os.path.dirname(path)
        has_start, start = read_constant(tree, "START", directory, rev)
        if not has_start:
            continue
        has_end, end = read_constant(tree, "END", directory, rev)
        rows.append({"path": path, "start": start, "end": end if has_end else "<missing>"})
    return rows


def judge_chain(rows, ancestor, tip="HEAD", begin=None):
    """The problems of a table of ranges (empty list = a single gap-free chain). ancestor(a, b) says whether a is an
    ancestor of (or equal to) b. tip is the revision the open range ends at; begin, when given, is the START the chain
    must begin with (a chain whose first ranges are missing is then rejected)."""
    problems = []
    starts = [r["start"] for r in rows]
    ends = [r["end"] for r in rows if isinstance(r["end"], str) and not r["end"].startswith("<")]
    for r in rows:
        if r["end"] == "<missing>":
            problems.append("no END in %s" % r["path"])
        if r["start"] == "<unresolved>" or r["end"] == "<unresolved>":
            problems.append("unresolved constant in %s" % r["path"])
    for s in sorted(set(starts)):
        if starts.count(s) > 1:
            problems.append("START %s is used more than once" % s[:8])
    opens = [r for r in rows if r["end"] is None]
    if len(opens) > 1:
        problems.append("%d open ranges (END = None)" % len(opens))
    beginnings = [r for r in rows if r["start"] not in ends]
    if len(beginnings) != 1:
        problems.append("%d chain beginnings (expected 1)" % len(beginnings))
        return problems
    by_start = {}
    for r in rows:
        by_start.setdefault(r["start"], r)
    if begin is not None and beginnings[0]["start"] != begin:
        problems.append("the chain begins at %s, not at %s" % (str(beginnings[0]["start"])[:8], begin[:8]))
    walked, current, seen = [], beginnings[0], set()
    while current is not None:
        if current["path"] in seen:
            problems.append("loop at %s" % current["path"])
            break
        seen.add(current["path"])
        walked.append(current)
        if current["end"] is None:
            break
        if isinstance(current["end"], str) and current["end"].startswith("<"):
            break
        current = by_start.get(current["end"])
    if len(walked) != len(rows):
        problems.append("the chain has a gap: %d of %d ranges are reached" % (len(walked), len(rows)))
    for i, r in enumerate(walked):
        if r["end"] is None and i != len(walked) - 1:
            problems.append("an open range is not the last one: %s" % r["path"])
        stop = tip if r["end"] is None else r["end"]
        if isinstance(stop, str) and not stop.startswith("<") and isinstance(r["start"], str):
            if not ancestor(r["start"], stop):
                problems.append("START %s is not an ancestor of %s in %s" % (r["start"][:8], str(stop)[:8], r["path"]))
            if r["end"] is not None and not ancestor(r["end"], tip):
                problems.append("END %s is not an ancestor of the tip in %s" % (r["end"][:8], r["path"]))
    return problems
