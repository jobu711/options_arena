# TLDR Cache for Code Orientation

Before reading a Python file >150 lines for orientation (not for editing),
check `.claude/cache/tldr/{module}/{file}.md` first. If a fresh summary
exists, use it instead of reading the full file. Read the full file only when:
- The summary is stale or missing
- You need exact line numbers for editing
- You need to trace a specific bug

Build/refresh: `python tools/tldr_analyzer.py`
Single file: `python tools/tldr_analyzer.py --file path/to/file.py`
