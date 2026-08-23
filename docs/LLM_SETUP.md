# WORKFACE — LLM setup

*How to point the agent at a model, what runs where, and what that means for Vercel.*

---

## 1. The short version

The repo is already built for this. `.env.example` carries three variables and there is nothing else to configure:

```bash
LLM_BASE_URL=
LLM_API_KEY=
LLM_MODEL=
```

Every provider worth using — Ollama on your laptop, DeepInfra, Together, Groq, OpenAI — speaks the same OpenAI-compatible protocol. So the client is one object and switching providers is an env change, never a code change:

```python
client = OpenAI(base_url=os.environ["LLM_BASE_URL"], api_key=os.environ["LLM_API_KEY"])
```

That is `WORKFACE_TECH_SPEC.md` §10 and it is already the decided architecture. Do not add provider branching to the code — the whole value of the decision is that there is none.

---

## 2. What actually talks to the LLM (this is the Vercel answer)

**Vercel never calls the model. Not once.** Three separate things run in three separate places:

| Piece | Where it runs | Talks to the LLM? |
|---|---|---|
| `apps/web` — Next.js console, ribbon, map, trace view | **Vercel** | **No.** `apps/web/app/` has no API routes. It reads committed JSON (`console.json`, `ribbon.json`) and later Supabase. |
| `apps/api` — evaluators, priors, twin, agent loop | **Your laptop**, and **GitHub Actions cron** for scheduled runs | **Yes**, and only at one step |
| Supabase | Hosted Postgres | No |

The agent writes its run, steps and conflicts to the database. The web app *reads* them. By the time a judge clicks your Vercel URL, the thinking already happened somewhere else and was written down.

**So: running Ollama on your laptop cannot break Vercel.** There is nothing for it to break.

The flip side is the real constraint: **GitHub Actions cannot reach `localhost:11434` on your laptop either.** If you want the agent to run unattended in CI, it needs a hosted endpoint. If you are happy running the agent from your laptop and committing the result, Ollama alone is enough.

And one more thing worth knowing: **the LLM is a small job.** Per §8.2, the physics, the window evaluation and the sequencing arithmetic are all plain Python. The model only picks which resolution strategy to try and writes the rationale a human reads. That is why the token bill is a few cents a run — and why a local 8B is a credible choice rather than a compromise.

---

## 3. Path A — Ollama on your laptop (your primary path)

You already have Ollama installed. This is the setup the spec assumes for development, and it is the one that keeps the pitch true.

### Step 1 — check it is running

```powershell
ollama --version
```

On Windows, Ollama runs as a background service with a system-tray icon and listens on `127.0.0.1:11434`. If `--version` works but requests fail, open the tray icon and confirm it is running.

### Step 2 — pull a model that can actually call tools

This matters more than raw quality. The agent's one job is emitting a correct tool call; a model that is merely fluent will fail at it.

```powershell
ollama pull qwen3:8b
ollama list
```

`qwen3` is trained for tool use, which is why §10 names it. If that exact tag has moved, check `ollama.com/library` — `granite4` is also trained for tool calling, and `qwen2.5-coder:14b` or `gemma3:12b` support it if you have the VRAM.

**Sizing:** an 8B at Q4 is roughly 5–6 GB of VRAM. If your GPU has less, Ollama will spill to CPU and you will get single-digit tokens per second — workable for a scripted run, painful live on stage. See §6 for why that does not have to matter.

### Step 3 — raise the context window

**This is the gotcha that will bite you.** Ollama's default context is small (a few thousand tokens), and an agent prompt carrying activity lists, window evaluations and a conflict description will silently overflow it. The symptom is not an error — it is the model quietly forgetting the tool definitions and answering in prose.

Set a user environment variable and restart Ollama:

```powershell
setx OLLAMA_CONTEXT_LENGTH 32768
setx OLLAMA_KEEP_ALIVE 30m
```

`OLLAMA_KEEP_ALIVE` keeps the model resident so the first request of your demo does not stall for twenty seconds while weights load.

### Step 4 — verify the OpenAI-compatible endpoint

```powershell
curl.exe http://localhost:11434/v1/models
```

You want a JSON list containing the model you pulled. That URL — with the `/v1` — is what goes in `LLM_BASE_URL`. Note the port is `11434`, not `1143`.

### Step 5 — write your `.env`

```bash
LLM_BASE_URL=http://localhost:11434/v1
LLM_API_KEY=ollama
LLM_MODEL=qwen3:8b
```

`LLM_API_KEY` must be non-empty — the OpenAI client refuses to construct without one — but Ollama ignores the value entirely. `ollama` is the conventional placeholder.

`.env` is already in `.gitignore`. Keep it that way; never commit a key.

### Step 6 — install the client

`apps/api/requirements.txt` does not yet include an LLM client:

```
httpx>=0.27
pydantic>=2.0
python-dotenv>=1.0
PyYAML>=6.0
pytest>=8.0
```

Add `openai>=1.40` and install:

```powershell
pip install -r apps/api/requirements.txt
```

This is a deliberate new dependency and CI installs from that file, so it should be called out in the day's report rather than slipped in.

### The one portability caveat

Ollama's OpenAI-compatible endpoint **does not support `tool_choice`**. So a prompt that works locally *because you forced a tool call* will behave differently on a hosted provider that honours the parameter. Write the prompt so it never needs forcing. (Ollama also does not support `logprobs` or image URLs — neither matters here.)

---

## 4. Path B — a hosted open-weight endpoint (for CI and the public URL)

Same three variables, different values. This is what you need if the agent runs on GitHub Actions cron, or if you want the demo to work without your laptop.

```bash
LLM_BASE_URL=https://api.deepinfra.com/v1/openai
LLM_API_KEY=<your deepinfra key>
LLM_MODEL=meta-llama/Llama-3.3-70B-Instruct-Turbo
```

DeepInfra is what §10 names; Together, Groq and Fireworks all work identically if you prefer one of those. Verify the exact model slug on the provider's site before demo day — slugs move.

For GitHub Actions, put `LLM_BASE_URL`, `LLM_API_KEY` and `LLM_MODEL` in **repo secrets**, not in the workflow file.

**Crucially, this path keeps the pitch intact.** Llama 3.3 is open-weight. "This runs on open models, and on your own infrastructure if you want it to" is still true when you are renting someone's GPU to run one — because the customer *could* run it themselves. That sentence stops being true the moment you switch to a closed model.

---

## 5. Path C — an OpenAI key

**Will it work?** Yes, completely, with zero code change:

```bash
LLM_BASE_URL=https://api.openai.com/v1
LLM_API_KEY=sk-...
LLM_MODEL=gpt-4o-mini
```

That is the entire setup. Get the key from `platform.openai.com` → API keys, and note it is a *platform* key with its own billing — a ChatGPT Plus subscription is a different product and does not give you API access.

**Should you?** Probably not as your demo path, and the reason is not cost.

§10 is one of the nine headline decisions in the tech spec, and it reads:

> *WORKFACE runs entirely on open-weight models. A contractor's P6 schedule — activity durations, float, milestone dates, subcontractor sequencing — never leaves their network.*

A project schedule is one of the most commercially sensitive documents a contractor owns; it is what their delay claim and their competitors' bids both turn on. "It runs on your infrastructure" is a procurement unlock for that buyer, and their IT *will* ask. Route the demo through OpenAI and the honest answer to "does our schedule leave our network?" becomes yes — and you have to stop saying the open-weight line, which is one of your strongest differentiators, for a model quality difference the agent's job barely exercises.

Cost is not the argument either way. §8.2 keeps the physics in Python, so you are looking at a few cents per run on any provider.

**Keep it as break-glass.** If Ollama dies an hour before the demo and DeepInfra is down too, swap the env var, run, and drop the open-weight claim from the script for that showing. Do not build on it and then discover on stage that a slide contradicts your configuration.

---

## 6. What to actually do on demo day

Do not run a live model in front of judges if you can avoid it, and you can. The repo is already built for this — `REPLAY_MODE=true` is in `.env.example`, and `AgentRun` carries a `replay` flag that the existing fixtures already set.

The pattern:

1. Run the agent live against your chosen model, once, the night before.
2. Commit the resulting `AgentRun`.
3. Demo from the committed trace.

You get the same trace, the same step cards, the same escalation — with no dependency on conference wifi, no cold-start stall, and no chance of the model picking a different strategy on the one run that matters. If a judge asks whether it is live, the honest answer is a good one: *"this is a recorded run from last night — here is the model it used, here is the hash chain, and we can re-run it now if you'd like."*

And per §10's warning: **do not swap models blind at the end.** A prompt tuned on a local 8B can call the wrong tool on a 70B. Run the loop against your demo model from Day 6 onward, not for the first time on Day 9. `tests/test_agent_replay.py` — ten fixed scenarios asserting the chosen tool, run against both models — is half an hour of work on Day 7 and turns "did the swap break anything" into a ten-second check.

---

## 7. Everything else you need for Days 5 and 6

**Day 5 — nothing new.** Every input is already on disk (`sweep_bundle.json`, `activities.json`, `trade_windows.json`), and the work is stdlib + pydantic. No key, no network, no model.

**Day 6 — only the LLM path above**, plus:

- `pip install -r apps/api/requirements.txt` after `openai` is added.
- Model pulled, `OLLAMA_CONTEXT_LENGTH` raised.
- **CI must not call the model.** There is no key in GitHub Actions and there should not be one for the test job. The smoke test has to skip cleanly when `LLM_BASE_URL` is unset, or CI goes red on every push.

**Worth checking now, before it blocks someone:**

- **Supabase.** `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` and the two `NEXT_PUBLIC_*` variables are needed for T1's Day-7 realtime channel. Migration `002_t2_day3.sql` exists in the repo — confirm it has actually been applied to the database, not just committed.
- **Mapbox.** `NEXT_PUBLIC_MAPBOX_TOKEN` is what the deck.gl site map renders over. T1's problem, but a missing token looks like a broken map.
- **Vercel.** Every `NEXT_PUBLIC_*` variable has to be set in the Vercel project too — local `.env` does not travel. The spec's warning about sleeping free tiers does not apply to Vercel, so you are fine there.
- **`REPLAY_MODE=true`** should stay true for the demo. It is what makes the FortyGuard fixtures the source of truth instead of live credits, and `MAX_FG_CALLS_PER_DAY=120` is your guard rail if it ever goes false.
