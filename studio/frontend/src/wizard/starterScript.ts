// The practice episode the guided walkthrough seeds into the active show.
//
// NOT internationalized on purpose: the script *grammar* is structural — `## SEGMENT`
// headers, `**SPEAKER:**` cues, and `»` shot directives are parsed by gen_manifest.py,
// and the speaker names become voice-map keys. A 47-locale translation pass would corrupt
// the markers and break speaker→voice mapping. The wizard's UI copy IS translated; this
// constant stays English and is meant to be edited by the user.
//
// Two speakers (NARRATOR, GUEST) are intentionally left unmapped in example-show's empty
// speaker_map, so Generate Manifest flags them as unmapped — which sets up the casting step.

export const STARTER_SLUG = "my-first-episode";
export const STARTER_TITLE = "My First Episode";

export const STARTER_SCRIPT = `# My First Episode

## COLD OPEN
**NARRATOR:** Welcome to your very first episode. Every line written like this one becomes a spoken voice cue.
» NARRATOR core

**GUEST:** And every speaker can have their own voice. You'll cast us on the Audio page in a moment.
» b-roll: a vintage television studio control room, black and white

## THE MIDDLE
**NARRATOR:** A line that starts with two arrows, like the one below me, is a shot direction — it tells the video stage what to put on screen.
» b-roll: an old broadcast tower against a grey sky

**GUEST:** You can write as many segments as you like. Each "## heading" starts a new one.

## SIGN OFF
**NARRATOR:** That's the whole idea. Edit this script, rewrite it, or replace it with your own — then press Generate Manifest at the top right.

**GUEST:** See you on the next page.
» GUEST core
`;
