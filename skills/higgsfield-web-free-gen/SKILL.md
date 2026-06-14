---
name: higgsfield-web-free-gen
description: "Generate Higgsfield images and video for FREE by driving the web app (browser / Claude-in-Chrome) under the account's Beta per-model 'unlimited' entitlements — and avoid the UI traps that silently bill credits despite 'unlimited'. The cost-control core of the MACU video pipeline. Generation is browser clicks ONLY; the Higgsfield MCP is read-only (verify, never create — MCP generate_* calls cost credits). Trigger when generating MACU/Higgsfield stills or video in the web app, when working the cowork-harvest job-board, or whenever someone asks why Higgsfield is charging credits despite an 'unlimited' plan. Verified on an account with plan_type=ultra + 'Active unlimited models (Beta)'."
trigger: /higgsfield-web-free-gen
---

# /higgsfield-web-free-gen

Make Higgsfield generations **free** by driving the **web app** under the account's
Beta per-model "unlimited" entitlements. The unlimited tiers are **web-only** — the
API/MCP always bills — so this skill is the cost-control core of the MACU pipeline.
Getting it wrong silently charges credits even though the plan says "unlimited."

## Golden rule

**Generate by browser clicks ONLY.** The Higgsfield MCP is **read-only here** — use
it to *verify* (model ids, credits, history), **never to create**. `generate_image`
/ `generate_video` over MCP/API **cost credits**, entitlement or not.

## The one control that decides billing: the "Unlimited" toggle

There's an **"Unlimited" toggle in the generate bar**. It is the *only* thing that
controls whether a generation is free.

- It **defaults OFF**, and **resets to OFF on every page reload.**
- **OFF = bills credits** — even on an unlimited-eligible model.
- **ON = free.**
- **Confirm via the Generate button label**, not the price:
  - button reads **`✦ N`** → it will **charge** N.
  - button reads **`Unlimited`** → it's **free**.
- Flipping the toggle to check costs nothing. When in doubt, flip it and read the button.

## The trap: UI labels ≠ backend models (silent charges)

The dropdown names don't map 1:1 to the entitled backend models:

- Dropdown **"Nano Banana 2"** → backend **`nano_banana_flash`** → **NOT entitled** →
  **charges even with the toggle ON**.
- Dropdown **"Nano Banana Pro"** → backend **`nano_banana_2`** → **entitled** → **free**.
- **For stills, always pick "Nano Banana Pro."**

## The price number lies

The **`✦ N`** price shown next to a model is **nominal** and appears even for
free-eligible models. **Trust the toggle (the button label), not the number.**

## Reload resets EVERYTHING — re-set every session

A page reload silently resets: **model → nano-banana-pro, aspect → 3:4, Unlimited
toggle → OFF.** After any reload (or new tab), **re-set model, aspect ratio, and the
Unlimited toggle** before generating.

## Entitled models (observed, Beta — verify, may change)

Nano Banana 2 · **Nano Banana Pro** · **Minimax Hailuo 2.3** · Kling v3.0 ·
FLUX.2 Pro · GPT Image · Seedream 4.5 · Kling O1 Image.

- **Stills → "Nano Banana Pro"** (backend `nano_banana_2`).
- **Video → "Minimax Hailuo 2.3".**

## Proven free recipes

- **Still:** "Nano Banana Pro" · aspect **1:1** · **1k** · Unlimited toggle **ON** →
  button reads **`Unlimited`** → **0 credits charged.**
- **Video:** "Minimax Hailuo 2.3" · Unlimited toggle **ON** → button reads
  `Unlimited` → free. (The toggle matters *most* for video — see cost below.)

## Character consistency: Elements (free), NOT Souls (paid)

To keep a character on-model across scenes and episodes, Higgsfield offers two
mechanisms — and only one is free. **For this pipeline, use Elements.**

- **Elements (use these).** A reusable character identity built from a **single
  image**, **instant, no training, and FREE** — Elements work with the unlimited
  models (Nano Banana Pro/2, Seedream, GPT Image, Kling 3.0, …). Create one from a
  still via the web app's **"Save as Element"** (or `show_reference_elements`); it
  returns an **`element_id`**. Embed **`<<<element_id>>>`** in any prompt to place
  that character in a new scene/background, consistent across episodes. Sync the
  `element_id` onto the Studio character record. (Studio's identity picker already
  prefers Elements.)
- **Souls (avoid for the free pipeline).** A *trained* identity model (Soul V2 /
  Cinema) — the strongest identity lock, but **NOT on the unlimited list, so training
  COSTS credits**. It needs ~5–20 reference images and ~10 min of training per
  character, and only works with the `soul_2` / `soul_cinema_studio` image models.
  Reach for a Soul only when a single-image Element isn't holding identity well
  enough and the credit cost is worth it.

**Rule of thumb:** Elements for cross-scene/episode consistency (free). For
talking-head **lipsync** shots, consistency comes from feeding the chosen still into
Hailuo 2.3 image-to-video — Elements matter mainly when you need the character in a
*new* scene/background.

> Worked example (ron): still gen `71b6dd93-d755-405a-bc80-7310fa7ab670`; Element
> `macu_ron` → `element_id 343fb601-ff2f-4281-b284-84850bd19c43`, created free.

## Zero-cost verification (prove you're on the free lane)

- **Subscription page** `higgsfield.ai/me/settings/subscription` → the **"Free
  generations used"** counter. If it stays **0 while your credits drop**, you are
  **not** on the free lane — stop and re-check the toggle/model.
- **Read-only MCP `show_generations`** → the *true backend model id* of what you made
  (catches the Nano-Banana label trap).
- **Read-only MCP `list_workspaces`** → live credits. Take a **before/after delta**
  around a generation; free = **0** delta.

## Cost of getting it wrong

~**1.5 cr / still**, ~**72 cr / Hailuo video**. A 57-clip episode is ~**4,100 credits
charged vs $0 free.** **The toggle matters most for video.** One reset-to-OFF you
didn't catch can burn a plan's worth of credits.

## Per-session checklist (do this every session / after every reload)

1. Pick the model by the **right dropdown name** (stills → "Nano Banana Pro";
   video → "Minimax Hailuo 2.3").
2. Set the **aspect ratio** you want (reload defaulted it to 3:4).
3. **Turn the Unlimited toggle ON** and confirm the Generate button reads
   **`Unlimited`** (not `✦ N`).
4. Generate (browser click).
5. Spot-check on the **subscription page** that "Free generations used" moved and
   credits did **not** — or `list_workspaces` before/after = 0 delta.
6. (If feeding the job-board) report the result's **generation id** — see the
   `cowork-harvest` skill; `show_generations` gives the id + the true backend model.

See `reference/model-map.md` for the label↔backend↔entitlement table and the cost
table. This skill pairs with **`cowork-harvest`** (the job-board loop) — that skill's
"generate in the web app" step **is** this skill.
