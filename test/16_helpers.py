from scgraph.helpers.visvalingam import visvalingam
from pamda.pamda_timer import pamda_timer

print("\n===============\nHelper Tests:\n===============")

# Test function to format coordinates
data = [[1, 1], [2, 2], [3, 2], [4, 1], [5, 1]]
expected_output = [[1, 1], [3, 2], [4, 1], [5, 1]]
realized_output = visvalingam(data, pct_to_keep=50, min_points=3)


success = True

if realized_output != expected_output:
    print("Basic Visvalingam Test: FAIL")
    success = False
else:
    print("Basic Visvalingam Test: PASS")

timed_vsivalingam = pamda_timer(visvalingam)

# Should run in close to O(n log n) time
print("\nScale Testing Visvalingam (should be O(n log n))...")
for n in range(1, 6):
    n_act = 10**n
    data = [[i, i%2+(i/n_act)] for i in range(n_act)]
    print(f"n={n_act}", end=":"+" "*(6-n))
    timed_vsivalingam(data, pct_to_keep=0, min_points=3)