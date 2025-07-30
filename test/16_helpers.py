from scgraph.helpers.visvalingam import visvalingam
from scgraph.helpers.kd_tree import KDTree
from pamda.pamda_timer import pamda_timer
from time import time

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


print("\nScale Testing KDTree...")
for n in range(1, 7):
    n_act = 10**n
    nodes = [(i, i+1) for i in range(n_act)]
    start_time = time()
    kd_tree = KDTree(nodes)
    print(f"n={n_act} KD-Tree built in {round((time() - start_time) * 1000, 4)} ms")
    start_time = time()
    closest_point = kd_tree.closest_point((5,5.5))
    print(f"n={n_act} KD-Tree found in {round((time() - start_time) * 1000, 4)} ms")
    if closest_point != (5, 6):
        print(f"KD-Tree closest point test failed for n={n_act}")
        success = False