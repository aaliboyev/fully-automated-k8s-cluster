"""Check one node's LINSTOR replicas from `linstor -m resource list` on stdin.

before: every volume with a disk on the node has another UpToDate replica.
after:  every replica on the node is UpToDate or Diskless.
Prints offending volumes and exits 1 if any.
"""
import json
import sys

node, mode = sys.argv[1], sys.argv[2]
replicas = {}
for res in json.load(sys.stdin)[0]:
    for vol in res["volumes"]:
        state = vol.get("state", {}).get("disk_state")
        replicas.setdefault((res["name"], vol["volume_number"]), {})[res["node_name"]] = state

bad = []
for (name, number), states in replicas.items():
    own = states.get(node)
    if own is None:
        continue
    if mode == "before":
        others = [n for n, s in states.items() if n != node and s == "UpToDate"]
        if own != "Diskless" and not others:
            bad.append(f"{name}/{number}: no UpToDate replica besides {node} ({states})")
    elif own not in ("UpToDate", "Diskless"):
        bad.append(f"{name}/{number}: {node} is {own}")

print("\n".join(bad))
sys.exit(bool(bad))
