# UI/UX AUDIT AND DESIGN PLAN - Career Intelligence System

**Date:** 2026-10-27  
**Auditor:** AI Design Agent  
**Scope:** Frontend redesign of Career Intelligence System (thesis project)

---

## 1. FRONTEND STACK & DIRECTORY STRUCTURE

### Stack
- **Framework:** React 18.3.1
- **Build Tool:** Vite 5.4.0
- **Language:** TypeScript 5.5.4
- **Router:** None (custom state-based navigation in App.tsx)
- **Styling:** Plain CSS with CSS variables (styles.css)
- **UI Libraries:** None (fully custom components)
- **HTTP:** Native fetch API
- **Testing:** Vitest 2.0.5

### Directory Structure
```
frontend/
├── src/
│   ├── App.tsx           # Main app with navigation state
│   ├── components.tsx    # Shared components (ErrorAlert, StatusBanner, Tag, Section, etc.)
│   ├── components.test.tsx
│   ├── main.tsx          # Entry point
│   ├── pages.tsx         # All page components
│   ├── styles.css        # Global styles
│   ├── hooks/            # Custom hooks (empty/minimal)
│   ├── pages/            # Additional page files (separate from pages.tsx)
│   ├── services/
│   │   └── api.ts        # API client
│   └── types/
│       └── api.ts        # Type definitions
├── dist/                 # Build output
├── index.html
├── package.json
└── vite.config.ts
```

### Notes
- Pages are defined in both `pages.tsx` (used by App) and there might be files in `pages/` directory - need to check.
- No routing library, all navigation via React state
- API proxied to `http://127.0.0.1:8000` via Vite

---

## 2. EXISTING SCREENS & USER JOURNEY

### Current Screens (from App.tsx)
1. **Home** - User creation/selection, health check, analysis trigger (profile or CV)
2. **User Profile** - Shows run metadata (limited due to no profile-read endpoint)
3. **Skills & Evidence** - Skill gap breakdown by categories
4. **Career Recommendations** - Ranked list with fit scores
5. **Skill Gap** - Detailed skill gap with narrative explanation
6. **Learning Roadmap** - Actionable items from skill gaps
7. **Evidence / Sources** - Source/provenance info
8. **Analysis Details** - Verification details and scoring weights

### Current User Journey
1. User lands on Home → checks backend health
2. Creates new user or selects existing user ID
3. Optionally specifies target career ID
4. Runs analysis via "Analyze stored profile" or "Upload CV and analyze"
5. On success, auto-navigates to "Career Recommendations"
6. Can navigate to other tabs to see details

### API Integration
- `GET /health`
- `POST /analysis/users` (create user)
- `POST /analysis/profile` (analyze with stored profile)
- `POST /analysis/cv` (analyze with CV upload)
- All return `AnalysisResponse` type

---

## 3. MAIN UI/UX PROBLEMS FOUND

### Navigation & Layout
- **Issue:** Header is very basic - just "Career Intelligence (research prototype)" with simple button nav
- **Issue:** No clear visual hierarchy, everything looks equally weighted
- **Issue:** No branding/identity, feels like internal tool
- **Issue:** Page title shown twice (in header context and as `<h2>{page}</h2>`)
- **Files:** `App.tsx:47-53`

### Home Page
- **Issue:** Very text-heavy, walls of labels/inputs with minimal visual grouping
- **Issue:** "Research prototype. Results are held in browser memory only..." warning is buried as paragraph
- **Issue:** No clear call-to-action, actions are scattered
- **Issue:** File input styling is browser-default and ugly
- **Issue:** No explanation of what the app does for first-time users
- **Issue:** Health check is separate from main flow
- **Files:** `pages.tsx:11-44`

### Typography & Spacing
- **Issue:** Very tight spacing, cramped layout
- **Issue:** System font stack only - functional but not polished
- **Issue:** No type scale - all text similar size
- **Issue:** Line heights/spacing inconsistent
- **Files:** `styles.css:3-4`

### Components
- **Issue:** Tables are not responsive well (overflow-x works but styling minimal)
- **Issue:** Cards have basic borders, no shadows/elevation
- **Issue:** Buttons have minimal styling - no hover states beyond cursor
- **Issue:** Tags use symbols (✓ △ ✗ ?) which are fine but need better visual treatment
- **Issue:** Section component just wraps with `<h2>` - not very distinct
- **Files:** `components.tsx`, `styles.css:6-15`

### Information Architecture
- **Issue:** "User Profile" tab shows mostly unavailable/metadata - confusing name
- **Issue:** "Skills & Evidence" vs "Skill Gap" - overlap in content
- **Issue:** Evidence/Sources tab is sparse
- **Issue:** No clear flow indication of where user is in process
- **Issue:** Tabs are all visible even when no analysis done (except body shows message)

### Empty/Error States
- **Issue:** ErrorAlert is functional but basic styling
- **Issue:** "No analysis yet. Run one from Home." is plain text
- **Issue:** Unavailable component is just a card with muted class

### Visual Design
- **Issue:** No color system beyond CSS variables - very utilitarian
- **Issue:** No icons
- **Issue:** No visual feedback for interactions
- **Issue:** Dark mode exists but not very polished
- **Issue:** Overall looks like a prototype, not thesis-demo ready

---

## 4. PROPOSED VISUAL DIRECTION & COLOR PALETTE

### Design Philosophy
**"Professional Academic SaaS"** - Clean, modern, trustworthy. Should feel polished enough for university thesis demonstration while remaining accessible and functional. Think modern career platforms (LinkedIn-style) but more focused and academic.

### Color Palette
I'll use a professional blue/indigo primary with semantic colors that are accessible.

**Light Mode (Default):**
```css
--bg: #ffffff
--bg-subtle: #f8fafc        /* Subtle backgrounds */
--bg-elevated: #ffffff      /* Cards, modals */
--fg: #0f172a              /* Primary text - slate-900 */
--fg-muted: #475569        /* Secondary text - slate-600 */
--fg-subtle: #64748b       /* Tertiary text - slate-500 */
--border: #e2e8f0          /* slate-200 */
--border-strong: #cbd5e1   /* slate-300 */
--primary: #2563eb         /* blue-600 */
--primary-hover: #1d4ed8   /* blue-700 */
--primary-foreground: #ffffff
--accent: #6366f1          /* indigo-500 */
--ok: #16a34a              /* green-600 */
--warn: #ea580c            /* orange-600 */
--bad: #dc2626             /* red-600 */
--info: #0891b2            /* cyan-600 */
```

**Dark Mode:**
```css
--bg: #020617              /* slate-950 */
--bg-subtle: #0f172a       /* slate-900 */
--bg-elevated: #1e293b     /* slate-800 */
--fg: #f1f5f9              /* slate-100 */
--fg-muted: #cbd5e1        /* slate-300 */
--fg-subtle: #94a3b8       /* slate-400 */
--border: #334155          /* slate-700 */
--border-strong: #475569   /* slate-600 */
--primary: #3b82f6         /* blue-500 */
--primary-hover: #2563eb   /* blue-600 */
--primary-foreground: #ffffff
--accent: #6366f1
--ok: #22c55e
--warn: #fb923c
--bad: #f87171
--info: #22d3ee
```

**Rationale:** Professional blue conveys trust/competency. Slate grays for neutral. Semantic colors are clear and accessible (WCAG AA compliant).

### Typography
- **Font Family:** Inter, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Helvetica Neue', sans-serif
- **Scale:**
  - Display: 2.25rem (36px) / 2.5rem line-height
  - H1: 1.875rem (30px) / 2.25rem
  - H2: 1.5rem (24px) / 2rem
  - H3: 1.25rem (20px) / 1.75rem
  - H4: 1.125rem (18px) / 1.75rem
  - Body: 1rem (16px) / 1.75rem
  - Small: 0.875rem (14px) / 1.5rem
  - XSmall: 0.75rem (12px) / 1rem
- **Weights:** 400, 500, 600, 700
- **Note:** Inter is widely available and excellent for UI. Can use system fonts as fallback. Will add Google Fonts import or use system stack with better fallbacks.

### Spacing Scale (4pt grid)
```css
--space-1: 0.25rem (4px)
--space-2: 0.5rem (8px)
--space-3: 0.75rem (12px)
--space-4: 1rem (16px)
--space-5: 1.25rem (20px)
--space-6: 1.5rem (24px)
--space-8: 2rem (32px)
--space-10: 2.5rem (40px)
--space-12: 3rem (48px)
--space-16: 4rem (64px)
```

### Border Radius
```css
--radius-sm: 0.375rem (6px)
--radius-md: 0.5rem (8px)
--radius-lg: 0.75rem (12px)
--radius-xl: 1rem (16px)
```

### Shadows
```css
--shadow-sm: 0 1px 2px 0 rgb(0 0 0 / 0.05)
--shadow: 0 1px 3px 0 rgb(0 0 0 / 0.1), 0 1px 2px -1px rgb(0 0 0 / 0.1)
--shadow-md: 0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)
--shadow-lg: 0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)
```

---

## 5. PROPOSED NAVIGATION & PAGE HIERARCHY

### New Navigation Structure
- **App Header:** Logo/title, user context (if user selected), status indicator
- **Primary Nav:** Horizontal tabs with icons, clearer active state
- **Breadcrumbs:** Optional for deeper pages
- **Page Layout:** Max-width container, consistent padding, better spacing

### Reorganized Information Architecture
Keep existing pages but improve grouping and naming clarity:

1. **Beranda / Home** - Dashboard/landing with clear CTAs
2. **Profil & Analisis** (or keep separate) - User setup and analysis trigger
3. **Rekomendasi Karir** - Career recommendations (primary result)
4. **Kesenjangan Skill** - Skill gap analysis (combined view)
5. **Roadmap Pembelajaran** - Learning roadmap
6. **Bukti & Sumber** - Evidence/transparency
7. **Detail Analisis** - Technical details/verification

But better to keep English to match codebase, just improve presentation.

### Navigation Improvements
- Show navigation only after user is set up? Or always show but disable unavailable tabs
- Add visual indicators for tabs that need data
- Better mobile navigation (stack vertically or hamburger if needed)
- Show current step in journey

---

## 6. SCREEN-BY-SCREEN REDESIGN PLAN

### A. App Shell (App.tsx, components.tsx)
**Changes:**
- Redesign header with better branding
- Improve nav with better active states, icons optional
- Add container layout with max-width and padding
- Improve error/status display positioning
- Add subtle background

**Components to create/update:**
- `Layout` component
- `Header` component
- `Nav` component

### B. Home Page (pages.tsx)
**Changes:**
- Hero section explaining the app
- Card-based layout for actions
- Better form styling
- Health check as subtle indicator
- Clear step-by-step flow (1. Create/select user, 2. Run analysis)
- Improved file upload UI
- Add icons for visual clarity
- Better empty states

### C. Career Recommendations
**Changes:**
- Card grid or improved card layout
- Better fit score visualization (progress bar instead of just meter)
- Skill pills/badges with better styling
- Clear CTA buttons
- "Why this recommendation" section
- Ranking visualization

### D. Skill Gap Analysis
**Changes:**
- Summary stats at top
- Better categorization with icons
- Expandable/collapsible sections
- Improved table design
- Clear "evidenced vs claimed" distinction
- Better empty states

### E. Learning Roadmap
**Changes:**
- Timeline/step-by-step visual
- Card per item with clear hierarchy
- Action indicators
- Better spacing

### F. Evidence/Sources & Details
**Changes:**
- Cleaner presentation
- Better use of progressive disclosure
- Improved verification status display

---

## 7. SHARED COMPONENTS & DESIGN TOKENS

### New/Improved Components
Create in `components.tsx` or new files:

1. **Button** - variants (primary, secondary, ghost, outline), sizes, states
2. **Input** - with labels, help text, error states
3. **Card** - with header, body, footer
4. **Badge/Tag** - improved styling
5. **Section** - redesigned
6. **Alert** - better variants
7. **Table** - improved responsive table
8. **EmptyState** - for when no data
9. **LoadingState** - spinner
10. **ProgressBar** - for scores
11. **Icon** - simple SVG icons or use inline

### Design Tokens
Move all tokens to CSS custom properties in `:root` and `[data-theme="dark"]` or use `prefers-color-scheme`

### Utility Classes
Add classes for flexbox, grid, spacing, typography

---

## 8. USABILITY & ACCESSIBILITY RISKS

### Risks & Mitigations
- **Color contrast:** Need to ensure all text meets WCAG AA (4.5:1). Test with new palette.
- **Keyboard navigation:** Ensure all buttons/links focusable, tab order logical
- **Screen readers:** Add proper ARIA labels, use semantic HTML
- **Motion:** Respect `prefers-reduced-motion`
- **Form accessibility:** Labels associated with inputs, error messages linked
- **Tables:** Add captions or proper headers
- **Focus indicators:** Already have `:focus-visible` but need to ensure visible on all backgrounds

---

## 9. FILES LIKELY TO BE MODIFIED

### Core Files
- `frontend/src/styles.css` - Complete redesign of styles
- `frontend/src/App.tsx` - Layout and navigation improvements
- `frontend/src/components.tsx` - Component redesign + new components
- `frontend/src/pages.tsx` - All page redesigns
- `frontend/index.html` - Add font imports if needed
- `frontend/src/main.tsx` - Possibly add theme provider

### Possibly New Files
- `frontend/src/components/Layout.tsx`
- `frontend/src/components/Button.tsx`
- `frontend/src/components/Card.tsx`
- `frontend/src/components/Input.tsx`
- `frontend/src/components/icons.tsx`

But better to keep changes minimal and consolidate where possible.

---

## 10. VERIFICATION PLAN

### Automated Checks
1. `npm run typecheck` - TypeScript compilation
2. `npm run build` - Production build
3. `npm run test` - Run tests (components.test.tsx exists)
4. `npm run lint` if available

### Manual Checks
1. **Responsive:** Test at 375px (mobile), 768px (tablet), 1024px+, 1440px
2. **Navigation:** All tabs work, state preserved correctly
3. **Forms:** Validation, submission, error states
4. **Data display:** All existing data renders correctly
5. **API integration:** No changes to API calls
6. **Accessibility:** Keyboard nav, focus states, contrast
7. **Dark mode:** Test if system preference works
8. **Empty states:** Test with no data
9. **Error states:** Simulate errors

### Browser Testing
If possible, run dev server and test in browser. Note limitations if not possible.

---

## IMPLEMENTATION APPROACH

### Phase 2 Priority (as per instructions)
1. Main layout and navigation
2. Primary user journey (Home)
3. Career recommendation presentation
4. Skill-gap presentation
5. Learning roadmap presentation
6. Forms, validation, loading, empty, error, success states
7. Responsive behavior
8. Accessibility and visual consistency
9. Small interaction improvements

### Principles
- **Preserve functionality:** No backend changes, no API contract changes
- **Minimal dependencies:** Use only what's available
- **Progressive enhancement:** Keep existing logic intact
- **Consistent:** Use design tokens everywhere
- **Accessible:** Follow WCAG guidelines
- **Performant:** No heavy animations

---

**Ready to proceed with implementation after review.** All changes will be frontend-only, preserving existing API contracts and business logic.
