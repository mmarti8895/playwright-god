# Playwright End-to-End Test Plan

## Overview

This repository appears to be a small static-site style app with client-side behavior concentrated in:

- `index.html`
- `app.js`
- `styles.css`

The indexed feature map strongly suggests these user-facing areas:

- Authentication
- Todo Management
- Navigation
- Profile and Settings

There are also lower-confidence areas:

- CLI Workflow
- Test Generation

Because the memory map does not expose concrete route strings, DOM selectors, or API URLs, this plan includes:

- **high-confidence user flows**
- **recommended selector strategy**
- **runtime discovery tasks** to confirm routes, selectors, and storage/network behavior before implementation

---

## Assumptions and Test Strategy

### Likely app shape
Given the repository profile (`static-site`) and limited file count, the app is likely one of:

- a single-page app with conditional sections
- a static HTML page with JS-driven view switching
- localStorage/sessionStorage-backed state rather than a real backend

### Recommended Playwright approach
Use a layered E2E strategy:

1. **Smoke tests**
   - App loads
   - Core UI visible
   - Main flows work

2. **Feature tests**
   - Authentication
   - Todo CRUD
   - Profile/settings
   - Navigation

3. **State and resilience tests**
   - Persistence after reload
   - Validation and error states
   - Session transitions

### Runtime discovery checklist
Before implementing tests, inspect the app for:

- actual routes or hash routes:
  - `/`
  - `/login`
  - `/todos`
  - `/profile`
  - `/settings`
  - or `#/login`, `#/todos`, etc.
- form controls:
  - email/username input
  - password input
  - todo input
  - add button
  - complete checkbox/button
  - delete button
  - logout button
- storage usage:
  - `localStorage`
  - `sessionStorage`
- network calls:
  - `fetch(...)`
  - XHR endpoints
- stable selectors:
  - `data-testid`
  - semantic roles and labels

---

# Feature Area: Authentication

**Confidence:** High  
**Evidence:** `app.js`, `index.html`, `styles.css`

## Target routes and actions to cover
Because no flow graph or explicit routes were provided, target these likely auth surfaces:

- **Routes/views:** login screen, authenticated home/todo view, logout transition
- **Actions:** sign in, invalid sign in, session persistence, access gating

## Special setup
- May require seeded credentials if auth is hardcoded in `app.js`
- If auth is local-only, tests may need to:
  - fill known credentials discovered from source
  - or mock browser storage state
- If auth uses network requests, intercept with `page.route()` and mock responses

## Suggested scenarios

### 1. User can sign in with valid credentials
**Goal:** Verify successful authentication and transition into the app.

**Steps**
- Open the app entry route
- Fill username/email and password
- Submit the sign-in form
- Verify authenticated content is shown

**Assertions**
- Login form disappears or becomes hidden
- Todo workspace or main app shell becomes visible
- User-specific UI appears, such as profile/settings/logout

**Selectors to look for**
- `input[type="email"]`, `input[name="email"]`, `input[name="username"]`
- `input[type="password"]`
- `button[type="submit"]`
- text like `Login`, `Sign In`

**Confidence signals**
- Authentication is the highest-confidence feature area
- Suggested opportunity explicitly includes valid sign-in

---

### 2. Invalid credentials show an actionable error
**Goal:** Ensure failed login gives clear feedback and does not authenticate the user.

**Steps**
- Open login view
- Enter invalid credentials
- Submit form

**Assertions**
- Error message is visible and readable
- User remains on login view
- Protected content is not shown
- Submit button remains usable for retry

**Selectors to look for**
- error container near form
- alert role: `[role="alert"]`
- inline validation text

**Potential implementation**
- If auth is mocked, return `401` or equivalent failure
- If auth is local-only, use known invalid values

---

### 3. Unauthenticated user is blocked from protected content
**Goal:** Verify access gating.

**Steps**
- Open app without prior auth state
- Attempt to access the main workspace route/view directly if one exists

**Assertions**
- User is redirected to login or shown login section
- Todo list/profile/settings are hidden until sign-in

**Routes to probe**
- `/`
- `/todos`
- `/profile`
- hash-based equivalents

**Special note**
- This is especially important if the app conditionally renders sections in a single page

---

### 4. Authenticated session persists after page reload
**Goal:** Confirm session continuity.

**Steps**
- Sign in successfully
- Reload the page

**Assertions**
- User remains authenticated
- Main workspace is still visible
- Login form does not reappear unexpectedly

**Confidence signals**
- Static-site apps often use `localStorage` or `sessionStorage`
- This is a high-value regression test for client-side auth

---

### 5. User can sign out and return to the login state
**Goal:** Verify session teardown.

**Steps**
- Sign in
- Open settings/profile if needed
- Click logout/sign out

**Assertions**
- User returns to login state
- Protected content is hidden
- Reload does not restore authenticated state unless intended

**Selectors to look for**
- `button:has-text("Logout")`
- `button:has-text("Sign Out")`
- profile/settings menu trigger

---

# Feature Area: Todo Management

**Confidence:** High  
**Evidence:** `app.js`, `index.html`, `styles.css`

## Target routes and actions to cover
Likely uncovered targets:

- **Routes/views:** main todo workspace, authenticated home/dashboard
- **Actions:** add todo, mark complete, delete todo, persistence, validation

## Special setup
- Likely requires authenticated state first
- If todos are persisted in localStorage, tests should isolate state per test
- If todos use API calls, intercept create/update/delete endpoints

## Suggested scenarios

### 1. User can add a todo item
**Goal:** Verify creation of a new task from the primary workspace.

**Steps**
- Sign in if required
- Enter a unique todo title
- Submit via add button or Enter key

**Assertions**
- New todo appears in the list
- Item text matches input
- Input clears after submission
- Item count increases if count UI exists

**Selectors to look for**
- todo input: `input[placeholder*="todo"]`, `input[name="todo"]`
- add button: `button:has-text("Add")`
- list container: `ul`, `ol`, `.todo-list`

**Confidence signals**
- Explicitly listed in suggested opportunities

---

### 2. Empty todo submission is prevented
**Goal:** Ensure basic validation.

**Steps**
- Focus todo input
- Submit with empty value or whitespace only

**Assertions**
- No new item is created
- Validation message appears or submit is ignored
- Existing list remains unchanged

**Why this matters**
- Common regression in simple JS todo apps
- High ROI for client-side validation

---

### 3. User can mark a todo item as complete
**Goal:** Verify update behavior.

**Steps**
- Create a todo
- Click its checkbox/toggle/complete button

**Assertions**
- Item shows completed styling
- Checkbox/toggle state changes
- If app separates active/completed items, item moves appropriately

**Selectors to look for**
- `input[type="checkbox"]`
- complete button/icon within todo row
- completed class such as `.completed`

---

### 4. User can delete a todo item
**Goal:** Verify removal behavior.

**Steps**
- Create a todo
- Click delete/remove control for that item

**Assertions**
- Item is removed from DOM
- List count decreases
- Deleted item does not reappear after reload unless deletion failed

**Selectors to look for**
- `button:has-text("Delete")`
- icon buttons inside todo row
- row-level action controls

**Confidence signals**
- Explicitly listed in suggested opportunities as part of complete/delete flow

---

### 5. Todo state persists after reload
**Goal:** Confirm client-side persistence.

**Steps**
- Sign in
- Add one or more todos
- Optionally complete one
- Reload page

**Assertions**
- Todos remain visible after reload
- Completion state is preserved
- No duplicate items are created

**Special note**
- Particularly valuable if `app.js` uses localStorage

---

# Feature Area: Navigation

**Confidence:** Medium  
**Evidence:** `app.js`, `index.html`

## Target routes and actions to cover
Likely uncovered targets:

- **Routes/views:** login, todos/home, profile, settings
- **Actions:** move between primary sections, preserve state while navigating

## Special setup
- Some navigation targets may only appear after authentication
- If this is a single-page app, navigation may be tab/section based rather than URL based

## Suggested scenarios

### 1. User can navigate between primary pages
**Goal:** Verify main app navigation works.

**Steps**
- Sign in
- Click each primary nav item available:
  - Home/Todos
  - Profile
  - Settings

**Assertions**
- Correct section becomes visible after each click
- Active nav state updates
- URL or hash changes if routing is implemented

**Selectors to look for**
- `nav a`
- buttons or tabs with labels like `Home`, `Todos`, `Profile`, `Settings`

**Confidence signals**
- Explicitly listed in suggested opportunities

---

### 2. Direct navigation to a section shows the correct content
**Goal:** Verify route/view rendering from direct entry.

**Steps**
- Open likely section routes directly in a new page context

**Assertions**
- Correct section loads for authenticated users
- Unauthenticated users are redirected or gated appropriately

**Routes to probe**
- `/`
- `/profile`
- `/settings`
- `/todos`
- hash route equivalents

---

### 3. Navigation preserves existing todo state
**Goal:** Ensure moving between sections does not reset workspace state.

**Steps**
- Sign in
- Add a todo
- Navigate to profile/settings
- Return to todos/home

**Assertions**
- Previously added todo is still present
- No duplicate rendering or reset occurs

---

# Feature Area: Profile and Settings

**Confidence:** High  
**Evidence:** `app.js`, `index.html`

## Target routes and actions to cover
Likely uncovered targets:

- **Routes/views:** profile page/section, settings page/section
- **Actions:** view profile details, sign out, possibly edit preferences if present

## Special setup
- Requires authenticated state
- If profile data is static or hardcoded, assert visible labels/values rather than backend behavior
- If profile data is fetched, mock the profile endpoint

## Suggested scenarios

### 1. User can view profile details
**Goal:** Verify authenticated account information is displayed.

**Steps**
- Sign in
- Navigate to profile

**Assertions**
- Profile section is visible
- Expected user fields are shown, such as:
  - username
  - email
  - display name

**Selectors to look for**
- headings like `Profile`
- labeled fields or text blocks
- account card/container

**Confidence signals**
- Explicitly listed in suggested opportunities

---

### 2. User can open settings from the authenticated shell
**Goal:** Verify settings access path.

**Steps**
- Sign in
- Click settings nav/menu item

**Assertions**
- Settings section appears
- Relevant controls are visible
- Current section indicator updates

**Selectors to look for**
- `button:has-text("Settings")`
- `a:has-text("Settings")`

---

### 3. User can sign out from settings
**Goal:** Verify logout from account settings.

**Steps**
- Sign in
- Navigate to settings
- Click sign out/logout

**Assertions**
- User returns to login state
- Authenticated-only sections are hidden
- Session does not survive reload unless intended

**Confidence signals**
- Explicitly listed in suggested opportunities

---

### 4. Profile/settings are not visible before login
**Goal:** Verify account surfaces are protected.

**Steps**
- Open app unauthenticated
- Attempt to access profile/settings

**Assertions**
- User is redirected to login or shown access restriction
- No sensitive profile details are rendered

---

# Feature Area: CLI Workflow

**Confidence:** Low to Medium  
**Evidence:** inferred from feature map, but repository contents do not show actual CLI files

## Target routes and actions to cover
No concrete routes apply here. This area appears to be inferred rather than directly represented in the visible file set.

## Recommendation
Do **not** prioritize Playwright browser E2E coverage for CLI workflow unless runtime inspection reveals:

- a browser UI that triggers indexing/generation
- a command console embedded in the page
- upload/import flows tied to repository indexing

## Suggested scenarios if a UI exists

### 1. User can start a repository indexing workflow from the UI
**Goal:** Verify any browser-exposed indexing trigger.

**Assertions**
- Start action is available
- Progress or status appears
- Completion state is shown

### 2. Authentication and CLI-related workflow work together
**Goal:** Verify gated access if indexing features require login.

**Assertions**
- Unauthenticated users cannot access workflow
- Authenticated users can initiate it

## Special note
If this is truly a command-line feature, it belongs in:
- Node integration tests
- shell-based tests
- not Playwright

---

# Feature Area: Test Generation

**Confidence:** Low  
**Evidence:** inferred only

## Target routes and actions to cover
No concrete browser routes or selectors are available from the memory map.

## Recommendation
Treat this as **out of scope for initial Playwright coverage** unless the app visibly includes:

- prompt input UI
- generated test output panel
- repository context upload/import UI

## Suggested scenarios if UI exists

### 1. User can generate tests from available repository context
### 2. Missing input shows validation before generation starts
### 3. Generated output is rendered and can be reviewed

---

# Cross-Feature End-to-End Journeys

These are high-value integrated tests spanning multiple areas.

## 1. Sign in, add a todo, complete it, delete it, and sign out
**Covers**
- Authentication
- Todo Management
- Profile/Settings

**Assertions**
- Each state transition succeeds
- No stale UI remains after logout

---

## 2. Sign in, navigate across sections, and confirm state is preserved
**Covers**
- Authentication
- Navigation
- Todo Management
- Profile/Settings

**Assertions**
- Navigation works
- Todo state remains intact
- Auth state remains intact until logout

---

## 3. Invalid login does not expose protected routes or account surfaces
**Covers**
- Authentication
- Navigation
- Profile/Settings

**Assertions**
- Error is shown
- Protected content remains inaccessible

---

# Selector Strategy

Because concrete selectors are not exposed in the memory map, prefer this order:

1. **Accessible selectors**
   - `getByRole('button', { name: /sign in/i })`
   - `getByRole('textbox', { name: /email|username/i })`
   - `getByRole('checkbox')`
   - `getByRole('link', { name: /profile|settings|home|todos/i })`

2. **Label-based selectors**
   - `getByLabel(/email|username/i)`
   - `getByLabel(/password/i)`

3. **Placeholder/text selectors**
   - `getByPlaceholder(/add todo/i)`

4. **Fallback CSS selectors**
   - `input[type="password"]`
   - `nav a`
   - `.todo-item`
   - `.completed`

## Recommendation for maintainability
Add explicit `data-testid` attributes for:
- `login-email`
- `login-password`
- `login-submit`
- `login-error`
- `todo-input`
- `todo-add`
- `todo-item`
- `todo-toggle`
- `todo-delete`
- `nav-profile`
- `nav-settings`
- `logout-button`

---

# API and Storage Observability

## API endpoints
No API endpoints are revealed in the memory map.

## What to inspect in `app.js`
Confirm whether the app uses:

- `fetch('/login')`
- `fetch('/todos')`
- `fetch('/profile')`

or browser storage such as:

- `localStorage.setItem(...)`
- `sessionStorage.setItem(...)`

## Playwright implementation guidance
- If network-backed:
  - use `page.route()` to mock auth/todo/profile endpoints
- If storage-backed:
  - use isolated browser contexts
  - clear storage in `beforeEach`
  - optionally seed auth state with `page.addInitScript`

---

# Priority Order

## P0
1. User can sign in with valid credentials
2. Invalid credentials show an actionable error
3. User can add a todo item
4. User can mark a todo item as complete
5. User can delete a todo item
6. User can sign out from settings

## P1
1. Unauthenticated user is blocked from protected content
2. Authenticated session persists after reload
3. Todo state persists after reload
4. User can navigate between primary pages
5. User can view profile details

## P2
1. Empty todo submission is prevented
2. Navigation preserves existing todo state
3. Direct navigation to a section shows the correct content
4. Profile/settings are not visible before login

---

# Risks and Blind Spots

## Blind spots from repository indexing
- No startup command inferred
- No explicit routes exposed
- No concrete selectors exposed
- No API endpoints exposed
- CLI/Test Generation may be false positives from feature inference

## Mitigation
Before writing the full suite, perform a short exploratory pass to capture:
- actual route map
- visible labels and roles
- auth mechanism
- persistence mechanism
- any hidden setup requirements

---

# Recommended Initial Playwright Suite Structure

```text
tests/
  auth.spec.ts
  todos.spec.ts
  navigation.spec.ts
  profile-settings.spec.ts
  app-smoke.spec.ts
```

## Suggested first tests to implement
- `auth.spec.ts`
  - signs in with valid credentials
  - shows error for invalid credentials
  - signs out successfully

- `todos.spec.ts`
  - adds a todo
  - completes a todo
  - deletes a todo
  - persists todos after reload

- `navigation.spec.ts`
  - navigates between primary sections
  - blocks protected sections when logged out

- `profile-settings.spec.ts`
  - shows profile details
  - opens settings
  - signs out from settings

---

# Final Recommendation

Start with the **high-confidence browser flows**:

- Authentication
- Todo Management
- Profile/Settings
- Navigation

Defer CLI/Test Generation until runtime inspection confirms they are truly browser-exposed features.

The strongest initial Playwright coverage for this repository is a compact suite validating:

1. login success/failure
2. todo add/complete/delete
3. profile/settings visibility
4. logout
5. state persistence across reload and navigation

If you want, I can also turn this plan into a **concrete Playwright spec scaffold** with example `test.describe()` blocks and locator patterns.