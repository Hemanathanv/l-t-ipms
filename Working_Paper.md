# Working Paper — Living document for progress

## 1. Base information from Prisma (Tbl01ProjectSummary) useful for a PROJECT MANAGER

*Not too many details — identity, ownership, key dates, and high-level health.*

| Category | Field (Prisma) | DB map | Use for PM |
|----------|----------------|--------|------------|
| **Identity** | projectKey | Project_Key | Unique id, filter for tools |
| | projectId | Project_ID | Short code |
| | projectName | Project_Name | Display name |
| | projectLocation | Project_Location | Site/region |
| **Ownership** | projectManager | Project_Manager | PM name |
| | projectManagerDesignation | Project_Manager_Designation | Role |
| **Key dates** | baselineStartDate | Baseline_Start_Date | Planned start |
| | baselineFinishDate | Baseline_Finish_Date | Planned finish |
| | contractualCompletionDate | Contractual_Completion_Date | Contract end |
| | forecastFinishDate | Forecast_Finish_Date | Current forecast |
| | dashboardAsondate | Dashboard_AsOnDate | Data as-of date |
| **High-level health** | scheduleHealthRag | Schedule_Health_RAG | RAG (e.g. G/Y/R) |
| | eotRagStatus | EOT_RAG_Status | EOT status |
| | spiOverall | SPI_Overall | Schedule performance |
| | projectExecutionIndex | Project_Execution_Index | Execution index |
| | daysToContractualEnd | Days_To_Contractual_End | Days to contract end |
| | scheduleRecoveryDays | Schedule_Recovery_Days | Recovery days |
| | recoveryPlanStatus | Recovery_Plan_Status | Recovery plan status |

*Tbl01ProjectSummary has many more fields (float, LAC, domain breakdowns, etc.); the above set is a minimal “base” that would help a PM without overwhelming context.*

---

## 2. What is currently sent to the LLM context

**Source:** `api/v1/chat/router.py` — when user selects a project (e.g. from header dropdown), `project_context` is built and passed into the agent; the WebSocket path builds the same dict and appends `[CONTEXT]` to the user message.

**Fields included in `project_context` dict:**

| Sent to context | Prisma source |
|-----------------|----------------|
| project_key | request.project_key (from dropdown) |
| project_name | project_data.projectName |
| project_location | project_data.projectLocation |
| start_date | project_data.baselineStartDate |
| end_date | project_data.contractualCompletionDate |

**Exact text appended to the user message (when a project is selected):**

```
[CONTEXT]
Selected Project: {project_name} ({project_location})
Project Start Date: {start_date}
Project End Date: {end_date}
When calling tools, use project_key='{project_key}' to filter results.
[/CONTEXT]
```

**Not currently sent to context (but available in Prisma for PM):**

- projectManager, projectManagerDesignation  
- baselineFinishDate, forecastFinishDate, contractualCompletionDate (only contractual is sent as “end_date”)  
- dashboardAsondate  
- scheduleHealthRag, eotRagStatus, spiOverall, projectExecutionIndex  
- daysToContractualEnd, scheduleRecoveryDays, recoveryPlanStatus  
- projectId (only project_key and project_name used in context)

---

## 3. Summary

- **In context today:** project identity (key, name, location), baseline start, contractual end, and instruction to use `project_key` in tools.
- **Possible next steps (if desired):** add 1–2 PM-oriented lines to context, e.g. PM name, schedule health RAG, and/or SPI/forecast finish — keeping the context block short so the model stays focused.

---

## 4. Incorporating reference UI (b_tEdNweJgpJ1-1772130380623)

**Reference location:** `C:\Users\prave\Downloads\b_tEdNweJgpJ1-1772130380623`

**What the reference has (single-file page + globals.css):**
- **app/page.tsx:** One large `IPMSChatPage` with mock data; all UI inline: `LoadingSpinner`, `Avatar`, `ThinkingDots`, `InsightCard`, `MessageBubble`, `WelcomeScreen`, `MessageInput`, `ChatHeader`, `Sidebar`, `ProjectPanel`. Uses CSS vars for chat/insight/sidebar.
- **app/globals.css:** L&T IPMS design tokens (oklch), chat tokens (`--chat-user-bubble`, `--chat-ai-bubble`, `--chat-surface`, `--chat-header-bg`, `--chat-input-bg`, `--insight-bg`, `--insight-border`, `--insight-text`), `.prose-chat`, scrollbar. Tailwind + tw-animate-css.
- **app/layout.tsx:** Geist fonts, Vercel Analytics.

**Current IPMS frontend (to keep):**
- **Main page:** `frontend/app/page.tsx` → `<ChatContainer />` (keep as-is; do not replace with reference’s single page so real API/WebSocket/auth stay).
- **globals.css:** Existing vars (--primary-color, --bg-dark, --message-user, etc.) and many custom classes (sidebar, version-selector, welcome, message, input, ai-insight-card, admin).
- **Components:** `ChatContainer`, `ChatHeader`, `Sidebar`, `MessageList`, `MessageInput`, etc., wired to `useChat`, `useProjects`, WebSocket.

**How to incorporate (without replacing the main page):**

| Area | Action |
|------|--------|
| **globals.css** | Add reference’s **chat design tokens** under `:root`: `--chat-user-bubble`, `--chat-ai-bubble`, `--chat-surface`, `--chat-header-bg`, `--chat-input-bg`, `--insight-bg`, `--insight-border`, `--insight-text` (and optional oklch sidebar tokens if you want the dark sidebar look). Add reference’s **`.prose-chat`** block so assistant messages can use it. Optionally align scrollbar and base body/layout to match. |
| **ChatHeader** | Keep existing logic (projects from API, version selector, auth). Update **styling** to use reference vars/classes: sticky header, `h-14`, `bg-[var(--chat-header-bg)]`, same spacing and project button style (e.g. “Select Project” / selected name + ChevronDown). |
| **Sidebar** | Keep shadcn `SidebarProvider` and existing conversation list + API. Apply reference **sidebar tokens** (--sidebar, --sidebar-primary, etc.) and structure (brand block, New Chat, Today/Earlier) in CSS/classes so it looks like the reference. |
| **Project panel** | Current project card is in `ChatContainer` (right side). Restyle to match reference **ProjectPanel**: same layout (Building2, MapPin, Calendar, TrendingUp, Clock), same labels (Location, Timeline, Progress, Duration). Drive content from `selectedProject` / API (name, location, start_date, end_date); add progress/duration when backend or derived data exists. |
| **Messages / insight** | In `MessageList`, use reference’s **bubble and insight** tokens: user bubble `bg-[var(--chat-user-bubble)]`, AI bubble `bg-[var(--chat-ai-bubble)]`, insight block use `--insight-bg`, `--insight-border`, `--insight-text`. Optionally add `.prose-chat` to assistant message body. Match rounded corners and spacing (e.g. rounded-2xl, rounded-tr-sm / rounded-tl-sm). |
| **Welcome + input** | Welcome: align layout and quick-prompts grid to reference `WelcomeScreen` (centered, prompt buttons). Input: align to reference `MessageInput` (rounded-2xl container, focus ring, optional Paperclip/Mic placeholders, Enter hint). Keep existing `onSend` / `sendMessage` and WebSocket behaviour. |
| **Optional** | Use reference **layout**: Geist fonts in `frontend/app/layout.tsx` if desired. Copy only those `components/ui` files from reference that IPMS doesn’t have and you actually need (e.g. spinner, empty state). |

**Do not:** Replace `frontend/app/page.tsx` with the reference’s single-file page (that would drop real auth, API, and WebSocket). Keep the existing component tree and only adopt styles, tokens, and layout ideas from the reference.

---

*Last updated: from codebase review (Tbl01ProjectSummary, api/v1/chat/router.py); reference UI incorporation plan added from b_tEdNweJgpJ1-1772130380623.*
