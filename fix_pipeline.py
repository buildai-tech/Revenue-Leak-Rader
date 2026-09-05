import sys

path = r'frontend/src/pages/Dashboard.tsx'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the recovery pipeline array block (starting with 'Detected')
start = None
for i, line in enumerate(lines):
    if "label: 'Detected'" in line:
        start = i
        break

if start is None:
    print("ERROR: Could not find 'Detected' label")
    sys.exit(1)

# Show what we found
print(f"Found at line {start+1}:")
for j in range(start, min(start+8, len(lines))):
    print(f"  {j+1}: {lines[j].rstrip()}")

# Build the replacement block (5 stages in correct order)
indent = '              '
new_lines = [
    f"{indent}{{ label: 'Detected', count: pipeline?.detected || 0, color: 'bg-rose-500' }},\n",
    f"{indent}{{ label: 'Reviewed', count: pipeline?.reviewed || 0, color: 'bg-blue-500' }},\n",
    f"{indent}{{ label: 'Recommended', count: pipeline?.recommended || 0, color: 'bg-amber-500' }},\n",
    f"{indent}{{ label: 'Intervention Started', count: pipeline?.intervention_started || 0, color: 'bg-cyan-500' }},\n",
    f"{indent}{{ label: 'Recovered', count: pipeline?.recovered || 0, color: 'bg-emerald-500' }},\n",
]

# Count how many old pipeline lines to replace (until we hit a line that's no longer a pipeline step)
end = start
count = 0
while end < len(lines) and (start + count) < start + 6:
    if "label: '" in lines[end] and ("count: pipeline?." in lines[end]):
        count += 1
        end += 1
    else:
        break

print(f"\nReplacing {count} lines (lines {start+1} to {start+count})")

# Replace the old lines with the new ones
lines[start:start+count] = new_lines

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("DONE - file written")

# Verify
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()
if "label: 'Recovered (Interventions)'" in content:
    print("WARNING: stale 'Recovered (Interventions)' still present")
else:
    print("OK: no stale 'Recovered (Interventions)' label")
