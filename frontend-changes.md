<<<<<<< HEAD
# Frontend Changes

## Feature: Light/Dark Mode Toggle Button

### Files Modified

| File | Change summary |
|------|---------------|
| `frontend/index.html` | Added `<button id="themeToggle">` with sun + moon SVG icons |
| `frontend/style.css` | Added light-theme variables, toggle button styles, icon animations, surface transitions |
| `frontend/script.js` | Added `initTheme`, `toggleTheme`, `updateToggleAriaLabel` functions and wired up the button |

---

### index.html

A fixed-position toggle button was inserted just before the closing `</body>` tag.
It contains two inline SVGs:

- **Sun icon** — visible in dark mode; clicking switches to light mode.
- **Moon icon** — visible in light mode; clicking switches to dark mode.

Both SVGs carry `aria-hidden="true"` because the button itself carries a descriptive `aria-label`.

---

### style.css

#### Light theme variables (`body[data-theme="light"]`)

Overrides the dark-mode `:root` palette with light equivalents:

| Variable | Dark value | Light value |
|----------|-----------|-------------|
| `--background` | `#0f172a` | `#f8fafc` |
| `--surface` | `#1e293b` | `#ffffff` |
| `--surface-hover` | `#334155` | `#f1f5f9` |
| `--text-primary` | `#f1f5f9` | `#0f172a` |
| `--text-secondary` | `#94a3b8` | `#64748b` |
| `--border-color` | `#334155` | `#e2e8f0` |
| `--assistant-message` | `#374151` | `#f1f5f9` |
| `--shadow` | `rgba(0,0,0,0.3)` | `rgba(0,0,0,0.08)` |

Primary/accent blue and focus-ring values are unchanged between themes.

#### `.theme-toggle` button

- `position: fixed; top: 1rem; right: 1rem` — top-right corner, above all content (`z-index: 100`).
- 40 × 40 px circular button matching the app's rounded aesthetic.
- Background and border drawn from `--surface` / `--border-color` so it always blends with the current theme.
- Hover: `scale(1.08)` + enhanced shadow.
- Active: `scale(0.93)` press-down feedback.
- Focus: `box-shadow` focus ring via `focus-visible` (keyboard-only, no ring on mouse click).

#### Icon animation

Both icons are `position: absolute; top: 50%; left: 50%`.
`transform: translate(-50%, -50%)` keeps them centred inside the button.

State machine:

| Theme | Sun | Moon |
|-------|-----|------|
| Dark (default) | `opacity: 1`, `rotate(0) scale(1)` | `opacity: 0`, `rotate(90deg) scale(0.5)` |
| Light | `opacity: 0`, `rotate(-90deg) scale(0.5)` | `opacity: 1`, `rotate(0) scale(1)` |

`transition: opacity 0.3s ease, transform 0.3s ease` drives the crossfade + spin.

#### Surface transitions

Key layout elements received `transition: background-color 0.3s ease, border-color 0.3s ease, color 0.3s ease` so the entire page colour-shifts smoothly instead of snapping.
Elements covered: `.sidebar`, `.chat-main`, `.chat-container`, `.chat-messages`, `.chat-input-container`, `.message.assistant .message-content`, `.message.welcome-message .message-content`, `.stat-item`, `.sources-collapsible`.

Elements that already had `transition: all 0.2s ease` (`.suggested-item`, `#chatInput`, `#sendButton`) inherit theme transitions for free.

---

### script.js

Three new functions added at the top of the file (before existing DOM code):

```
initTheme()           — reads localStorage and applies saved theme on page load
toggleTheme()         — flips the active theme, persists to localStorage
updateToggleAriaLabel(theme) — keeps aria-label in sync ("Switch to dark/light mode")
```

`initTheme()` is called first inside `DOMContentLoaded`, before `setupEventListeners()`, ensuring no flash of the wrong theme.

The click handler is registered inside `setupEventListeners()`:

```js
document.getElementById('themeToggle').addEventListener('click', toggleTheme);
```

Theme preference is persisted in `localStorage` under the key `"theme"` (`"light"` or `"dark"`). Default (no saved value) is dark mode.
=======
# Code Quality Tooling Changes

## Summary

Added `black` for automatic Python code formatting and created a development script for running quality checks.

---

## Files Changed

### `pyproject.toml`
- Added `[dependency-groups]` section with `black>=24.0.0` as a dev dependency
- Added `[tool.black]` configuration:
  - `line-length = 88` (black default)
  - `target-version = ["py313"]` (matches project's Python version)

### `scripts/quality.sh` (new file)
- Development script for running quality checks
- Usage:
  - `./scripts/quality.sh` — check formatting without making changes (CI-safe)
  - `./scripts/quality.sh --fix` — apply black formatting in-place

### Python files reformatted by black (9 files)
- `backend/models.py`
- `backend/app.py`
- `backend/rag_system.py`
- `backend/session_manager.py`
- `backend/search_tools.py`
- `backend/config.py`
- `backend/ai_generator.py`
- `backend/document_processor.py`
- `backend/vector_store.py`

---

## How to Use

Install dev dependencies (one-time):
```bash
uv sync --dev
```

Check formatting (no changes applied):
```bash
./scripts/quality.sh
```

Apply formatting:
```bash
./scripts/quality.sh --fix
```

Run black directly:
```bash
uv run black .          # format in-place
uv run black --check .  # check only
```
>>>>>>> quality_feature
