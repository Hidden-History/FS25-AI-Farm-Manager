# Daily use

You talk to the manager in Claude Code, in your farm folder. It introduces itself as
**Cyrus**. Most of a session is plain conversation.

## A normal session

1. Start the game and load your savegame.
2. In your farm folder, start Claude Code and say **"briefing"**, or type `/farm-briefing`.
3. Play. Save the game when you want the manager to see what changed.
4. When you stop, say **"close out"**, or type `/farm-closeout`.

The briefing also starts a background watcher. While it runs, every game save makes the
manager re-read your farm and refresh the game's menu page, and every answer you click on a
card comes straight back to it. Closeout stops the watcher.

## What to say

| Say | Or type | You get |
|---|---|---|
| "set up my farm manager" | `/fs25-farm-manager` | First-time setup, or the menu if the farm is already set up |
| "briefing" | `/farm-briefing` | What changed since last time, and what is worth doing today |
| "status" | `/farm-status` | A quick look at the save. Writes nothing |
| "what should I buy?" | | Planning: seed and fertilizer timing, equipment you do not own, the used market, with prices |
| "what's oat worth?" | | Prices, and what a piece of land would cost |
| "close out" | `/farm-closeout` | Writes the session up so the next one starts informed |

Other things worth asking:

- "What does field 12 need?"
- "Which production is closest to running out?"
- "How is the fleet?"

## What Cyrus will and will not do

- It reads your save every session. It does not quote your cash or your land from memory.
- When a figure is not on disk, it says so and asks you. It does not make one up.
- It recommends; you decide.
- It never changes your savegame.
- It will not edit the mod. If you want the mod to do something new, it logs your request.

## At closeout

Cyrus asks two things:

1. Whether anything that went wrong this session looks like a real product bug worth
   reporting.
2. Whether there is anything you would like added or changed.

Nothing is sent without you seeing it first. See
[Privacy and feedback](../reference/privacy-and-feedback.md).

## Related

- [The in-game menu](in-game-menu.md)
- [Cards and replies](cards-and-replies.md)
