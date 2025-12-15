import os
import sys

from treehornx.main import main

safe_folders = [
    "benchmarks/single_pass/safe",
    #    "benchmarks/safe"
]
unsafe_folders = [
    "benchmarks/single_pass/unsafe",
    "benchmarks/unsafe",
]

for folder in safe_folders:
    files = os.listdir(folder)
    for file in files:
        file_path = os.path.join(folder, file)
        print(f"Testing file: {file_path}")
        main(["function=main", f"m=1", f"n=20", file_path])
