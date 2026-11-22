# Fintwin Live Market — السوق الحي

**Tagline:** شاهد مشروعك قبل أن تبنيه  
**Entry points:** every saved project detail page, every saved run row, and the curated demo detail pages.

The Live Market is a visualization layer on top of the existing Fintwin simulation. It does **not** create new persona decisions, prices, or financial estimates in the browser. The Python adapter reads the saved simulation result, normalizes it into deterministic visual events, and the renderer only displays those events.

---

## Files

### Added

| File | Purpose |
| --- | --- |
| `src/live_market.py` | Deterministic visual adapter, representative-persona selection, normalized events, behavioral/financial metrics, before/after comparison, grounded persona answers, curated demo cases, demo scenario runner. |
| `static/live-market.js` | Live Market shell, Three.js renderer, canvas 2D fallback, controls, filters, event feed, inspector, journey, grounded chat, scenario panel, comparison/split view, routing state, performance and mobile behavior. |
| `static/live-market.css` | Dark green / lime / black-and-white visual system, RTL layout, responsive rules, reduced-motion rules, project-detail entry buttons and run-history buttons. |
| `static/vendor/three.min.js` | Vendored Three.js r160 for the optional 3D stage. |
| `static/vendor/three.LICENSE` | Three.js license. |
| `LIVE_MARKET.md` | This document. |

### Modified

| File | Change |
| --- | --- |
| `app.py` | Live Market HTML routes, JSON APIs, Pydantic request models, and adapters between the existing database/service layer and `src/live_market.py`. |
| `static/index.html` | Loads `live-market.css` and `live-market.js`; adds the `#view-live` SPA section. |
| `static/app.js` | SPA route parsing for `/projects/:id/live-market` and `/demo/:id/live-market`, open/close/back navigation, project-detail hero button, run-history buttons, and deferred click handling. |
| `src/scenario.py` | Extra Arabic/Darija/English phrasing support for parking, card payment, shadda variants (`قوّي`, `خفّض`, `زوّد`), delivery price, and delivery cost changes. |

### Database

**No migration is required.** Live Market reuses the existing `projects` and `runs` tables and the existing JSON `config_json` / `result_json` payloads. Project scenarios are persisted as normal runs through `service.run_what_if`. Demo scenarios are intentionally in-memory and unsaved.

---

## Routes

### SPA pages

| Method | Route | Behavior |
| --- | --- | --- |
| `GET` | `/projects/{project_id}/live-market` | Loads the SPA; the latest saved run is used. `?run={run_id}` reopens a specific saved run. |
| `GET` | `/demo/{demo_id}/live-market` | Loads the SPA; opens a curated demo case. |

### APIs

| Method | Route | Behavior |
| --- | --- | --- |
| `GET` | `/api/projects/{project_id}/live-market?run_id=` | Returns the normalized Live Market for a saved project/run. |
| `POST` | `/api/projects/{project_id}/live-market/scenario` | Runs the existing `run_what_if` scenario system, persists a new run, preserves the baseline, returns the new Live Market and before/after comparison. |
| `POST` | `/api/projects/{project_id}/live-market/chat` | Grounded persona answer from the saved persona/decision; no LLM key required. |
| `GET` | `/api/demo/{demo_id}/live-market` | Returns a curated demo case generated with the real `simulate()` engine. |
| `POST` | `/api/demo/{demo_id}/live-market/scenario` | Reruns a demo scenario in memory and returns an explicitly unsaved comparison. |
| `POST` | `/api/demo/{demo_id}/live-market/chat` | Grounded persona answer for a demo persona, optionally against the in-memory demo scenario. |

---

## Adapter connection

```
existing DB (projects / runs)
        │
        ├─ project detail ──► Live Market button / run-history button
        │
        └─ app.live_market_for_run()
                │
                └─ build_live_market(project, run, runs=...)
                        ├─ normalized environment + locations
                        ├─ normalized persona profiles
                        ├─ deterministic event timeline (seed = persona + scenario + activity)
                        ├─ 22 representative personas max
                        ├─ behavioral + financial metrics from the saved result
                        └─ grounded persona view

scenario request
        │
        ├─ project → service.run_what_if() → persisted run → new Live Market + compare
        └─ demo    → parse_rule_based() + simulate() in memory → unsaved Live Market + compare
```

The renderer consumes normalized events with fields such as `timestamp`, `personaId`, `type`, `newState`, `location`, `reasonCodes`, `confidence`, and `financialImpact`. It never recalculates an offer price, a probability, or a financial result.

### Determinism

- Same project + scenario + dataset + seed → identical event list, persona probabilities, and metrics.
- Demo cases use fixed seeds such as `demo:noya-work-cafe`.
- Verified by requesting the same demo twice and comparing `events`, `personas`, and `metrics`.

### Demo cases

| Demo id | Environment | Seed |
| --- | --- | --- |
| `demo-street` | E-commerce / streetwear | `demo:northline-streetwear` |
| `demo-cafe` | Café / work café | `demo:noya-work-cafe` |
| `demo-local` | Clothing retail / atelier | `demo:atelier-yasmine` |
| `demo-service` | Home services / freelance | `demo:fixli-home-services` |
| `demo-food` | Restaurant / fast food | `demo:dar-box-kitchen` |

The demo set intentionally includes positive, rejection, abandonment, waiting, parking, price, trust, payment, and repeat-purchase outcomes. Not every demo is positive.

---

## Performance limits

- Three.js is loaded lazily only when a Live Market opens; the main SPA does not pay the cost.
- 100+ personas are analyzed, but at most **22 representative personas** are rendered. Legacy 12-persona runs render all 12.
- Low-poly capsule/sphere/torus/box primitives; shared geometry per repeated persona part.
- `InstancedMesh` for repeated road dashes (one draw call instead of 11).
- Shadows only outside performance mode; 1024×1024 shadow map, disabled entirely in low-performance mode.
- Name labels render only for the selected persona; non-selected/non-visible personas are culled.
- Device pixel ratio is capped (1.6 normal, 1.2 in 2D, 1.0 in low-performance Three.js).
- Performance mode disables antialiasing, shadows, and soft shadow maps.
- Animation pauses automatically when the browser tab becomes hidden and resumes when it returns.
- Mobile widths below 720 px default to the canvas 2D renderer.
- If Three.js fails to load or WebGL is unavailable, the same feed, inspector, metrics, filters, and controls continue in 2D.
- Reduced-motion preference starts the simulation paused and disables CSS animation/transitions in the shell.

---

## Accessibility and RTL

- Page and Live Market shell are RTL-first (`dir="rtl"`, Arabic labels).
- `Fintwin` is wrapped in `<bdi>` where it appears next to Arabic text.
- Controls are real `<button>` elements with labels; the canvas is focusable and supports `+`/`-` keyboard zoom.
- `Escape` clears the selected persona/event and resets the camera.
- Selected/active states use borders, labels, and position in addition to color.
- Reduced-motion media query plus runtime `prefers-reduced-motion` detection.
- Responsive layout verified at 1440×1000 and 390×844 (no horizontal overflow).

---

## Verification performed

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe -m compileall -q app.py src
node --check static/live-market.js
node --check static/app.js
.venv\Scripts\python.exe app.py
```

Validated in headless Chrome against `http://127.0.0.1:7860`:

1. Project detail → hero **افتح السوق الحي** → Live Market.
2. Project detail → saved run row → Live Market with the correct `?run=` id.
3. Direct `/projects/{id}/live-market` and `/demo/{id}/live-market` routes.
4. Demo café, clothing retail, e-commerce, service, and restaurant.
5. Saved-run reopen and run switcher inside the Live Market.
6. Filters: segment, wilaya, age group, income band, decision, payment method, new/returning.
7. Persona selection from the stage/people list; journey timeline; grounded preset chat.
8. Event feed click → persona selected, camera focused, event explanation visible.
9. Scenario preset → new run → comparison panel → split-screen before/after.
10. 2D fallback, low-performance mode, mobile viewport, reduced-motion mode.
11. API failure (missing project/run) → error state with retry button, no uncaught exception.
12. Close button and browser back navigation return to project/demo detail.
13. Missing LLM key does not affect Live Market chat; it is deterministic and grounded in saved data.
14. Same demo requested twice produces identical events, personas, and metrics.

### Screenshots

| File | Case |
| --- | --- |
| `screenshot-cafe-live.png` | Café demo, desktop 3D |
| `screenshot-retail-live.png` | Clothing retail demo, desktop 3D |
| `screenshot-ecommerce-live.png` | E-commerce demo, desktop 3D |
| `screenshot-comparison-split.png` | Café before/after split-screen |
| `screenshot-comparison-metrics.png` | Café before/after metric and persona differences |
| `screenshot-mobile-ecommerce.png` | Mobile 390×844, 2D fallback + low-performance mode |
| `screenshot-project-detail-entry.png` | Project detail entry point |
| `screenshot-project-live.png` | Saved project Live Market |
| `screenshot-cafe-comparison.png` | Café comparison in 2D |

---

## Notes / constraints

- The renderer is read-only: it visualizes saved decisions. Only an explicit scenario action triggers a new simulation.
- Project scenarios are saved as new runs and never mutate the baseline run.
- Demo scenarios are explicitly labeled **حالة عرض غير محفوظة** and are not persisted.
- Legacy runs with fewer than 22 personas are supported; the “+100 شخصية” note switches to the actual count below 100.
- The 3D stage is optional. All decision content remains available in the 2D fallback.
