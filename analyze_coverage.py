import xml.etree.ElementTree as ET

tree = ET.parse('coverage.xml')
root = tree.getroot()

print(f"Lines: {root.get('lines-covered')} / {root.get('lines-valid')} = {root.get('line-rate')}")
print(f"Branches: {root.get('branches-covered')} / {root.get('branches-valid')} = {root.get('branch-rate')}")

cls = sorted([c for c in root.findall('.//class')], key=lambda c: float(c.get('line-rate', '1')))
print("\nWorst 40 files (lowest coverage):")
for c in cls[:40]:
    fname = c.get('filename')
    lrate = float(c.get('line-rate', '1'))
    lines = c.findall('.//line')
    unhit = [l.get('number') for l in lines if l.get('hits') == '0']
    print(f"  {fname}: {lrate:.2%} (unhit lines: {len(unhit)})")
