# Safety Policy

Autonoma is for **personal, authorized automation only** — your own accounts,
devices, and workflows. It is **not** designed to, and must not be used to,
evade anti-bot systems, CAPTCHAs, fraud/abuse detection, rate limits, platform
abuse detection, or terms-of-service restrictions, or to gain unauthorized
access. The controls below are required behavior.

## High-risk actions requiring explicit approval
Autonoma pauses and requests explicit user approval before any of:

- File deletion
- Credential entry
- Login submission
- Payment form submission
- Financial transfer
- Email sending
- Mass messaging
- External network upload
- Software installation
- System setting changes
- Accessing sensitive folders
- Running destructive commands
- Exporting secrets or credentials

Approvals are surfaced live in the dashboard and via `GET /api/v1/approvals`.

### Sequential approval queue
When more than one agent is active, approval requests are presented **one at a
time** through a single queue — never stacked or shown in parallel — to prevent
approval fatigue and reduce the chance of approving the wrong action.

## Input behavior modes are not evasion tools
Human-like mouse/keyboard pacing exists for natural interaction, demos, QA
testing, and accessibility workflows. It is **not** tuned to defeat bot
detection. Machine-speed mode exists for efficient authorized local workflows.

## Provider endpoint constraint
For API-Based / Hybrid inference, only plain chat/completion endpoints —
including multimodal/vision variants — are allowed. A provider's own autonomous
**agent / tool-use / "computer use"** endpoint is rejected in configuration,
because routing through it would create a second, uncoordinated control loop
that bypasses Autonoma's shared input lock, sequential approval queue, and audit
trail. The model may see and reason about the screen; only Autonoma's agent
system acts on it. Enforced via `api_config.endpoint_type`.

## Action verification (no false success)
No action is marked successful on absence-of-error alone. Each step may declare
a verifiable success condition (expected on-screen text, field read-back, window
state); the automation layer checks it *after* acting.

- `status: "success"` **never** coexists with `verified: false`. If the outcome
  can't be confirmed, the status is `unverified` (or `failed`), not success.
- Text input confirms target focus before typing and verifies field content.
- Clicks use a bounded **retry-with-recheck** loop, not blind re-clicking.
- Repeated verification failures feed Stuck Detection & Recovery.

## File-system scope
Direct file access is **out of scope by default**. A skill that genuinely needs
it must declare `direct_file_access` in its constraints (treated as a high-risk
action) *and* an explicit `AUTONOMA_WORK_DIR` must be configured. Root/system/home
paths (`/`, `C:\`, `C:\Windows`, home-directory roots) are refused.

## OS-command compatibility
Generated commands are validated against the target OS's shell conventions
before execution. Incompatible syntax (e.g. bash-only `echo -e` on Windows) is
translated when safe, otherwise rejected — never silently run to produce wrong
output.

## Secrets
- Stored in environment variables, an encrypted local vault, or an external
  secret manager. Never hardcoded.
- Never saved as raw values inside skills, logs, task files, or screenshots.
- Referenced by handle (`password_secret_ref`); the raw value is resolved only
  at execution time and never returned by any API.
- Redacted from UI, API responses, live event streams, screenshots, and logs.

## Audit trail
Append-only (`INSERT`-only), redacted at write time, timestamped, and linked to
agent/task/skill. Each entry records success/failure and the truthful `verified`
flag, is viewable in the UI, and feeds the real-time dashboard.

## Demonstration recordings
Programming-by-demonstration captures are sensitive (they can reveal window
contents). They are stored and redacted under the same protections as
screenshots/secrets and are never exported or transmitted off the local system
without explicit approval.
