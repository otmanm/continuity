# Tested

## Clean install from GitHub, 2026-10-25

The two install commands from the README were run on the author's Mac against the public repository, in an empty Claude Code configuration folder (`CLAUDE_CONFIG_DIR` set to a new scratch folder). The author's own Claude setup was not used and its plugin files kept the same hash before and after.

| Step | Command | Result |
|---|---|---|
| 1 | `claude plugin marketplace add otmanm/continuity` | Cloned https://github.com/otmanm/continuity.git, "Successfully added marketplace: agent-continuity" |
| 2 | `claude plugin install continuity@agent-continuity` | "Successfully installed plugin: continuity@agent-continuity (scope: user)" |
| 3 | `claude plugin list` | `continuity@agent-continuity`, version 0.2.0, enabled |
| 4 | `python3 examples/check_example.py`, run inside the installed copy | `ALL 12 CHECKS PASS` |

Environment: macOS 27.0.1, Claude Code 2.1.310, Python 3.14.2. The installed copy holds the four skills: checkpoint, context-closeout, conversation-record, handoff.

The test ran on version 0.2.0, the version on GitHub at the time. Version 0.2.1 changes only the README, the CHANGELOG, the version number and one comment.

## Not tested yet

- Linux and Windows.
- The skills running inside a real Claude Code session after this clean install.
- The Codex copies installed on a machine other than the author's.
