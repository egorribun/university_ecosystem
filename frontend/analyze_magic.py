import os
import re
from collections import Counter


def analyze_magic_values(root_dir):
    w_counter = Counter()
    h_counter = Counter()

    for root, _, files in os.walk(root_dir):
        for file in files:
            if not file.endswith(".tsx"):
                continue

            path = os.path.join(root, file)
            with open(path, encoding="utf-8") as f:
                content = f.read()

            w_matches = re.findall(r"w-\[([^\]]+)\]", content)
            h_matches = re.findall(r"h-\[([^\]]+)\]", content)

            w_counter.update(w_matches)
            h_counter.update(h_matches)

    print("Top 10 Widths:")
    for val, count in w_counter.most_common(10):
        print(f"  {val}: {count}")

    print("\nTop 10 Heights:")
    for val, count in h_counter.most_common(10):
        print(f"  {val}: {count}")


analyze_magic_values(r"c:\Users\egorribun\Documents\university_ecosystem\frontend\src")
