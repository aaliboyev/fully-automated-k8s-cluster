"""Writes every dashboard as JSON next to this directory.

Run: python3 components/observability/dashboards/src/build.py
The JSON is committed; the chart turns each file into a ConfigMap whose
folder is the directory name.
"""
import json
import pathlib

import edge
import home
import private_gateway
import node
import platform_board
import storage
import workload

OUT = pathlib.Path(__file__).resolve().parent.parent
BOARDS = {"cluster": [home, node, workload, private_gateway, edge, storage, platform_board]}

for folder, modules in BOARDS.items():
    (OUT / folder).mkdir(exist_ok=True)
    for m in modules:
        board = m.build().json()
        (OUT / folder / f"{board['uid']}.json").write_text(json.dumps(board, indent=2) + "\n")
        print(f"{folder}/{board['uid']}.json")
