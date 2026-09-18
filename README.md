# MiroxAI

A light, orange-accented, developer-focused chat UI (ChatGPT-inspired
layout, with a dark mode and full theme customization) backed by a
Python/Flask server: AIRoute as the model provider, real per-user chat
history, custom persona/personalization, a lightweight memory system,
file understanding, a simple built-in web search, ChatGPT-style
markdown/code rendering, and a local "project agent" connected over
real SSH.

**Everything is free and unrestricted for every user** — no plans, no
billing, no feature gating.

## Run it

```bash
pip install -r requirements.txt
cp .env.example .env   # then fill in the keys you have
python app.py
```

Open **http://localhost:5000**. Nothing breaks if `.env` is empty —
chat just says plainly that no AIRoute key is connected yet instead of
faking a response.

**Note on the reloader:** `app.py` runs with `use_reloader=False` on
purpose — Flask's debug reloader silently restarts the process on any
file change, which would otherwise wipe pairing codes and live agent
connections mid-session. Saved keys, persona, memory, and chat history
survive restarts either way (they're persisted to disk).

## Appearance — light/dark, color themes, corner style, font

Settings → Appearance. Defaults to **light mode with an orange accent**
and a clean, developer-leaning look. Everything here is a pure UI
preference stored in the browser's `localStorage` (no server round
trip needed for something this cosmetic):

- **Light / Dark** — full token swap, not just an accent change.
- **Color theme** — orange (default), pink/purple, blue/indigo,
  green/teal, or monochrome.
- **Corner style** — sharp, soft, or round, applied to every panel,
  card, and button via two CSS variables.
- **Font** — system default, Inter, Poppins, JetBrains Mono, or Lora
  (loaded from Google Fonts), applied app-wide.

Code blocks always render on a dark background regardless of the
overall theme — a deliberate developer-tool convention (matches
VS Code, GitHub, etc.), not a bug.

The Liquid Glass effect (lensing highlight + a slow ambient sweep) now
runs in light mode too, not just dark — it used to be dampened almost
to nothing in light mode, which made panels read as flat cards. The
sweep uses a soft dark sheen in light mode and a bright highlight in
dark mode (same mechanism, different color, so it reads correctly
against either background), and the ambient background blobs are more
visible in light mode than before as well.

## Typo tolerance

The system prompt explicitly tells the model to read past typos,
autocorrect slips, and minor grammar mistakes and respond to what you
clearly meant, rather than getting confused by a misspelled word or
stopping to correct you unless you actually ask for proofreading. The
message input also has the browser's native `spellcheck`/`autocorrect`
attributes turned on, so you get an underline on typos as you type,
same as any other text field.

## Personalization (custom character)

Settings → Personalization. Add free-text instructions — a
personality, a role, a tone — that get layered on top of whichever
model preset is active for every message. It's saved per user and
persists across sessions.

## Memory

Settings → Memory. A small list of facts, not a vector database:

- The model can write `remember:<fact>` in a reply (stripped from what
  you see, extracted server-side) when it decides something durable is
  worth keeping — your name, a preference, an ongoing project. The
  system prompt tells it to do this sparingly, not for one-off details.
- You can also add or delete facts by hand.
- Remembered facts are included as context in every future message, so
  the model can actually use them, and you can inspect or clear
  everything at any time — nothing hidden.

## File understanding

Click the paperclip in the composer to attach a text-based file (.txt,
.md, .csv, .json, code files, etc. — capped at 2MB). It's read
client-side and sent along with your next message as context, then
cleared. There's no OCR or binary/PDF parsing here — it's a text
attachment, not a document-understanding pipeline; adding real PDF/
image support would need a proper parsing library and is a reasonable
next step if you need it.

## Web search — simple, on purpose

Click the search icon in the composer to toggle web search on for your
next message. It calls DuckDuckGo's free Instant Answer API (no key
required) and folds any results into the prompt as context. Worth
being upfront about the limits: this surfaces instant-answer/infobox
content, not a ranked list of ordinary web pages — it works well for
factual or topic questions and can come back completely empty for
narrower or current-events queries. If you need real search coverage,
swap `web_search_snippets()` in `app.py` for a proper search API (Bing,
SerpAPI, Tavily, etc.) — the rest of the pipeline (folding results into
the prompt) stays the same.

## Model provider — AIRoute, with a free fallback

Settings → your AIRoute API key, saved once and remembered. Also:

- `AIROUTE_BASE_URL` defaults to the real
  `https://route-ai-playground.lovable.app`. The backend auto-corrects
  a URL pasted without `://` instead of erroring.
- AIRoute's documented status codes map to plain messages: 401
  (bad/revoked key), 400 (unsupported model/empty prompt), 402 (out of
  credits), 429 (rate limited).
- ⚠️ If you've ever pasted a real key in plaintext somewhere it could be
  logged or seen by others, treat it as compromised and rotate it.

**Fallback: Pollinations.** If no AIRoute key is saved, or an AIRoute
call fails for any reason, MiroxAI automatically retries with
Pollinations (`gen.pollinations.ai`) — a free, OpenAI-compatible chat
endpoint that usually works with **no API key at all**. You can
optionally save a Pollinations key in Settings if you have one, but
it's not required to get real responses. This also happens to be why
conversation history works properly now (see below) — Pollinations
takes a real `messages` array, unlike AIRoute's single-string prompt.

## Shared keys + admin, and running this for your LAN

Both provider keys used to be saved per-user, which quietly meant
every new anonymous browser session started with a blank slate — the
actual reason it felt like you had to keep re-adding them. They're now
a **single shared config**: one admin sets the AIRoute/Pollinations
keys once, in Settings → General → Admin, and every visitor's chat
uses that same key without any setup on their end.

- On first run, if you haven't set `ADMIN_PASSWORD` in `.env`, one is
  generated and printed to the console/logs — use that to unlock admin
  in Settings. It changes every restart unless you set a real one in
  `.env`.
- Only the admin can view or change the AIRoute/Pollinations keys, or
  add/remove MCP servers (see below). Everyone else can see *whether*
  a model is connected, and use it, but not touch the key.
- The server now binds to `0.0.0.0` by default (set `HOST` in `.env`
  to override), so other devices on the same network can reach it at
  `http://<this-machine's-LAN-IP>:5000` — a phone, another laptop,
  anyone on the same Wi-Fi. Worth knowing: everyone who can reach it
  is sharing the admin's usage/credits on that key, and the Flask
  dev server this runs on isn't hardened for the open internet — LAN
  use is fine, don't port-forward this straight onto the public
  internet without putting a real reverse proxy and HTTPS in front of
  it first.
- Flask's interactive debugger (lets anyone hitting an error run
  Python from the browser) is automatically disabled whenever the
  server isn't bound to localhost specifically, since that debugger is
  a real risk once other devices can reach the app.

## MCP server connections

Settings → MCP (admin-only to add/remove; visible to everyone). Connect
external tools speaking the Model Context Protocol — a weather
lookup, a search index, whatever a given MCP server exposes — and the
AI can call them mid-conversation. Under the hood this is the plain
JSON-RPC 2.0 HTTP form of MCP (`tools/list`, `tools/call`), implemented
directly rather than pulling in an SDK. When the model decides to use
a tool, it writes `mcp:call:<server_id>:<tool>:{...json args...}` in
its reply (a system-prompt instruction only sent when at least one
server is connected); the backend runs the call, then asks the model
for one more turn to turn the raw result into a normal answer — the
person chatting never sees the tool-call syntax itself, just the
final response, plus a small "🔧 Called X → Y" note the same way
project-agent actions show up.

⚠️ I don't have internet access in my sandbox, so this has only been
tested against mocked HTTP responses shaped like the spec, not a real
MCP server — please try it against one you have and tell me if the
wire format needs any adjustment.

## Five more bugs fixed

- **The project agent asked too many clarifying questions instead of
  just building things.** The system prompt now tells it to default to
  doing the work with a sensible default when a detail's missing
  (language, file name, structure) rather than stopping to ask — it
  still mentions the choice it made in a short sentence so you can
  redirect it, but a working first draft beats a round of questions.
- **Sandbox pointed at root when run with sudo.** If `agent_client.py`
  is launched as root (e.g. `sudo python agent_client.py`), Python's
  home-directory lookup resolves to `/root` instead of your actual
  account's home folder — which your regular user can't read or write
  without root permission, causing exactly the access failures you'd
  expect. The agent now detects this (running as root, or home
  resolving to a root-owned directory) and asks for your normal
  username, then uses `/home/<username>` (or `/Users/<username>` on
  macOS) instead — falling back to root only if you explicitly opt in
  or the given username has no home folder on this machine. Verified
  with simulated root/non-root conditions covering all four outcomes
  (normal user untouched, redirected on request, opted out, invalid
  username). The simplest fix is usually just not running this with
  `sudo` in the first place — it doesn't need elevated permissions for
  anything it does.
- **"Failed to write file" for any real code.** The command parser cut
  off `write:file:` content at the first newline — so anything beyond
  a one-line file (i.e. almost any actual source code) silently got
  truncated and then failed. `write:file:` now supports a fenced
  code-block form for real multi-line files:
  ````
  write:file:MyProject/app.py
  ```python
  def hello():
      print("hi")
  ```
  ````
  The model's instructions were updated to use this form for anything
  longer than one line, and command order is now preserved (folder
  creation before the files that go in it, etc.) rather than being
  reshuffled. Verified end-to-end with a real multi-file project write.
- **Sandbox location.** It was already under the user's home directory
  (`~/MiroxAI-Projects`), never system root — that part wasn't
  actually broken, but error messages are now clearer (permission vs.
  filesystem vs. other errors) to make cross-platform issues easier to
  diagnose.
- **File attachments with no visible confirmation.** Attaching a file
  gave no indication in the actual conversation that it was included —
  now a "📎 Attached: filename" note shows in chat when you send. Also
  broadened the accepted file types significantly and added a check
  that warns you if a selected file looks binary (image, PDF, etc.)
  instead of silently sending garbled text.
- **Image generation had no fallback.** Like chat, image generation now
  falls back to Pollinations' free, keyless image API if AIRoute isn't
  configured or fails.

## Three bugs fixed

- **The project agent connected but ignored file requests.** The
  command syntax the backend parses (`create:folder:`, `write:file:`,
  etc.) was never actually explained to the model — so when connected,
  it just answered honestly as a normal chatbot that can't touch your
  filesystem. The system prompt now tells it about the five available
  actions (and, symmetrically, tells it plainly that it *can't* do
  file operations when no agent is connected, rather than guessing).
- **No conversation memory within a chat.** Every message was being
  answered in isolation — the model had no idea what was said two
  messages ago in the *same* conversation. Prior turns are now sent as
  real context on every request (last 20 messages), so follow-ups
  actually work. (This is separate from the long-term "Memory" feature
  below, which persists specific facts *across* conversations.)
- **Code blocks looked broken when customizing Appearance.** The code
  block had a hardcoded corner radius while everything else — including
  the chat bubble it sits inside — followed your chosen corner style,
  so changing to "Sharp" or "Round" made code blocks visibly clash with
  their surroundings. Fixed to scale with the same setting.

## Model presets — MiroxGen1 / MiroxUltraV1 / SearchQue (topbar switcher)

Pick between **MiroxGen1** (fast, `google/gemini-3.1-flash-lite`),
**MiroxUltraV1** (deeper reasoning, `google/gemini-3.1-pro-preview`),
and **SearchQue** (a study-focused preset for students — walks through
problems step by step and cites sources when it uses web search
results, rather than just handing over a final answer) in the topbar;
your choice is sent with every message. SearchQue's `airoute_model` is
set to the literal string `"SearchQue"`, matching what you said is
configured on your AIRoute dashboard — if it errors with "unsupported
model," double check the exact identifier there (case/spelling
matters). Each preset has a system-prompt persona so it answers as
itself rather than naming the underlying provider — worth being
upfront that this is a prompting layer, not a fine-tune or a custom
dataset, and it can still occasionally be talked around under direct
interrogation.

### SearchQue's own API key + direct connection test

Settings → General → SearchQue API key. This is separate from the
main AIRoute key above — useful if your AIRoute dashboard tracks
SearchQue against its own key/quota rather than sharing the general
one. Leave it blank and SearchQue just uses the shared AIRoute key
like the other presets; set it and SearchQue uses that instead,
automatically, with no other config needed.

The "Test connection" button next to it does a *real* direct call —
it actually asks SearchQue to say hello right then, using whichever
key is currently active for it, and shows you the literal reply (or
the literal error) rather than just checking that a key string is
saved. I tested the whole flow (key falls back correctly when unset,
the right key gets used once one *is* set, admin-only write access,
and the test endpoint itself) directly against a mocked provider
response.

## UI refresh — dark/green default, icon rail, editable titles

**Update: the default look changed again**, this time toward a warmer,
flatter, more minimal style (cream background, terracotta accent,
softer shadows instead of a visible blur/glass effect, more rounded
corners, AI replies as plain text instead of a bordered card, user
messages as a soft tinted pill instead of a bold gradient) — inspired
by the general feel of minimal AI chat interfaces, built as an
original palette rather than copying any specific product's actual
branding, logo, or exact colors. Dark mode and the green/orange/pink/
blue/monochrome accents from the previous default are all still there
in Settings → Appearance, just no longer what you see out of the box.
No logo changes — `logo.png` is untouched.

The default look now leans on a reference chat-UI design you shared:
dark mode with a vivid green accent by default (still fully
switchable in Settings → Appearance — light mode and the other accent
colors are all still there, just no longer the default). Structural
changes to match:

- **Right icon rail** — Image Studio, Project agent, AI-Talk, and MCP
  servers moved out of the sidebar into a slim icon column on the
  right (a vertical rail on desktop/tablet, a bottom tab bar on
  phones, since a side rail doesn't work at phone width). These are
  the same features as before, just relocated — nothing was removed.
- **Editable chat titles** — click the pencil next to the title to
  rename a conversation; it persists via a new `/api/history/<id>/rename`
  endpoint, not just a local relabel that forgets itself on reload.
- **Solid accent "New chat" button**, matching the reference design's
  pill button treatment instead of a bordered glass card.

I didn't fabricate sidebar items that don't correspond to a real
feature here (e.g. the reference design's "Explore," "Categories," and
"Library" aren't things this app has, so they're not in the sidebar as
dead links) — the redesign covers layout, color, and the specific
interaction patterns (editable title, rail icons) rather than cloning
every element regardless of whether it does anything.

## Two bugs fixed

- **Copy-to-clipboard silently did nothing on the LAN.**
  `navigator.clipboard` only exists in "secure contexts" — HTTPS, or
  `localhost` — so it's `undefined` on a plain-HTTP LAN address like
  `http://192.168.x.x:5000`, which is exactly how people now reach this
  app after the LAN-sharing feature was added. Calling `.writeText` on
  `undefined` failed immediately with no fallback and no visible
  feedback. Copy now tries the real Clipboard API first, falls back to
  the older `execCommand` method (which works without a secure
  context) if that's unavailable, and shows a real error state instead
  of just doing nothing when both fail.
- **Small-screen layout gaps.** Added a dedicated tablet breakpoint
  (narrower sidebar/rail rather than the full desktop layout jammed
  into less space), bumped several touch targets up to a real
  minimum size (44px) that were a bit tight for a finger, and the new
  icon rail specifically becomes a bottom tab bar below 760px instead
  of a vertical rail that wouldn't fit.

## Real chat history

The sidebar's History list is backed by actual persisted conversations
(`/api/history`), each with a real id and a title from your first
message — reopen or delete any of them.

## Message actions + rich text

Every message has a copy button; AI messages also get like/dislike
(logged server-side via `/api/feedback`, not wired to anything further
yet). AI replies render as markdown via `marked`, sanitized with
`DOMPurify` before insertion as HTML (necessary since it's untrusted
LLM-generated text, not something safe to drop into the page raw).
Code blocks get `highlight.js` syntax highlighting and a "Copy code"
button pinned to the top of the block.

## Image Studio

Click "Image Studio" in the sidebar: a prompt box, style chips, aspect
ratio chips, and a gallery with a morphing liquid-blob loading
placeholder. Calls AIRoute's `POST /api/public/v1/images` endpoint
directly. One caveat: AIRoute's docs didn't specify valid model
identifiers for `/images` (only four chat models were documented), so
`AIROUTE_IMAGE_MODEL` in `.env` is a reasonable guess — change it if
generation fails with an "unsupported model" error.

## Voice input

Click the mic — uses the browser's built-in Web Speech API (Chrome,
Edge, Safari), transcribing locally and sending automatically when you
stop talking. No server-side fallback (that used Hugging Face's
Whisper, removed along with the rest of HF), so other browsers get a
clear "not supported" message.

## AI-Talk — voice calling

Click "AI-Talk" in the sidebar for a phone-call-style interface:
listen → send what you said through the normal `/api/chat` endpoint
(so it shares history, memory, personas, the project agent — every
other feature) → speak the reply back → listen again, on a loop until
you hang up. Both directions use only the browser's free, built-in Web
Speech APIs (`SpeechRecognition` for listening, `SpeechSynthesisUtterance`
for speaking) — no server, no API key, nothing sent anywhere just to
talk. Configure the voice and speaking speed in Settings → Voice; which
voices are available depends entirely on your device/OS, not on
MiroxAI. Requires the same browser support as the mic button (Chrome,
Edge, Safari); others will get a clear message instead of a silent
failure.

## Code syntax highlighting

Code blocks use `highlight.js`'s full language bundle (not the
smaller "common" subset), so far more languages get real syntax
coloring — keywords, strings, function names, etc. — not just a
generic monospace block. The color theme (atom-one-dark) is
intentionally the same in both light and dark app modes, matching how
most developer tools keep code panes dark regardless of the overall
UI theme.

## The project agent — and what it does *not* need from you

**What you do NOT need to do:** enable SSH on your computer, open any
port, run any server on your machine, or give MiroxAI your computer's
real login username or password. A design where this backend held
your real OS credentials and opened a full shell into your computer
would be a genuine remote-access backdoor — categorically different
from, and much more dangerous than, what's actually built here.

What actually happens:

- You download and run `agent_client.py` on your own computer. It
  connects *out* to the server — nothing on your machine listens for
  an inbound connection.
- Settings → Project agent → "Generate one-time pairing code" gives
  you a 6-digit OTP, valid for 15 minutes, single-use — the *only*
  thing you type into the agent script.
- Under the hood, that connection uses the SSH protocol (via
  `paramiko`) purely for encryption; the pairing code doubles as the
  SSH password for that handshake. That's an implementation detail of
  how the two processes talk, not a login to anything.
- The agent **pins the server's host key** on first connection (like a
  real SSH `known_hosts`, saved to `~/.miroxai/known_hosts.json`) and
  refuses to connect — loudly — if that key ever changes later.
- Requires `pip install paramiko` on both sides.

⚠️ **I still haven't been able to run a live end-to-end test of this
handshake** — my sandbox has neither `paramiko` installed nor internet
access. The code follows paramiko's documented API closely and the
non-network logic is tested, but please run through pairing once for
real and let me know if anything breaks.

### How the command whitelist is scoped, and why

Arbitrary command execution triggered by parsing raw LLM output,
reachable remotely, is the same architecture as a remote-access trojan
regardless of what transport carries it — prompt injection from
anything the model reads could hijack it. What's actually built:

1. **Outbound-only** connection, as above.
2. **Pairing required** — a 6-digit, 15-minute one-time code.
3. **Whitelisted verbs only** — `parse_agent_commands` in `app.py`
   recognizes exactly `create:folder:`, `create:file:`, `write:file:`,
   `read:file:`, `list:dir:`. No "run shell command" verb.
4. **Sandboxed on the agent's side** — every path is resolved inside
   one folder (`~/MiroxAI-Projects` by default) and can't escape it.

## Mobile

Below 760px, the sidebar becomes an off-canvas drawer, inputs are
sized at 16px to stop iOS Safari's zoom-on-focus, tap targets are
enlarged, and safe-area insets keep content clear of notches.

## Persistence

Saved AIRoute key, persona, memory facts, sign-in identity, and chat
history are written to a single local JSON file (`MIROXAI_DATA_FILE`,
default `miroxai_data.json`) so they survive a restart. Trade-off worth
knowing: that file holds your **API key in plaintext**. Fine for a
single-user local/dev setup; keep it (and `ssh_host_key`) out of
source control — already covered by the included `.gitignore`.

## Going to production

This is a working starter, not a hardened deployment:

- `miroxai_data.json` is plaintext on disk.
- `SECRET_KEY` in `.env` must be a long random value in production.
- Put this behind HTTPS before exposing it publicly.
- `ssh_host_key` is the server's SSH identity — keep it out of source
  control and back it up.
- Swap the in-memory-plus-JSON-file setup for a real database with
  encrypted secret storage before serving multiple real users.

## Files

- `index.html`, `style.css`, `script.js` — frontend
- `app.py` — Flask backend (auth, AIRoute chat/images, persona,
  memory, web search, history, feedback, SSH agent server, persistence)
- `agent_client.py` — downloadable local agent (SSH client, runs on
  the user's own machine)
- `logo.png` — generated app icon/avatar
- `requirements.txt`, `.env.example`, `.gitignore` — setup
- `miroxai_data.json`, `ssh_host_key` — generated at runtime; don't commit either
