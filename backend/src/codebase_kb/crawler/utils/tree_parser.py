from collections import defaultdict

def build_tree(paths):
    tree = {}

    for path in paths:
        parts = path.split("/")
        current = tree

        for part in parts:
            current = current.setdefault(part, {})

    return tree


def print_tree(tree, prefix=""):
    items = list(tree.items())

    for i, (name, subtree) in enumerate(items):
        is_last = i == len(items) - 1

        connector = "└── " if is_last else "├── "
        print(prefix + connector + name)

        extension = "    " if is_last else "│   "
        print_tree(subtree, prefix + extension)