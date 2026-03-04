# Analysis: #253 — CLI Rendering V2 Panels

## Single stream — 4 new render functions + protocol branching

## Key Files
| File | What to change |
|------|---------------|
| `src/options_arena/cli/rendering.py` | 4 new render functions + modify render_debate_panels() |
| `tests/test_cli/test_rendering_v2.py` | NEW — 8 tests |

## Panel Colors
- Flow: bright_magenta
- Fundamental: bright_cyan
- Risk v2: bright_blue
- Contrarian: yellow
- Trend (renamed Bull for v2): green
- Verdict: blue

## Key Pattern
- Use Text() constructor, NOT markup=True (bracket crash prevention)
- Branch on result.debate_protocol == "v2"
- V2 renders: Trend → Flow → Fundamental → Volatility → Risk → Contrarian → Verdict
- V1 unchanged
