# Terminal Management Test Plan

## Document Information

| Field | Value |
|-------|-------|
| Project | Homepage App - Terminal Manager |
| Version | 1.0 |
| Date | 2026-01-25 |
| Author | QA Engineer |
| Status | Draft |

---

## Table of Contents

1. [Overview](#overview)
2. [Test Scope](#test-scope)
3. [Test Environment](#test-environment)
4. [Unit Tests](#unit-tests)
5. [Integration Tests](#integration-tests)
6. [E2E Tests](#e2e-tests)
7. [Edge Cases](#edge-cases)
8. [Performance Tests](#performance-tests)
9. [Browser Compatibility](#browser-compatibility)
10. [New Features Test Plan](#new-features-test-plan)

---

## Overview

This test plan covers the terminal management features in the Homepage App, including:

- **Existing Features:**
  - Terminal tab management (create, close, rename, switch)
  - iframe terminals via ttyd
  - dtach sessions for persistence
  - Project sidebar with filtering
  - Terminal state persistence via localStorage

- **New Features (To Be Implemented):**
  - Terminal activity detection (input waiting)
  - Audio beep notification when input needed
  - Yes/No quick action buttons on tabs
  - Preview tooltip on tab hover
  - Right-click paste functionality

---

## Test Scope

### In Scope

- Terminal Manager JavaScript functions
- Tab management lifecycle
- iframe loading and display
- dtach session handling
- API interactions for project folders
- localStorage state persistence
- New activity detection features

### Out of Scope

- ttyd service itself (system-level)
- dtach binary functionality
- Network layer issues
- Docker container internals

---

## Test Environment

| Component | Details |
|-----------|---------|
| Server | http://192.168.1.200:1000 |
| Terminal Ports | 7680 (Bash), 7681 (Claude), 7682 (Sudo) |
| Browsers | Chrome 120+, Firefox 115+, Safari 17+, Edge 120+ |
| Test Data | `/home/cactus/claude/*` project folders |

---

## Unit Tests

### UT-001: generateTabId()

| Field | Value |
|-------|-------|
| **ID** | UT-001 |
| **Description** | Verify unique tab ID generation |
| **Priority** | P1 |
| **Steps** | 1. Call `generateTabId()` multiple times<br>2. Collect returned IDs |
| **Expected Result** | Each call returns unique ID matching pattern `tab_[timestamp]_[random]` |
| **Test Code** | `const ids = new Set(); for(let i=0; i<100; i++) ids.add(generateTabId()); assert(ids.size === 100);` |

### UT-002: getTerminalState() - Empty State

| Field | Value |
|-------|-------|
| **ID** | UT-002 |
| **Description** | Verify default state when localStorage is empty |
| **Priority** | P0 |
| **Steps** | 1. Clear localStorage<br>2. Call `getTerminalState()` |
| **Expected Result** | Returns `{ tabs: [], activeTabId: null }` |

### UT-003: getTerminalState() - Existing State

| Field | Value |
|-------|-------|
| **ID** | UT-003 |
| **Description** | Verify state restoration from localStorage |
| **Priority** | P0 |
| **Steps** | 1. Set `cactusTerminalTabs` in localStorage<br>2. Call `getTerminalState()` |
| **Expected Result** | Returns parsed JSON matching stored value |

### UT-004: getTerminalState() - Invalid JSON

| Field | Value |
|-------|-------|
| **ID** | UT-004 |
| **Description** | Handle corrupted localStorage data gracefully |
| **Priority** | P1 |
| **Steps** | 1. Set invalid JSON to `cactusTerminalTabs`<br>2. Call `getTerminalState()` |
| **Expected Result** | Returns default `{ tabs: [], activeTabId: null }` without throwing |

### UT-005: saveTerminalState()

| Field | Value |
|-------|-------|
| **ID** | UT-005 |
| **Description** | Verify state is correctly serialized to localStorage |
| **Priority** | P0 |
| **Steps** | 1. Set `terminalTabs` and `activeTerminalTabId`<br>2. Call `saveTerminalState()`<br>3. Read localStorage |
| **Expected Result** | localStorage contains serialized state matching variables |

### UT-006: createTerminalTab() - New Tab

| Field | Value |
|-------|-------|
| **ID** | UT-006 |
| **Description** | Create a new terminal tab for a project |
| **Priority** | P0 |
| **Steps** | 1. Call `createTerminalTab('bash', 'my-project')` |
| **Expected Result** | - Tab added to `terminalTabs` array<br>- `activeTerminalTabId` set to new tab<br>- `saveTerminalState()` called<br>- Tab rendered in DOM |

### UT-007: createTerminalTab() - Duplicate Session

| Field | Value |
|-------|-------|
| **ID** | UT-007 |
| **Description** | Reusing existing tab when session already exists |
| **Priority** | P0 |
| **Steps** | 1. Create tab for 'bash', 'project-a'<br>2. Create another tab for 'bash', 'project-a' |
| **Expected Result** | - No new tab created<br>- Existing tab activated<br>- Total tabs count unchanged |

### UT-008: createTerminalTab() - Invalid Type

| Field | Value |
|-------|-------|
| **ID** | UT-008 |
| **Description** | Handle invalid terminal type gracefully |
| **Priority** | P2 |
| **Steps** | 1. Call `createTerminalTab('invalid', 'project')` |
| **Expected Result** | Function returns early without errors or changes |

### UT-009: closeTerminalTab() - Single Tab

| Field | Value |
|-------|-------|
| **ID** | UT-009 |
| **Description** | Close the only open terminal tab |
| **Priority** | P0 |
| **Steps** | 1. Create one tab<br>2. Close that tab |
| **Expected Result** | - Tab removed from array<br>- `activeTerminalTabId` set to null<br>- Placeholder shown |

### UT-010: closeTerminalTab() - Multiple Tabs

| Field | Value |
|-------|-------|
| **ID** | UT-010 |
| **Description** | Close active tab when multiple exist |
| **Priority** | P0 |
| **Steps** | 1. Create 3 tabs<br>2. Activate middle tab<br>3. Close middle tab |
| **Expected Result** | - Middle tab removed<br>- Previous tab becomes active<br>- Correct tab highlighted |

### UT-011: closeTerminalTab() - Non-active Tab

| Field | Value |
|-------|-------|
| **ID** | UT-011 |
| **Description** | Close a tab that is not currently active |
| **Priority** | P1 |
| **Steps** | 1. Create 3 tabs<br>2. Activate last tab<br>3. Close first tab |
| **Expected Result** | - First tab removed<br>- Last tab remains active<br>- No activation change |

### UT-012: activateTerminalTab()

| Field | Value |
|-------|-------|
| **ID** | UT-012 |
| **Description** | Switch between terminal tabs |
| **Priority** | P0 |
| **Steps** | 1. Create 2 tabs<br>2. Activate second tab<br>3. Activate first tab |
| **Expected Result** | - `activeTerminalTabId` updated<br>- CSS class 'active' toggled correctly<br>- Correct iframe visible |

### UT-013: activateTerminalTab() - Invalid ID

| Field | Value |
|-------|-------|
| **ID** | UT-013 |
| **Description** | Handle activation of non-existent tab |
| **Priority** | P2 |
| **Steps** | 1. Call `activateTerminalTab('non-existent-id')` |
| **Expected Result** | Function returns early without errors |

### UT-014: renameTerminalTab()

| Field | Value |
|-------|-------|
| **ID** | UT-014 |
| **Description** | Rename an existing terminal tab |
| **Priority** | P1 |
| **Steps** | 1. Create tab<br>2. Call `renameTerminalTab(tabId, event)` with prompt returning 'New Name' |
| **Expected Result** | - Tab name updated<br>- State saved<br>- Tab re-rendered with new name |

### UT-015: renameTerminalTab() - Cancel

| Field | Value |
|-------|-------|
| **ID** | UT-015 |
| **Description** | Cancel rename operation |
| **Priority** | P2 |
| **Steps** | 1. Create tab<br>2. Call `renameTerminalTab()` with prompt returning null |
| **Expected Result** | - Tab name unchanged<br>- No state save triggered |

### UT-016: toggleTerminalSidebar()

| Field | Value |
|-------|-------|
| **ID** | UT-016 |
| **Description** | Toggle sidebar visibility |
| **Priority** | P1 |
| **Steps** | 1. Call `toggleTerminalSidebar()` twice |
| **Expected Result** | - First call: sidebar collapsed, icon changes to expand<br>- Second call: sidebar expanded, icon changes to collapse |

### UT-017: renderTerminalTabs() - Empty

| Field | Value |
|-------|-------|
| **ID** | UT-017 |
| **Description** | Render empty tabs container |
| **Priority** | P1 |
| **Steps** | 1. Set `terminalTabs = []`<br>2. Call `renderTerminalTabs()` |
| **Expected Result** | Tabs container is empty |

### UT-018: renderTerminalTabs() - Multiple Tabs

| Field | Value |
|-------|-------|
| **ID** | UT-018 |
| **Description** | Render multiple tabs correctly |
| **Priority** | P0 |
| **Steps** | 1. Add 3 tabs to array<br>2. Call `renderTerminalTabs()` |
| **Expected Result** | - 3 tab elements rendered<br>- Active tab has 'active' class<br>- Correct type badges shown |

### UT-019: renderProjectList() - No Filter

| Field | Value |
|-------|-------|
| **ID** | UT-019 |
| **Description** | Render full project list |
| **Priority** | P1 |
| **Steps** | 1. Set `allProjectFolders` with 5 projects<br>2. Call `renderProjectList()` |
| **Expected Result** | All non-hidden projects rendered with B and C buttons |

### UT-020: renderProjectList() - With Filter

| Field | Value |
|-------|-------|
| **ID** | UT-020 |
| **Description** | Filter project list by search term |
| **Priority** | P1 |
| **Steps** | 1. Set 5 projects including 'homepage-app'<br>2. Call `renderProjectList('home')` |
| **Expected Result** | Only projects containing 'home' shown |

---

## Integration Tests

### IT-001: Tab Creation -> iframe Load

| Field | Value |
|-------|-------|
| **ID** | IT-001 |
| **Description** | Verify iframe loads with correct URL when tab created |
| **Priority** | P0 |
| **Steps** | 1. Click [B] button for project 'test-project'<br>2. Wait for iframe load |
| **Expected Result** | - Tab created and active<br>- iframe src = `http://host:7680?arg=bash_test-project&arg=test-project&arg=bash` |

### IT-002: Tab State Persistence

| Field | Value |
|-------|-------|
| **ID** | IT-002 |
| **Description** | Verify tabs persist across page reloads |
| **Priority** | P0 |
| **Steps** | 1. Create 2 terminal tabs<br>2. Reload page<br>3. Check terminal manager |
| **Expected Result** | - Both tabs restored<br>- Correct tab is active<br>- iframes reload correctly |

### IT-003: API -> Project List Load

| Field | Value |
|-------|-------|
| **ID** | IT-003 |
| **Description** | Verify project list loads from API |
| **Priority** | P0 |
| **Steps** | 1. Navigate to Terminaux page<br>2. Wait for sidebar load |
| **Expected Result** | - API `/api/projects/folders` called<br>- Projects rendered in sidebar<br>- Hidden projects excluded |

### IT-004: Hidden Projects Sync

| Field | Value |
|-------|-------|
| **ID** | IT-004 |
| **Description** | Verify hidden projects sync with server |
| **Priority** | P1 |
| **Steps** | 1. Open settings modal<br>2. Hide a project<br>3. Reload page |
| **Expected Result** | - API `/api/projects/hidden` called<br>- Project remains hidden after reload |

### IT-005: dtach Session Reattach

| Field | Value |
|-------|-------|
| **ID** | IT-005 |
| **Description** | Verify dtach session survives tab close/reopen |
| **Priority** | P0 |
| **Steps** | 1. Create terminal tab<br>2. Type `echo test` in terminal<br>3. Close browser tab (not terminal tab)<br>4. Reopen page and terminal |
| **Expected Result** | - dtach session exists at `/tmp/dtach-sessions/`<br>- Terminal reconnects to same session<br>- Command history preserved |

### IT-006: Terminal Mode CSS Toggle

| Field | Value |
|-------|-------|
| **ID** | IT-006 |
| **Description** | Verify terminal mode hides unnecessary UI |
| **Priority** | P1 |
| **Steps** | 1. Navigate to Terminaux page |
| **Expected Result** | - `body.terminal-mode` class applied<br>- Header, footer, top-bar hidden<br>- Vertical nav bar visible |

### IT-007: Sidebar Toggle State

| Field | Value |
|-------|-------|
| **ID** | IT-007 |
| **Description** | Verify sidebar toggle works correctly |
| **Priority** | P2 |
| **Steps** | 1. Open terminal manager<br>2. Click sidebar toggle button<br>3. Click again |
| **Expected Result** | - Sidebar collapses to 40px width<br>- Icon changes direction<br>- Sidebar expands back |

---

## E2E Tests

### E2E-001: Complete Terminal Workflow

| Field | Value |
|-------|-------|
| **ID** | E2E-001 |
| **Description** | Full workflow from page load to terminal usage |
| **Priority** | P0 |
| **Steps** | 1. Load homepage<br>2. Click 'Terminaux' tab<br>3. Wait for projects to load<br>4. Click [B] on a project<br>5. Type `ls` in terminal<br>6. Verify output<br>7. Close tab<br>8. Verify placeholder shown |
| **Expected Result** | Complete workflow succeeds without errors |

### E2E-002: Multi-Tab Terminal Session

| Field | Value |
|-------|-------|
| **ID** | E2E-002 |
| **Description** | Work with multiple terminals simultaneously |
| **Priority** | P0 |
| **Steps** | 1. Open Bash terminal for project A<br>2. Open Claude terminal for project A<br>3. Open Bash terminal for project B<br>4. Switch between tabs<br>5. Verify each terminal maintains state |
| **Expected Result** | - 3 tabs visible<br>- Each terminal independent<br>- Switching works correctly |

### E2E-003: Session Persistence After Browser Close

| Field | Value |
|-------|-------|
| **ID** | E2E-003 |
| **Description** | Verify dtach sessions survive complete browser shutdown |
| **Priority** | P0 |
| **Steps** | 1. Create terminal<br>2. Start long-running command `top`<br>3. Close browser completely<br>4. Reopen page and terminal<br>5. Verify `top` still running |
| **Expected Result** | - Session reconnects<br>- `top` command still active<br>- Terminal responsive |

### E2E-004: Project Search and Open

| Field | Value |
|-------|-------|
| **ID** | E2E-004 |
| **Description** | Search for project and open terminal |
| **Priority** | P1 |
| **Steps** | 1. Open terminal manager<br>2. Type in search box<br>3. Verify list filters<br>4. Click [C] on filtered result<br>5. Verify Claude terminal opens |
| **Expected Result** | - Search filters correctly<br>- Terminal opens for correct project |

### E2E-005: Tab Rename Workflow

| Field | Value |
|-------|-------|
| **ID** | E2E-005 |
| **Description** | Rename terminal tab via double-click |
| **Priority** | P2 |
| **Steps** | 1. Create terminal tab<br>2. Double-click tab<br>3. Enter new name in prompt<br>4. Verify name updated<br>5. Reload page<br>6. Verify name persisted |
| **Expected Result** | - Tab shows new name<br>- Name persists after reload |

### E2E-006: Navigate Between Pages

| Field | Value |
|-------|-------|
| **ID** | E2E-006 |
| **Description** | Verify terminal state preserved when switching pages |
| **Priority** | P1 |
| **Steps** | 1. Open terminal in Terminaux page<br>2. Click Accueil in nav bar<br>3. Click Terminaux in nav bar<br>4. Verify terminal still visible |
| **Expected Result** | - Tabs preserved<br>- Active tab still active<br>- iframes maintain state |

---

## Edge Cases

### EC-001: Maximum Tabs

| Field | Value |
|-------|-------|
| **ID** | EC-001 |
| **Description** | Handle opening many terminal tabs |
| **Priority** | P2 |
| **Steps** | 1. Open 20+ terminal tabs<br>2. Switch between tabs<br>3. Close tabs one by one |
| **Expected Result** | - All tabs render<br>- Tab bar scrollable or wraps<br>- Performance acceptable |

### EC-002: Special Characters in Project Name

| Field | Value |
|-------|-------|
| **ID** | EC-002 |
| **Description** | Handle project names with special characters |
| **Priority** | P1 |
| **Steps** | 1. Create folder with name containing spaces, dots, hyphens<br>2. Open terminal for that project |
| **Expected Result** | - Session name sanitized correctly<br>- Terminal opens without error |

### EC-003: Network Disconnection

| Field | Value |
|-------|-------|
| **ID** | EC-003 |
| **Description** | Handle network loss during terminal session |
| **Priority** | P1 |
| **Steps** | 1. Open terminal<br>2. Disconnect network<br>3. Reconnect network |
| **Expected Result** | - Terminal shows connection lost state<br>- Reconnects automatically or shows retry option |

### EC-004: ttyd Service Unavailable

| Field | Value |
|-------|-------|
| **ID** | EC-004 |
| **Description** | Handle ttyd service being down |
| **Priority** | P1 |
| **Steps** | 1. Stop ttyd service<br>2. Try to open terminal |
| **Expected Result** | - iframe shows error or timeout<br>- User can retry or close tab |

### EC-005: Concurrent Session Access

| Field | Value |
|-------|-------|
| **ID** | EC-005 |
| **Description** | Same session accessed from two browser tabs |
| **Priority** | P2 |
| **Steps** | 1. Open terminal in browser tab 1<br>2. Open same URL in browser tab 2<br>3. Type in one terminal |
| **Expected Result** | - dtach allows multiple attachments<br>- Input visible in both<br>- Session not corrupted |

### EC-006: Project Folder Deleted

| Field | Value |
|-------|-------|
| **ID** | EC-006 |
| **Description** | Handle project folder deletion while terminal open |
| **Priority** | P2 |
| **Steps** | 1. Open terminal for project<br>2. Delete project folder externally<br>3. Try to use terminal |
| **Expected Result** | - Terminal shows working in fallback directory<br>- Error message if running commands |

### EC-007: localStorage Full

| Field | Value |
|-------|-------|
| **ID** | EC-007 |
| **Description** | Handle localStorage quota exceeded |
| **Priority** | P3 |
| **Steps** | 1. Fill localStorage near quota<br>2. Try to save terminal state |
| **Expected Result** | - Error handled gracefully<br>- User notified<br>- App continues functioning |

### EC-008: Rapid Tab Open/Close

| Field | Value |
|-------|-------|
| **ID** | EC-008 |
| **Description** | Rapid successive tab operations |
| **Priority** | P2 |
| **Steps** | 1. Rapidly click [B] and [X] buttons |
| **Expected Result** | - No race conditions<br>- State remains consistent<br>- No duplicate tabs |

### EC-009: Empty Project List

| Field | Value |
|-------|-------|
| **ID** | EC-009 |
| **Description** | Handle no projects available |
| **Priority** | P2 |
| **Steps** | 1. Make API return empty project list |
| **Expected Result** | - Sidebar shows empty state<br>- No errors |

### EC-010: iframe Load Timeout

| Field | Value |
|-------|-------|
| **ID** | EC-010 |
| **Description** | Handle slow or failed iframe load |
| **Priority** | P2 |
| **Steps** | 1. Slow down network<br>2. Open terminal tab |
| **Expected Result** | - Loading indicator shown<br>- Timeout handled gracefully |

---

## Performance Tests

### PT-001: Initial Load Time

| Field | Value |
|-------|-------|
| **ID** | PT-001 |
| **Description** | Measure terminal manager initialization time |
| **Priority** | P1 |
| **Target** | < 500ms |
| **Steps** | 1. Profile `initTerminalManager()` execution |
| **Metrics** | - Time to render project list<br>- Time to restore tabs<br>- Total initialization time |

### PT-002: Tab Switch Latency

| Field | Value |
|-------|-------|
| **ID** | PT-002 |
| **Description** | Measure time to switch between tabs |
| **Priority** | P0 |
| **Target** | < 100ms |
| **Steps** | 1. Create 10 tabs<br>2. Measure click-to-visible time |
| **Metrics** | - DOM update time<br>- iframe visibility toggle time |

### PT-003: Memory with Many Tabs

| Field | Value |
|-------|-------|
| **ID** | PT-003 |
| **Description** | Monitor memory usage with multiple terminals |
| **Priority** | P1 |
| **Target** | < 100MB per tab |
| **Steps** | 1. Open 10 terminals<br>2. Use Chrome DevTools Memory panel |
| **Metrics** | - Heap size per tab<br>- iframe memory overhead |

### PT-004: Render Performance

| Field | Value |
|-------|-------|
| **ID** | PT-004 |
| **Description** | Measure `renderTerminalTabs()` performance |
| **Priority** | P2 |
| **Target** | < 16ms (60fps) |
| **Steps** | 1. Add 50 tabs<br>2. Measure render time |
| **Metrics** | - Time to generate HTML<br>- Time to update DOM |

### PT-005: API Response Time

| Field | Value |
|-------|-------|
| **ID** | PT-005 |
| **Description** | Measure project folders API latency |
| **Priority** | P1 |
| **Target** | < 200ms |
| **Steps** | 1. Measure `/api/projects/folders` response time |
| **Metrics** | - Server response time<br>- Total round-trip time |

---

## Browser Compatibility

### BC-001: Chrome

| Field | Value |
|-------|-------|
| **ID** | BC-001 |
| **Browser** | Chrome 120+ |
| **Priority** | P0 |
| **Test Areas** | - All unit tests<br>- iframe loading<br>- localStorage<br>- CSS rendering<br>- Event handling |

### BC-002: Firefox

| Field | Value |
|-------|-------|
| **ID** | BC-002 |
| **Browser** | Firefox 115+ |
| **Priority** | P0 |
| **Test Areas** | - All unit tests<br>- iframe loading<br>- localStorage<br>- CSS rendering (flexbox/grid)<br>- Event handling |

### BC-003: Safari

| Field | Value |
|-------|-------|
| **ID** | BC-003 |
| **Browser** | Safari 17+ |
| **Priority** | P1 |
| **Test Areas** | - iframe cross-origin issues<br>- localStorage quotas<br>- CSS rendering<br>- Touch events on iPad |

### BC-004: Edge

| Field | Value |
|-------|-------|
| **ID** | BC-004 |
| **Browser** | Edge 120+ |
| **Priority** | P1 |
| **Test Areas** | - Same as Chrome (Chromium-based)<br>- Edge-specific features |

### BC-005: Mobile Chrome

| Field | Value |
|-------|-------|
| **ID** | BC-005 |
| **Browser** | Chrome Mobile (Android) |
| **Priority** | P2 |
| **Test Areas** | - Touch interactions<br>- Responsive layout<br>- On-screen keyboard |

---

## New Features Test Plan

### Activity Detection Feature

#### AF-001: Detect Shell Prompt

| Field | Value |
|-------|-------|
| **ID** | AF-001 |
| **Description** | Detect when shell is waiting at prompt |
| **Priority** | P0 |
| **Steps** | 1. Open terminal<br>2. Wait for prompt<br>3. Verify activity indicator changes |
| **Expected Result** | - Tab shows "waiting for input" state<br>- Detection within 500ms of prompt |

#### AF-002: Detect Command Running

| Field | Value |
|-------|-------|
| **ID** | AF-002 |
| **Description** | Detect when command is running (not waiting) |
| **Priority** | P0 |
| **Steps** | 1. Run `sleep 10`<br>2. Verify activity indicator |
| **Expected Result** | - Tab shows "running" state<br>- State changes when command completes |

#### AF-003: Detect Y/N Prompt

| Field | Value |
|-------|-------|
| **ID** | AF-003 |
| **Description** | Detect yes/no confirmation prompts |
| **Priority** | P0 |
| **Steps** | 1. Run `rm -i file`<br>2. Verify Y/N detection |
| **Expected Result** | - Tab shows Y/N buttons<br>- Detection within 500ms |

#### AF-004: Handle Multiple Prompt Types

| Field | Value |
|-------|-------|
| **ID** | AF-004 |
| **Description** | Detect various prompt formats |
| **Priority** | P1 |
| **Steps** | Test: `[Y/n]`, `(yes/no)`, `Continue?`, `Proceed? [y/N]` |
| **Expected Result** | - All common formats detected |

### Audio Beep Notification

#### AB-001: Beep on Input Needed

| Field | Value |
|-------|-------|
| **ID** | AB-001 |
| **Description** | Play audio beep when terminal waits for input |
| **Priority** | P1 |
| **Steps** | 1. Run long command<br>2. Wait for prompt<br>3. Listen for beep |
| **Expected Result** | - Audio plays when prompt detected<br>- Volume appropriate |

#### AB-002: Beep Settings

| Field | Value |
|-------|-------|
| **ID** | AB-002 |
| **Description** | User can enable/disable beep |
| **Priority** | P2 |
| **Steps** | 1. Open settings<br>2. Toggle beep setting<br>3. Verify behavior changes |
| **Expected Result** | - Setting persisted<br>- Beep respects setting |

#### AB-003: Beep Throttling

| Field | Value |
|-------|-------|
| **ID** | AB-003 |
| **Description** | Prevent rapid repeated beeps |
| **Priority** | P1 |
| **Steps** | 1. Rapidly complete commands<br>2. Verify beep frequency |
| **Expected Result** | - Max 1 beep per second<br>- No audio overload |

#### AB-004: Browser Audio Permissions

| Field | Value |
|-------|-------|
| **ID** | AB-004 |
| **Description** | Handle audio permission denied |
| **Priority** | P2 |
| **Steps** | 1. Deny audio permissions<br>2. Trigger beep |
| **Expected Result** | - No error thrown<br>- Fallback behavior (visual only) |

### Yes/No Quick Action Buttons

#### YN-001: Button Display

| Field | Value |
|-------|-------|
| **ID** | YN-001 |
| **Description** | Y/N buttons appear on tab when detected |
| **Priority** | P0 |
| **Steps** | 1. Trigger Y/N prompt in terminal<br>2. Check tab UI |
| **Expected Result** | - Y and N buttons visible on tab<br>- Styled distinctly |

#### YN-002: Yes Button Action

| Field | Value |
|-------|-------|
| **ID** | YN-002 |
| **Description** | Clicking Y sends 'y' to terminal |
| **Priority** | P0 |
| **Steps** | 1. Trigger prompt<br>2. Click Y button |
| **Expected Result** | - 'y' + Enter sent to terminal<br>- Command proceeds |

#### YN-003: No Button Action

| Field | Value |
|-------|-------|
| **ID** | YN-003 |
| **Description** | Clicking N sends 'n' to terminal |
| **Priority** | P0 |
| **Steps** | 1. Trigger prompt<br>2. Click N button |
| **Expected Result** | - 'n' + Enter sent to terminal<br>- Command cancelled |

#### YN-004: Buttons Hide After Use

| Field | Value |
|-------|-------|
| **ID** | YN-004 |
| **Description** | Y/N buttons disappear after clicking |
| **Priority** | P1 |
| **Steps** | 1. Click Y or N button<br>2. Check tab UI |
| **Expected Result** | - Buttons hidden immediately<br>- Tab returns to normal state |

#### YN-005: Cross-frame Communication

| Field | Value |
|-------|-------|
| **ID** | YN-005 |
| **Description** | Parent page communicates with iframe terminal |
| **Priority** | P0 |
| **Steps** | 1. Verify postMessage works<br>2. Test in different browsers |
| **Expected Result** | - Messages sent and received<br>- No CORS errors |

### Preview Tooltip on Tab Hover

#### PT-001: Tooltip Display

| Field | Value |
|-------|-------|
| **ID** | PT-001 |
| **Description** | Tooltip shows terminal preview on hover |
| **Priority** | P2 |
| **Steps** | 1. Hover over inactive tab |
| **Expected Result** | - Tooltip appears after 500ms delay<br>- Shows last N lines of terminal output |

#### PT-002: Tooltip Content

| Field | Value |
|-------|-------|
| **ID** | PT-002 |
| **Description** | Tooltip shows relevant terminal content |
| **Priority** | P2 |
| **Steps** | 1. Run command in terminal<br>2. Switch to another tab<br>3. Hover original tab |
| **Expected Result** | - Shows recent output<br>- Text readable |

#### PT-003: Tooltip Positioning

| Field | Value |
|-------|-------|
| **ID** | PT-003 |
| **Description** | Tooltip positions correctly |
| **Priority** | P3 |
| **Steps** | 1. Hover tabs at different positions<br>2. Check tooltip placement |
| **Expected Result** | - Tooltip stays on screen<br>- Doesn't cover tab |

### Right-Click Paste Functionality

#### RP-001: Context Menu Display

| Field | Value |
|-------|-------|
| **ID** | RP-001 |
| **Description** | Right-click shows paste option in terminal |
| **Priority** | P1 |
| **Steps** | 1. Right-click in terminal iframe |
| **Expected Result** | - Custom context menu appears<br>- Paste option visible |

#### RP-002: Paste Action

| Field | Value |
|-------|-------|
| **ID** | RP-002 |
| **Description** | Clicking paste inserts clipboard content |
| **Priority** | P1 |
| **Steps** | 1. Copy text to clipboard<br>2. Right-click in terminal<br>3. Click Paste |
| **Expected Result** | - Clipboard content inserted at cursor<br>- Works with multiline text |

#### RP-003: Clipboard Permissions

| Field | Value |
|-------|-------|
| **ID** | RP-003 |
| **Description** | Handle clipboard permission denied |
| **Priority** | P2 |
| **Steps** | 1. Deny clipboard permissions<br>2. Try to paste |
| **Expected Result** | - Error message shown<br>- Fallback to Ctrl+V suggestion |

#### RP-004: iframe Context Menu Override

| Field | Value |
|-------|-------|
| **ID** | RP-004 |
| **Description** | Custom menu works despite iframe |
| **Priority** | P1 |
| **Steps** | 1. Right-click in iframe terminal<br>2. Verify custom menu |
| **Expected Result** | - Browser context menu suppressed<br>- Custom menu shown |

---

## Test Data Requirements

| Data Type | Description | Location |
|-----------|-------------|----------|
| Test Projects | 5-10 test project folders | `/home/cactus/claude/test-*` |
| Long-running Commands | Scripts that run for testing | `sleep`, `top`, `tail -f` |
| Y/N Prompts | Commands that ask for confirmation | `rm -i`, `apt install` |

---

## Test Automation Recommendations

### Framework

- **Unit Tests:** Jest with jsdom
- **Integration Tests:** Playwright or Cypress
- **E2E Tests:** Playwright (supports iframe testing)

### CI/CD Integration

```yaml
# GitHub Actions example
test:
  steps:
    - run: npm test           # Unit tests
    - run: npm run test:e2e   # E2E tests
```

### Mock Requirements

- Mock `localStorage` for unit tests
- Mock `fetch` API for API tests
- Mock `prompt()` for rename tests
- Mock `Audio` for beep tests

---

## Sign-off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| QA Lead | | | |
| Dev Lead | | | |
| Product Owner | | | |

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-25 | QA Engineer | Initial version |
