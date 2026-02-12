import glob
import os
import re
from collections import Counter


def analyze_opacity(root_dir):
    opacity_counter = Counter()

    # Regex for finding class strings
    class_regex = re.compile(r'class(Name)?=["\'`]([^"\'`]+)["\'`]')

    # Regex for finding opacity modifiers (e.g., /10, /20, /[0.5])
    # Matches: bg-black/20, text-white/50, border-red-500/[0.1]
    # Also matches: opacity-50, opacity-[0.5]
    opacity_mod_regex = re.compile(r"\/(\d+|\[[^\]]+\])")
    opacity_util_regex = re.compile(r"\bopacity-(\d+|\[[^\]]+\])")

    print(f"Scanning {root_dir}...")

    for ext in ["*.tsx", "*.ts"]:
        for file_path in glob.glob(os.path.join(root_dir, "**", ext), recursive=True):
            try:
                with open(file_path, encoding="utf-8") as f:
                    content = f.read()

                    # Find all class strings
                    matches = class_regex.findall(content)
                    for _, class_string in matches:
                        classes = class_string.split()
                        for cls in classes:
                            # Check for slash opacity
                            mod_match = opacity_mod_regex.search(cls)
                            if mod_match:
                                opacity_counter[mod_match.group(1)] += 1

                            # Check for opacity utility
                            util_match = opacity_util_regex.search(cls)
                            if util_match:
                                opacity_counter[util_match.group(1)] += 1

            except Exception as e:
                print(f"Error reading {file_path}: {e}")

    print("\nTop Opacity Values:")
    for value, count in opacity_counter.most_common(20):
        print(f"  {value}: {count}")


if __name__ == "__main__":
    analyze_opacity(r"c:\Users\egorribun\Documents\university_ecosystem\frontend\src")
