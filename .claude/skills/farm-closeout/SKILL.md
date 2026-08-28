---
name: farm-closeout
description: Close out an FS25 farm session — dispatches the fs25-farm-manager skill's CO (closeout) menu item.
disable-model-invocation: true
---

Invoke the **`fs25-farm-manager`** skill and dispatch its menu item **`CO` (Closeout)** for
the farm bound to this project directory.

That skill is the source of truth for the workflow — follow its instructions as written,
including which sanctum files to verify and the rule that the finances ledger row is
completed rather than appended. Don't reconstruct the steps from this file; it exists only to
give the player a short way to end a shift.

$ARGUMENTS
