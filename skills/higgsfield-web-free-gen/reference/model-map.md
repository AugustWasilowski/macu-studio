# Higgsfield web free-gen — model map & cost reference

Hard-won facts from a live CoWork session on an account with **`plan_type = ultra`**
+ **"Active unlimited models (Beta)"**. Beta entitlements can shift — the verification
methods below are the source of truth; this table is a starting point.

## The billing model in one line

The web app's **"Unlimited" toggle** decides billing, not the plan and not the model
alone. OFF (the default, and the reload state) bills credits even on an entitled
model; ON is free. The **Generate button label is the truth**: `✦ N` = charges N,
`Unlimited` = free. The `✦ N` number shown by a model is nominal and appears even on
free-eligible models — ignore it, read the button.

## Dropdown label ↔ backend model ↔ entitlement

| Dropdown label | Backend model id | Entitled (free w/ toggle ON)? | Use for |
|---|---|---|---|
| **Nano Banana Pro** | `nano_banana_2` | ✅ yes | **stills** (default) |
| Nano Banana 2 | `nano_banana_flash` | ❌ **no — charges even toggle ON** | avoid |
| **Minimax Hailuo 2.3** | — | ✅ yes | **video** (default) |
| Kling v3.0 | — | ✅ yes | video |
| Kling O1 Image | — | ✅ yes | image |
| FLUX.2 Pro | — | ✅ yes | image |
| GPT Image | — | ✅ yes | image |
| Seedream 4.5 | — | ✅ yes | image |

**The trap:** "Nano Banana 2" (the friendlier-sounding name) is `nano_banana_flash`
and is **not** entitled — it charges. "Nano Banana **Pro**" is `nano_banana_2` and is
free. Confirm the real id you used with read-only `show_generations`.

## Cost if you get it wrong

| Item | Charged (toggle OFF / wrong model) |
|---|---|
| still | ~1.5 cr |
| Minimax Hailuo 2.3 video | ~72 cr |
| **57-clip episode** | **~4,100 cr** (vs **$0** free) |

The toggle matters **most for video** — a single missed reset-to-OFF on a video batch
torches credits fast.

## Zero-cost verification

- `higgsfield.ai/me/settings/subscription` → **"Free generations used"** counter.
  Moves on a free gen; if it stays 0 while credits drop, you're billing.
- Read-only MCP **`show_generations`** → the true backend model id of a generation.
- Read-only MCP **`list_workspaces`** → live credits; before/after delta = 0 proves free.

## Reload state (re-set every session)

A reload resets: **model → nano-banana-pro**, **aspect → 3:4**, **Unlimited toggle →
OFF**. Always re-pick model, re-set aspect, and re-enable Unlimited (confirm the
button reads `Unlimited`) after any reload or new tab.

## Proven free recipes

- **Still:** "Nano Banana Pro", aspect 1:1, 1k, Unlimited ON → button `Unlimited` → 0 cr.
- **Video:** "Minimax Hailuo 2.3", Unlimited ON → button `Unlimited` → free.
