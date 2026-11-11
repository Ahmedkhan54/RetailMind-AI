# RetailMind AI — Reference Video Analysis

**Source:** `C:\Users\ak837\Downloads\WhatsApp Video 2026-11-09 at 1.16.35 PM.mp4`
**Extracted evidence:** `video_frames/frame_000.jpg` … `frame_020.jpg` (21 frames, 848×480, 30 fps, 41.67 s)
**Reference product on screen:** “Fernly” project dashboard — end card states *“Built in HTML, CSS & GSAP.”*

This document records what the video actually shows. It is the design contract used to check the RetailMind AI implementation. It is **not** permission to copy content, fake data, or replace RetailMind functionality.

---

## 1. Overall appearance

- Airy, light SaaS workspace. Page background is a very light cool grey/near-white; cards are pure white with soft shadows and ~10–14 px radii.
- Strong navy accent (roughly `#173b73` / `#1b3a6b`) used for primary buttons, the highlighted KPI card, active navigation, chart strokes, the gauge and the dark utility card.
- Supporting blues: mid blue (~`#4b83d5`) and pale blue (~`#a6c4f1`). Neutral greys for secondary text (~`#98a2b3`).
- Status colours: green (completed/positive), amber (in progress), purple/indigo (running), red (destructive/leave meeting).
- Typography: clean geometric sans (Inter/SF-like). Tight letter-spacing on headings, very large numeric values, small uppercase group labels in the sidebar.
- Spacing: generous page padding (~30 px desktop), 12–16 px card gutters, compact 8–10 px control spacing.
- Borders are almost invisible; separation comes from soft shadows and whitespace.

## 2. Shell layout

### Sidebar (fixed left, ~220–248 px)
- Brand lockup: rounded square mark + wordmark, top-left.
- Two or more grouped nav sections with tiny uppercase labels:
  - **MENU:** Dashboard (active), Tasks (with count badge), Calendar, Analytics, Team.
  - **GENERAL:** Settings, Help, Logout.
- Active item: pale blue pill/row with navy text and a left indicator; inactive items grey.
- Bottom promotional card (“Fernly for iOS & Android”) in dark navy with a download button.
- Sidebar is independently scrollable.

### Topbar (sticky, ~62 px)
- Global search with placeholder (“Search projects & people”) and a `⌘ K` shortcut hint.
- Inbox icon (red dot), bell icon, avatar with name + email.
- Breadcrumb/context is light and secondary.

### Page header
- Large page title (`Dashboard`, `Tasks`, `Analytics`, `Help center`) with one-line subtitle.
- Right-side actions: filled navy pill (`+ Add Project`, `+ New Task`) and outline pill (`Import Data`, `Export CSV`).

## 3. Dashboard page (frames 000–004, 017–019)

- **KPI row (4 cards):** first card is filled navy with white text; the other three are white. Each has a title, a large number, a trend/context line, and a circular arrow button in the top-right. Values visibly change between frames (24 → 23, etc.), i.e. **animated counters**.
- **Project Analytics:** bar/column chart with 7 bars. Bars alternate between solid navy/blue and **diagonal hatched/striped** light bars. Bars grow on entrance.
- **Reminders card:** heading, large navy call-to-action text, time range, full-width navy “Start Meeting” button. Later frames show the same button in red “Leave Meeting · 00:01” with a **live ticking timer**.
- **Project card:** “+ New” outline pill; list rows with a colourful brand glyph, project name and due date.
- **Team Collaboration:** member rows with circular initials, name, role, and status chips (`Completed` green, `In Progress` amber, `Running` purple).
- **Project Progress:** **semicircular gauge** with a large centred percentage (42% → 40%), label “Project Ended”, and a three-item legend with coloured dots (Completed / In Progress / Pending). The arc is animated.
- **Time Tracker:** dark navy card with a very large monospace timer (`01:24:08`), and circular pause/stop controls; digits visibly roll.
- Onboarding callout chips (“Start the timer — the digits roll”) float bottom-left.

## 4. Notifications (frames 001–002)

- Bell opens a white dropdown anchored top-right.
- Header: “Notifications” + “Mark all read”.
- Rows: circular avatar initials (green/purple/pink), actor name, action text, timestamp (“5m ago”, “32m ago”, “1h ago”).
- Red unread dot on the bell; red dot on inbox icon.

## 5. Tasks / kanban page (frames 005–009)

- Header “Tasks” with subtitle, `+ New Task` navy pill, “14 tasks shown”.
- Filter tabs: `All`, `My tasks`, `High priority`, `Due this week`; selected tab navy.
- Four columns: `To do`, `In progress`, `In review`, `Done`, each with a count.
- Cards: coloured tag (`Frontend`, `Design`, `Backend`, `Marketing`), priority (`P` High / Medium / Low), title, due date, comment/attachment counts, avatar stack, done check.
- Drag-and-drop between columns with a lifted shadow state.
- Filtering `High priority` immediately reflows the board (counts and cards animate).
- **New Task modal:** dimmed overlay, centred white card, Title, Tag, Priority, Assignee, Due date, `Cancel` + `Create task` (navy).
- Keyboard hints (`G` then `T`) are shown as keycaps.

## 6. Analytics page (frames 010–013)

- Header, period segmented control `7D / 30D (active) / 90D`, `Export CSV` outline pill.
- **KPI row with sparklines:** four cards — Tasks completed, Hours tracked, On-time delivery, Avg cycle time — each with a large value, a delta vs previous period (green/red), and a thin animated sparkline area beneath.
- **Throughput:** combo/area-line chart. Solid navy line + pale blue filled area for “This period”; dashed grey line for “Previous”. Y gridlines are extremely light. Hover shows a dashed vertical cursor and a navy tooltip card (`Fri 24 · 865h · ▲ 47.5% vs 30d`).
- **Time by project:** donut chart with a large centred value (`3,553h` / `tracked 90d`). Legend rows list colour dot, project, hours. Hovering a legend row (a) enlarges/centres that segment and swaps the centre label (e.g. `796h / Search Revamp`), (b) dims the other legend rows. This is a real hover/cross-filter interaction.
- **Activity** strip and **Top contributors** list.
- Charts re-plot smoothly when the period toggles.

## 7. Help center (frames 014–016)

- Navy gradient hero card: “How can we help?”, search field, and four category tiles (Getting started, Projects & tasks, Team, Billing & plans). Selected tile turns white.
- **FAQ accordion:** “Frequently asked” with `+` expanders; expanding shows body copy; `Show all` link.
- **Keyboard shortcuts** panel with keycaps (`⌘ K`, `/`, `G D`, `G T`, `G C`, `Esc`).
- **Still stuck?** dark navy card with `Start a chat` and `Email us` buttons.
- Selecting a topic filters the FAQ list.

## 8. Motion and interaction inventory

| Interaction | Where | Behaviour |
|---|---|---|
| Number roll-up | KPI cards, totals | Values animate from previous to new value |
| Bar growth | Project Analytics | Bars grow from baseline on load/refresh |
| Gauge sweep | Project Progress | Arc animates to percentage |
| Donut transition | Time by project | Segment grows, centre value swaps, legend highlights |
| Line draw / area fill | Throughput | Path draws in; area fades in |
| Chart re-plot | Period toggle / filters | Smooth interpolation, not a hard swap |
| Live clock | Time Tracker / meeting | Digits increment every second |
| Dropdown | Notifications | Fade/slide down |
| Modal | New task | Overlay fade + card scale-in |
| Drag & drop | Kanban | Card lifts, columns highlight |
| Accordion | Help/FAQ | Height/opacity expansion |
| Tooltips | All charts | Cursor line, floating card, delta |
| Onboarding chips | Bottom-left | Floating hints |

Motion is subtle and fast (roughly 200–600 ms), never blocking interaction, and uses transform/opacity/clip where possible.

## 9. Responsive behaviour implied by the reference

- Desktop: 248 px sidebar + fluid content, 4-up KPI row, multi-column chart grids.
- Tablet (~≤1120 px): tighter sidebar, 2-up secondary grids.
- Mobile (~≤900 px): sidebar collapses into a slide-in sheet with a hamburger; topbar compresses; search becomes an icon; KPI cards go 2-up; chart grids stack to one column; tables scroll horizontally; primary actions become full width.
- Touch targets ≥ 40 px, safe-area padding for notches, no horizontal page overflow, pinch-zoom preserved.

## 10. What RetailMind already matches

The existing Next.js frontend was already redesigned toward this language before this task continued:

- Off-white background, white cards, navy `--primary: #173b73`, chart blues, 0.7 rem radius (`frontend/src/app/globals.css`).
- Grouped sidebar with brand, active pill, scroll-position restore, active-item visibility, mobile sheet (`frontend/src/components/app-shell.tsx`).
- Topbar with breadcrumb, search + `⌘ K` hint, alerts bell, profile, sign-out.
- KPI card grid, panel cards, ranked lists, tables, empty/loading states.
- Dashboard area chart + vertical bar chart and forecast line chart use Recharts animations gated by the shared animation preference (`frontend/src/lib/animation-preference.tsx`), which combines `prefers-reduced-motion` with a user toggle.
- HttpOnly session cookie, `SameSite=Lax`, HTTPS-aware `Secure` flag, same-origin API proxy, CSP, and security headers (HSTS, nosniff, frame options, referrer policy, permissions policy).

## 11. Gap analysis (what this task adds)

1. **Video analysis artefact** — this document.
2. **Mobile security & access (Problem 61)** — CSP, explicit HTTPS/secure-cookie guidance, mobile viewport/safe-area polish, mobile upload accept types, deployment checklist.
3. **Animated charts (Problem 62)** — a shared animation preference (reduce-motion + manual off switch), animated KPI counters, animated donut with centre value and legend highlight, animated semicircle gauge, sparkline KPI cards, consistent Recharts entrance/update easing, loading states, and analytics-page charts from real API rows.
4. **Tracking matrix 60 → 62** plus a separate **reference-video design verification** row/section.
5. **Evidence** — lint/type/build and regression tests.

## 12. Visual comparison checklist (used for final verification)

| # | Check | Status |
|---|---|---|
| V1 | Light neutral canvas, white cards, navy primary, soft shadows | **PASS (static)** |
| V2 | Fixed grouped sidebar with brand, active state, scroll restore | **PASS** |
| V3 | Mobile sidebar becomes a sheet; no page overflow | **PASS (code)** — device pending |
| V4 | Sticky topbar with breadcrumb, search + shortcut, alerts, profile | **PASS** |
| V5 | Page title + subtitle + primary/outline action pills | **PASS** |
| V6 | KPI row with one emphasised card and real animated counters | **PASS** — API values, animated |
| V7 | KPI sparklines/trend context from real series | **PASS** — requires ≥2 API points |
| V8 | Bar chart with entrance growth and hover tooltip | **PASS** |
| V9 | Two-series trend (solid current, dashed/pale comparison) with area fill | **PASS** |
| V10 | Donut with centre value + legend values + hover highlight | **PASS** |
| V11 | Semicircle gauge with centre % and legend | **PASS** |
| V12 | Analytics page shows a chart plus table from real API rows | **PASS** |
| V13 | Smooth refresh/resize; native Recharts animation only | **PASS** — no extra animation library |
| V14 | Reduced-motion respected; manual “disable animations” available | **PASS** — system + Preferences toggle |
| V15 | Forecast chart still animates and remains accurate | **PASS** — same API values |
| V16 | Tables scroll on mobile; touch targets usable | **PASS (code)** — device pending |
| V17 | Mobile CSV/Excel upload works; accept/MIME handling correct | **PASS (tests)** — device pending |
| V18 | No hardcoded business figures; every number comes from the API | **PASS** |
| V19 | HTTPS/secure cookie/headers documented; no security bypass | **PASS** — see `MOBILE_SECURITY_AND_ACCESS.md` |
| V20 | Regression suite + frontend lint/build pass | **PASS** — 319 passed / 5 skipped; lint, tsc, build pass |

Legend: **PASS** = implemented and verified by code review plus automated checks. **PASS (code/tests)** = implementation and supporting tests verified, but physical-device or authenticated-browser confirmation is still listed as pending in the tracker. No item is marked PASS on the basis of an unavailable environment.

---

## Evidence notes / limitations

- Frames are 848×480 screen recordings of a stylised demo; exact hex values and fonts are approximated from the frames, not read from the reference source.
- The reference is a different product (project/task management). RetailMind keeps its own information architecture (retail analytics, datasets, forecasting, segmentation, exports). Only visual language, layout patterns, and motion behaviour are adopted.
- No physical Android/iOS device is available in this environment. Mobile behaviour is verified by responsive CSS, component review, and the existing simulated Android MIME upload tests; real-device steps are documented in `MOBILE_SECURITY_AND_ACCESS.md`.
