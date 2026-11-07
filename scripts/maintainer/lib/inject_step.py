#!/usr/bin/env python3
"""Insert a YAML snippet as the first step(s) of a job.

Used for act-local-only patches (e.g. recreating the .git dir that act's
fake checkout strips). Never applied to real workflow files -- the caller
operates on a scratch copy under a temp dir.

Usage: inject_step.py <workflow-file> <job-name> <snippet-file>
"""

import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: inject_step.py <workflow-file> <job-name> <snippet-file>", file=sys.stderr)
        return 2
    wf_path = Path(sys.argv[1])
    job = sys.argv[2]
    snippet = Path(sys.argv[3]).read_text()
    if not snippet.endswith("\n"):
        snippet += "\n"

    lines = wf_path.read_text().splitlines(keepends=True)
    job_idx = next((i for i, line in enumerate(lines) if line.rstrip("\n") == f"  {job}:"), None)
    if job_idx is None:
        print(f"error: job '{job}' not found in {wf_path}", file=sys.stderr)
        return 1
    steps_idx = next(
        (i for i in range(job_idx + 1, len(lines)) if lines[i].rstrip("\n") == "    steps:"),
        None,
    )
    if steps_idx is None:
        print(f"error: no 'steps:' found for job '{job}' in {wf_path}", file=sys.stderr)
        return 1

    block = [
        "      # ACT-LOCAL-BEGIN (temporary, local `act` runs only)\n",
        snippet,
        "      # ACT-LOCAL-END\n",
    ]
    lines[steps_idx + 1 : steps_idx + 1] = block
    wf_path.write_text("".join(lines))
    print(f"injected snippet into {wf_path} job '{job}'")
    return 0


if __name__ == "__main__":
    sys.exit(main())
