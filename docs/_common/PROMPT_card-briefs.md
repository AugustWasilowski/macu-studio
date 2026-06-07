<!-- Per-card-type briefs for THE MACU REPORT card-text generator.
     Each `## <card_type>` section below is the brief handed to the LLM on
     top of the card-text system prompt (PROMPT_card-text.md). Edit the
     prose under each heading; keep the `## ` headings exactly as named.
     Text before the first heading (this note) is ignored. A missing
     section falls back to the in-code default. -->

## macu_title

The RECURRING franchise title card that opens the broadcast. The wordmark is the show itself, so title_line_1='THE MACU' and title_line_2='REPORT' (do not change these). kicker is tonight's bulletin tease — a short, deadpan all-caps topic line drawn from what this episode is actually about. sub is a single dry station-ID tagline (e.g. 'FROM THE LAST TRANSMITTER.'). Funny via flat understatement, never a joke with a setup.

## fresh_title

A FRESH per-episode segment title card (same layout as the franchise intro, different words). title_line_1 + title_line_2 are the SEGMENT/EPISODE title broken across two short lines (each <= ~16 chars, all-caps, no punctuation) — punchy and a little ominous. kicker is a short topic tease above it. sub is a one-line deadpan logline, ideally lifting a phrase or beat straight from the script. Think a grim TV chyron written by someone too tired to be scared.

## weather

The WEATHER segment card — a post-apocalyptic forecast delivered like routine local news. kicker is a short all-caps segment label naming the weather beat. title_line_1 + title_line_2 are the forecast headline in two short blunt lines: name a specific grim condition tied to THIS episode's setting (look for outside / sky / temperature / hazard beats in the script), never generic, never cute. sub is a one-line deadpan advisory that treats catastrophe as a mild inconvenience. Comedy comes from the flat delivery, not from the words being silly.

## youtube_thumb

The YOUTUBE THUMBNAIL — read at a glance on a phone, so MAXIMUM punch and MINIMUM words. title_line_1 + title_line_2 are the hook in two VERY short, VERY loud all-caps lines (<= ~12 chars each) — the single most absurd or quotable idea in the episode, ideally a verbatim punchline from the script. kicker is a tiny over-line label. sub is one short barbed teaser. idtag stays the EP stamp. Bait the click without lying about the episode.

