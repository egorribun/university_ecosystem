import ast
import os

models_dir = "app/models"
relationships = []
missing_noload = []

for root, _, files in os.walk(models_dir):
    for file in files:
        if not file.endswith(".py"):
            continue
        filepath = os.path.join(root, file)
        with open(filepath, encoding="utf-8") as f:
            lines = f.readlines()
            content = "".join(lines)

        try:
            tree = ast.parse(content, filename=filepath)
        except (
            Exception
        ) as e:  # RZ-22-01-JUSTIFIED: audit script parsing failure report
            print(f"Error parsing {filepath}: {e}")
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = None
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    func_name = node.func.attr

                if func_name == "relationship":
                    has_lazy = False
                    lazy_val = None
                    for kw in node.keywords:
                        if kw.arg == "lazy":
                            has_lazy = True
                            if isinstance(kw.value, ast.Constant):
                                lazy_val = kw.value.value

                    lineno = node.lineno
                    end_lineno = getattr(node, "end_lineno", lineno)
                    in_range = [
                        lines[idx]
                        for idx in range(
                            max(0, lineno - 3), min(len(lines), end_lineno + 3)
                        )
                    ]
                    is_exempt = any("noload-exempt" in line for line in in_range)

                    rel_info = {
                        "file": filepath,
                        "line": lineno,
                        "has_lazy": has_lazy,
                        "lazy_val": lazy_val,
                        "is_exempt": is_exempt,
                    }
                    relationships.append(rel_info)
                    if (not has_lazy or lazy_val != "noload") and not is_exempt:
                        missing_noload.append(rel_info)

print(f"Total relationship() calls found in app/models: {len(relationships)}")
print(f'Relationships missing lazy="noload" or exempt: {len(missing_noload)}')
for r in relationships:
    print(
        f"  {r['file']}:{r['line']} -> lazy={r['lazy_val']!r} exempt={r['is_exempt']}"
    )
