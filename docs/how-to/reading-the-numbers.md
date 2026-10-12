# Reading the numbers

The Farm Manager would rather tell you it does not know than show a number it cannot back
up. So some cells hold words. Each one means something specific.

## Words you will see in place of a number

| You see | Where | It means |
|---|---|---|
| **unknown** (dim) | any "as of" line | The manager could not read this figure. It is **not** zero. |
| **capacity refused** (dim) | Farm tab: Storage fill, Points at capacity, Low fuel | The figure needs a capacity (a tank size, a storage size) that could not be worked out, so no figure is given. |
| **rate refused** | Productions tab | The production's rate could not be worked out. |
| **stock unreadable** | Productions tab | The stock level could not be read. |
| a number with a plus, such as **2+** | Farm tab: Low fuel | At least that many. Some machines could not be measured, so the true count may be higher. |
| **full** | Productions tab | The output storage is full. |

A dim **unknown** on a line that has no other tag is normal. It is the plain "not read"
answer.

## Fields

| You see | It means |
|---|---|
| **No crop** | The field is bare. This is a real answer, shown at full brightness. |
| a crop name, such as **Oat** | The game's own name for the crop. |
| **No contract** in the contract box | The game was checked and this field has no contract. |
| **unknown** in the contract box | The contract could not be read. |
| an empty Contract cell in the list | No contract. The list keeps the cell blank; the detail box says it in words. |
| **Harvest-state ground** | A ground state the game leaves set after harvest. It is **not** an instruction to harvest. Look at Growth stage for that. |
| **differs — 12 Wheat  13 Wheat  14 No crop** | This field is several savegame parcels that disagree. Each parcel is listed with its own value. |
| an upper-case word, such as `SOME_STATE` | A ground or crop state this version has no label for. It is shown raw so it is never blank. Please [report it](../reference/privacy-and-feedback.md). |

## Fleet

- **Machines owned** counts machines. Pallets are counted on their own line, **Pallets
  owned**.
- **Bales owned** counts bales the game has saved as bales. A finished bale still inside a
  round baler is not counted until it is dropped.
- **Low fuel** counts machines with an engine whose tank is at 25 % or less. A machine with
  an empty tank counts. A trailer or tanker carrying diesel as cargo does not.

## LIVE and "as of"

**LIVE** figures come from the running game. **as of** figures are the manager's last read
of your save, with the time of that read. See
[where the numbers come from](in-game-menu.md#where-the-numbers-come-from).

## If a number looks wrong

1. Check the "as of" time. An old time means the manager has not read a newer save.
2. Save the game with a session running, then look again.
3. If it is still wrong, tell Cyrus what you see in game. It logs the difference, and at
   closeout it can offer to report it.
