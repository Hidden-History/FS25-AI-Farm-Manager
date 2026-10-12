# The notifier command

Cyrus sends cards for you. This page is for players who want to send one by hand or from
their own script.

Run it from your farm folder, so it can find which savegame the folder is bound to.

```bash
python3 .claude/skills/fs25-farm-manager/scripts/notify_farm_manager.py \
    -s warn -t "Silo Alert" -i silo "Corn silo 2 is 92% full"
```

## Options

| Option | Meaning |
|---|---|
| *message* | The text of the card. Required |
| `-s`, `--severity` | `ok` (green), `info` (blue), `warn` (amber) or `critical` (red) |
| `-t`, `--title` | The card's heading. Default: Farm Manager |
| `-i`, `--icon` | The glyph. See the list below |
| `--ttl MS` | How long to show the card, in milliseconds, **when the panel is OFF**. `0` (the default) works it out from the length of the text. With the panel ON a card does not expire, and a card with buttons never expires |
| `--id ID` | A name for this card. Needed for any card that asks a question |
| `--action TYPE` | Adds answer buttons: `ack` (a check) or `yesno` (thumbs up and down). The command also accepts `text`, which adds no button: typed replies always go through the panel's reply bar |
| `--choice VALUE:LABEL` | **Do not use in this version.** The command accepts it and reports the card as delivered, but the mod draws no button for an option, so the player cannot answer the card |
| `--timeout SECONDS` | How long to wait for the mod to pick the card up. Default 2 |
| `--config PATH` | Path to `sanctum/config.json`, if you are not in the farm folder |
| `--bridge PATH` | Full path to `notify.xml`. Overrides all detection. The `FS25_BRIDGE` environment variable does the same |
| `--path-only` | Prints where the card would be written, and stops |
| `-q`, `--quiet` | Prints less |

## Glyphs

`leaf` `alert` `check` `briefing` `contract` `silo` `fleet` `finances` `crop` `weather`
`harvest` `field` `report` `equipment` `fuel` `building` `supply` `schedule` `profit`
`worker` `dealer` `soil` `season` `thumb_up` `thumb_down` `chat` `send` `gear` `close`
`snooze` `critical`

`--help` shows the option as `--icon NAME` and does not print this list.

## A card that asks a question

```bash
python3 .claude/skills/fs25-farm-manager/scripts/notify_farm_manager.py \
    --id ctr-field18 -s info -t "Contract Ready" \
    --action yesno "Field 18 harvest contract. Take it?"
```

Your click is written to `replies.xml` for this savegame. The manager reads it with
`read_replies.py`.

Only `ack` and `yesno` give the player something to click.

## Results

| Exit code | Meaning |
|---|---|
| `0` | The mod read the card. This proves delivery, not that you looked at it |
| `2` | Nothing read it: the game is not running, the mod is not enabled, or a different savegame is loaded |
| `1` | The command could not work out where to write |

A `2` is never a success.

## Related

- [Cards and replies](../how-to/cards-and-replies.md)
- [Files on disk](files-on-disk.md)
