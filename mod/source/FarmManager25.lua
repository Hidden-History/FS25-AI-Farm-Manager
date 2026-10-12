--[[
    FarmManager25.lua
    -----------------
    Shows a designed, severity-coloured on-screen notification the instant an
    external "Farm Manager" process (e.g. a Claude Code skill) writes one to a
    small bridge file on disk.

    Bridge file (created on first map load; the folder is derived from the
    mod's PACKAGE name -- see MOD_NAME below):
        <FS25 profile folder>/modSettings/FS25_AIFarmManager25/notify.xml
    On Windows:
        Documents\My Games\FarmingSimulator2025\modSettings\FS25_AIFarmManager25\notify.xml

    ---------------------------------------------------------------------------
    WIRE FORMAT (protocol 4; base shape below, additions further down) -- XML,
    because FS25 WILL NOT LET US READ ANYTHING ELSE
    ---------------------------------------------------------------------------
        <farmManager25>
            <notification severity="warn" title="Market" ttl="8000">
                <line>Oat is at its annual low</line>
                <line>$431/1000L, peaks $644 on day 11.</line>
            </notification>
        </farmManager25>

    Protocol 1 used a plain-text notify.txt read with io.open(path, "r"). That
    CANNOT WORK. FS25 sandboxes io to write-only:

        Warning: io.open, only write mode ('w') is allowed
        Error: ...FarmManager25.lua:412: attempt to call missing method 'read' of table

    io.open(path, "r") does not fail cleanly -- it returns a TABLE with no read
    method, and it opens the file FOR WRITING and holds the handle. So the next
    poll hit "Sharing violation on file ... perhaps open in another program?"
    That was us, holding our own file, because the error aborted update() before
    file:close() ever ran.

    The sanctioned read path is the engine XML API, verified against shipped
    mods: XMLFile.load(name, path) with NO schema (EasyDevControls
    EasyDevControlsGuiManager.lua:126 does exactly this), then :getString(key),
    :hasProperty(key), :delete(). Attributes are "path#attr"; repeated elements
    are "path(i)".

    Body text is carried as indexed <line> elements rather than one string with
    newlines, so nothing depends on whether the engine's XML reader preserves
    newlines inside element text -- a question I would have had to guess at.

    Protocol 4 (additive): <notification> MAY carry a stable id="..." (the
    correlation key for future replies) and an <actions> block declaring reply
    affordances:
        <notification id="ctr-field18-0812" severity="warn" title="Contract Ready">
            <line>Field 18 - Harvest</line>
            <actions>
                <action type="yesno"/>
                <action type="choice"><option value="sell_a">Sell A</option></action>
            </actions>
        </notification>
    A protocol-3 card (no id/<actions>) parses and renders exactly as before.
    A card offering <actions> MUST carry an id (a reply needs something to
    reference); an id-less <actions> block is dropped.

    A card WITH <actions> draws an affordance row (ack -> check, yesno ->
    thumb_up/thumb_down, always a close/dismiss X). Clicks route whenever the
    ENGINE's shared mouse cursor is on screen (g_inputBinding state -- raised
    by AutoDrive's MMB, Courseplay's RMB, this mod's own Ctrl+Comma cursor
    toggle, or any other cursor mod). Click-gating only READS that shared
    state; the ONE place the mod writes it is the standalone cursor toggle
    (FM25_TOGGLE_CURSOR, added S157 so the overlay is reachable ON FOOT, where
    AD's MMB / CP's RMB -- both vehicle-context -- cannot raise it; the S155
    assumption that they always could was disproven in on-foot play). Whoever
    raised the cursor owns it. Ctrl+Period (FM25_TOGGLE_OVERLAY) instead
    toggles the OVERLAY
    between its two modes: ON (default) is a persistent always-on panel --
    header, cards and reply bar stay up and cards do not auto-expire; OFF is
    the original transient pop-up notifier where each card fades after its
    ttl. Every un-dismissed card -- info AND action -- persists in the client
    store and across sessions via state.xml (which mirrors the live stack); a
    card leaves only when the player dismisses (its X) or answers it, or, in
    OFF mode, when a transient card fades. A click on an affordance
    appends a reply to modSettings/FS25_AIFarmManager25/replies.xml:

        <farmManager25Replies>
            <reply id="ctr-field18-0812" action="yes"
                   realTime="2026-07-19 12:00:00"/>
        </farmManager25Replies>

    The reply echoes the card's id (the correlation key); the skill ingests
    and truncates the file on its own schedule (fire-and-forget). Appends are
    deduped by (id, action) so a double-click can never double-count. If the
    interactive layer ever fails it latches OFF and cards keep rendering as
    the plain one-way notifier -- interactive -> one-way -> native, each tier
    strictly less capable but still delivering the message.

    ---------------------------------------------------------------------------
    WHY THE FILE IS CONSUMED, AND WHY THERE IS NO CONTENT DEDUP
    ---------------------------------------------------------------------------
    Consuming a message = DELETING the bridge file (deleteFile, an engine
    global -- Courseplay mocks it in mock-GiantsEngine.lua:51). That is both the
    dedup AND the sender's delivery receipt: the sender watches for the file to
    disappear and only then may claim the message was displayed.

    Delete rather than truncate: an empty file is not valid XML, so every
    subsequent poll would fail to parse it and spam the log. Absence is
    unambiguous.

    An earlier version ALSO compared content to the last message and returned
    early if they matched. That silently dropped every repeated notification
    ("Silo 3 is almost full" twice in a row -> the second never appeared) and,
    worse, returned BEFORE clearing the file, so the bridge stayed dirty forever
    and the sender's receipt never arrived. The clear is the dedup. Do not
    reintroduce a content comparison.

    ---------------------------------------------------------------------------
    RENDERING, AND WHY THERE IS A FALLBACK
    ---------------------------------------------------------------------------
    The panel is drawn with the same primitives the shipped HUD mods use:
    Overlay.new(g_baseUIFilename) + setUVs(g_colorBgUVs) + setColor + render,
    with geometry from getNormalizedScreenValues so it is resolution-independent.

    If any of that throws, we do NOT go quiet. We disable the custom panel for
    the session and fall back to the game's native notification permanently.
    A notification that fails to draw and says nothing is worse than an ugly
    one: the operator would keep sending messages into a void believing they
    landed.

    Native API, verified against shipped mods (Courseplay
    AIDriveStrategyCombineCourse.lua:675, EasyDevControls):
        g_currentMission:addIngameNotification(type, text)  -- EXACTLY 2 args.
    No icon, no title, no duration -- which is precisely why this panel exists.

    Only OK / INFO / CRITICAL were observed in any installed mod. WARNING is
    NOT assumed to exist: resolveNativeType() looks the constant up at runtime
    and falls back to INFO if the engine does not define it.
]]

-- FarmManagerTheme.lua loads first (modDesc <extraSourceFiles> order) and
-- creates this table to hang THEME on; extend it, never clobber it.
FarmManager25 = FarmManager25 or {}

-- FS25 sandboxes each mod to modSettings/<ITS OWN MOD NAME>/ and refuses
-- everywhere else. The real game said so in as many words:
--
--   Error: No access to folder '.../modSettings/FarmManager25/notify.xml'
--   Info:  Mod has full access in '.../modSettings/FS25_AIFarmManager25'
--
-- g_currentModName is that name, captured at chunk scope while it is still set.
-- Courseplay does exactly this (Courseplay.lua:19):
--   self.baseDir = getUserProfileAppPath() .. "modSettings/" .. Courseplay.MOD_NAME .. "/"
-- Derived, not hardcoded: rename the zip and the folder follows.
FarmManager25.MOD_NAME = g_currentModName or "FS25_AIFarmManager25"
FarmManager25.RELATIVE_FOLDER = "modSettings/" .. FarmManager25.MOD_NAME .. "/"

-- g_currentModDirectory is only set WHILE THIS FILE IS BEING LOADED. By the time
-- loadMap runs it is nil, so Utils.getFilename(rel, nil) hands back the relative
-- path unchanged and the atlas "goes missing":
--
--   FarmManager25: could not build the HUD, falling back to native notifications
--     -- atlas missing at textures/fm25_atlas.dds        <- no directory on it
--
-- Capture it here, at chunk scope, exactly as Courseplay does (Courseplay.lua:16):
--   Courseplay.BASE_DIRECTORY = g_currentModDirectory
-- That line was in front of me and I used the global inline anyway.
FarmManager25.MOD_DIR = g_currentModDirectory or ""
FarmManager25.FILE_NAME       = "notify.xml"
FarmManager25.SETTINGS_NAME   = "settings.xml"
-- The mod-WRITTEN client store (window position). settings.xml stays the
-- hand-edited power-user override that seeds defaults; state.xml is the live
-- runtime store, so a user drag and a user file-edit never fight over one file.
FarmManager25.STATE_NAME      = "state.xml"
-- BUG: one install serves EVERY savegame, so a single card store showed save A's
-- cards in save B (v3.0.0.0, found in a live test). The cards moved to a
-- PER-SAVEGAME file; state.xml stayed exactly where it is and kept its <hud>
-- element, because panel position/scale are a function of the MONITOR, not of a
-- farm -- moving them would have made "drag the panel in one save, it resets in
-- another" a new bug shipped by the fix. SPLIT, never moved: every existing
-- player's panel settings survive the upgrade with no migration code.
FarmManager25.CARDS_NAME      = "cards.xml"
-- The reverse channel: an append log the skill reads + truncates on its next
-- run. Many replies accrue between skill runs, so it is a log, not the
-- single-slot bridge notify.xml is. Per-savegame for the same reason the cards
-- are: an ack for save A must not be ingested as save B's answer.
FarmManager25.REPLIES_NAME    = "replies.xml"
-- The FARM table Cyrus publishes for THIS savegame. ⛔ PERSISTENT: unlike
-- notify.xml it is NEVER consumed-and-deleted -- see readFarmFile. Written by
-- the Python half, read-only to Lua. Per-savegame for the same reason the
-- cards are (BUG-027): money, land, contracts and fleet are properties of a
-- SAVEGAME, not of the machine.
FarmManager25.FARM_NAME       = "farm.xml"
-- The document schema this reader understands. Must track SCHEMA_VERSION in
-- emit_farm_xml.py; readFarmFile refuses a document stamped anything else
-- rather than reading v2 semantics as though they were v1.
FarmManager25.FARM_SCHEMA     = 1
-- The LIVE contract rewards, written by THIS mod for the skill to read back
-- (plan item 5a). It exists because the figure is absent from the savegame, not
-- merely unparsed: AbstractMission:saveToXMLFile writes `.info#reward` from
-- `self.reward`, which the game leaves at 0 while a field-tied contract is only
-- OFFERED and computes at accept-time (FRICTION-LOG F-025). Same folder, same
-- per-savegame reason (BUG-027) and the same direction of travel as replies.xml:
-- Lua writes, Python reads. NEVER inside the savegame folder -- the published
-- "100% read-only" promise holds by construction, because saveFolder is
-- modSettings/<MOD>/<savegameKey>/ and nothing here composes any other path.
FarmManager25.CONTRACTS_NAME  = "contracts.xml"
FarmManager25.CHECK_INTERVAL_MS = 200      -- ~5x/sec: imperceptible, cheap
FarmManager25.PROTOCOL          = 4
FarmManager25.MAX_REPLIES       = 64       -- bound: a skill that never ingests must not grow the file forever
FarmManager25.DEFAULT_TITLE     = "FARM MANAGER"
FarmManager25.MAX_QUEUE         = 8        -- bound: a runaway sender must not eat memory
FarmManager25.MAX_ACTIONS       = 6        -- bound: <action> / <option> elements read per card
-- The card STORE bound. Visibility is decided at render time (renderStack
-- keeps the newest cards that fit on screen and says "+N more" for the
-- rest), so this bounds MEMORY, not the screen -- and eviction is printed,
-- because a silently vanished card is exactly the LT-5 failure.
FarmManager25.MAX_STORE         = 16
-- ⛔ RETENTION (TECH-DEBT-060). MAX_STORE bounds the LIVE stack; these bound the
-- RETAINED TRANSCRIPT -- the cards that have LEFT the stack. This mod is the only
-- component that ever holds a card's TEXT: writeReply records id/action/gameTime/
-- realTime and nothing else, so before this the correlation id outlived the very
-- question it referred to, and 49 live exchanges were unreconstructable
-- afterwards. Retention is what makes an answered exchange readable later.
--
-- ⛔ THE SEPARATION THAT MATTERS: `retained` is a DIFFERENT TABLE from `stack`
-- (see the declaration below). renderStack never reads it, so retaining 100
-- cards puts ZERO extra cards on the player's HUD. That is the same distinction
-- MAX_STORE's comment above already draws -- a store bound, not a screen bound --
-- applied to history instead of to memory.
FarmManager25.RETENTION_PRESETS = {0, 25, 50, 100, 200}
FarmManager25.DEFAULT_RETENTION = 100
-- Derived, never typed twice. storeBound() must cover the largest cap any
-- stepper -- or a hand-edited settings.xml -- can select, and "two fields bearing
-- one answer, only one of them checked" is this project's founding defect class.
-- Computed from the presets, so it cannot disagree with them.
FarmManager25.RETENTION_MAX = 0
for _, v in ipairs(FarmManager25.RETENTION_PRESETS) do
    if v > FarmManager25.RETENTION_MAX then
        FarmManager25.RETENTION_MAX = v
    end
end
-- The live cap (settings row 8). Clamped into [0, RETENTION_MAX] at every point
-- it is set, which is what makes storeBound() a true upper bound on what
-- saveCards can write.
FarmManager25.retentionCap = FarmManager25.DEFAULT_RETENTION

--- The ONE bound BOTH cards.xml paths use. saveCards writes at most MAX_STORE
--  live + retentionCap (<= RETENTION_MAX) retained cards; loadCards reads at
--  most this many back. ⛔ Deriving both ends from one function is what makes
--  "the write cap and the read cap disagree, so cards vanish on restart"
--  structurally impossible rather than merely tested for -- a defect that only
--  appears after a reload is exactly the kind this project ships by accident.
function FarmManager25.storeBound()
    return FarmManager25.MAX_STORE + FarmManager25.RETENTION_MAX
end
FarmManager25.LINGER_MS         = 6000     -- a new card tops older ones up to at least this
FarmManager25.MAX_LINES         = 6        -- bound: a panel must not swallow the screen
FarmManager25.MAX_BODY_LINES    = 24       -- bound: how many <line> elements we will read
-- How long a message stays up IN OFF MODE (overlay ON never expires cards).
-- The first real-game test read as too fast: a 60-char message got
-- 3000 + 60*45 = 5.7s, fine for "read this word", far too quick for "read
-- this, decide, act". The S155 owner test raised the floor again: 15s is the
-- read-and-decide window. All three are overridable in settings.xml.
FarmManager25.MIN_TTL_MS        = 15000
FarmManager25.MAX_TTL_MS        = 60000
FarmManager25.MS_PER_CHAR       = 70       -- reading speed -> auto duration
FarmManager25.FADE_IN_MS        = 160
FarmManager25.FADE_OUT_MS       = 260

-- Factory defaults, kept as named constants so the settings page's "reset
-- position" and scale/linger cycles have a stable origin even after
-- loadSettings/loadState have mutated the live DESIGN values. DESIGN seeds its
-- anchor/scale from these (one source of truth); reset restores them.
FarmManager25.DEFAULT_ANCHOR_X  = 0.985
FarmManager25.DEFAULT_ANCHOR_Y  = 0.86
FarmManager25.DEFAULT_UI_SCALE  = 0.72
-- Settings-page cycle presets (S158). Scale steps span the buildOverlays clamp
-- (0.4-1.5); linger steps are the OFF-mode floor MIN_TTL_MS in ms.
FarmManager25.SCALE_PRESETS     = {0.5, 0.6, 0.72, 0.85, 1.0, 1.25}
FarmManager25.LINGER_PRESETS_MS = {10000, 15000, 30000, 60000}
-- Steps for the four knobs loadSettings has ALWAYS honoured and no GUI ever
-- exposed (hud#widthPx, hud#textSizePx, hud#bgAlpha -> cardAlpha, timing#maxMs).
-- ⭐ ZERO NEW BEHAVIOUR: the code already reads all four -- players simply could
-- not reach them without hand-editing settings.xml. Each list is centred on the
-- live DESIGN default so the factory value is one of the steps and the stepper
-- opens where the player already is.
FarmManager25.WIDTH_PRESETS_PX    = {260, 300, 330, 380, 440, 520}
FarmManager25.TEXTSIZE_PRESETS_PX = {11, 12, 13, 15, 17, 20}
FarmManager25.ALPHA_PRESETS       = {0.5, 0.65, 0.8, 0.92, 1.0}
FarmManager25.MAXTTL_PRESETS_MS   = {30000, 60000, 120000, 300000}

-- Severity -> the NAME of the native constant to fall back to (names, not
-- values: the constant is resolved at runtime so an engine that lacks WARNING
-- degrades instead of erroring) + the default glyph. Card COLOURS live in
-- FarmManager25.THEME.cards (FarmManagerTheme.lua) -- its keys MUST cover
-- every severity key here.
FarmManager25.SEVERITIES = {
    ok       = { native = "OK",       icon = "check"    },
    info     = { native = "INFO",     icon = "leaf"     },
    warn     = { native = "WARNING",  icon = "alert"    },
    critical = { native = "CRITICAL", icon = "critical" },
}
FarmManager25.DEFAULT_SEVERITY = "info"
-- Severity RANK (settings row 9, "minimum severity shown"). SEVERITIES above is a
-- hash and therefore carries no order, so the ordering is stated once, here,
-- beside it -- not re-derived at each call site. The two MUST cover the same
-- keys; severityRank returns 0 for anything it does not know, and the render
-- gate treats 0 as "always show" rather than "below the floor". A card we cannot
-- rank must still be drawn, for the same reason buildNotification shows an
-- unknown severity as info instead of swallowing the message.
FarmManager25.SEVERITY_ORDER = {"ok", "info", "warn", "critical"}
-- The live render floor. "ok" is rank 1, the bottom, so the factory default
-- shows everything. ⛔ THIS GATES THE HUD ONLY -- getMessageLog returns every
-- retained card regardless. A transcript that hides messages would rebuild the
-- hole retention exists to fill.
FarmManager25.minSeverity = "ok"

function FarmManager25.severityRank(severity)
    for i, key in ipairs(FarmManager25.SEVERITY_ORDER) do
        if key == severity then
            return i
        end
    end
    return 0
end

-- Atlas regions, in atlas pixels. MIRRORS build_atlas.py -- change one, change
-- both. The card is 3-sliced: caps keep their corner radius at any width, the
-- middle is uniform left-to-right so stretching it is invisible.
-- 2048x1024 (task103-item14, BP-070): the PROCEDURAL card/pill cells grew to
-- 256 -- at 4K x1.5 HUD scale a card draws ~168px tall, so the old 128px cell
-- was upscaling on screen (the primary blur mechanism). The icon grid STAYS
-- at 128px cells: the owner sheets are 126-204px native, so bigger cells
-- could only be filled by upscaling the art in the build (worse, and a build
-- error there) -- 128 still covers the 40*3=120px worst-case draw. Slice
-- RATIOS (CARD_CAP/CARD_PX) unchanged, so on-screen geometry is identical.
-- Non-square power-of-two is proven (Courseplay iconSprite.dds 256x512).
FarmManager25.ATLAS_W    = 2048
FarmManager25.ATLAS_H    = 1024
-- The atlas file, mod-root-relative. ONE literal, because two would drift:
-- the HUD resolves it at loadMap and setGlyph resolves it per glyph, and a
-- rename that updated only one would leave the menu sampling a texture that
-- no longer exists -- silently, because setImageFilename cannot report a
-- missing file (GuiOverlay.createOverlay just leaves overlay.overlay unset).
FarmManager25.ATLAS_FILE = "textures/fm25_atlas.dds"
FarmManager25.CARD_PX    = 256
FarmManager25.CARD_CAP   = 80
FarmManager25.UV_CARD_L  = {0,   0, 80, 256}
FarmManager25.UV_CARD_M  = {80,  0, 96, 256}
FarmManager25.UV_CARD_R  = {176, 0, 80, 256}
FarmManager25.UV_PILL_L  = {256, 0, 80, 256}
FarmManager25.UV_PILL_M  = {336, 0, 96, 256}
FarmManager25.UV_PILL_R  = {432, 0, 80, 256}
FarmManager25.ICONS = {
    leaf      = {  0, 256, 128, 128},
    alert     = {128, 256, 128, 128},
    check     = {256, 256, 128, 128},
    briefing  = {384, 256, 128, 128},
    contract  = {512, 256, 128, 128},
    silo      = {640, 256, 128, 128},
    fleet     = {768, 256, 128, 128},
    finances  = {896, 256, 128, 128},
    crop      = {  0, 384, 128, 128},
    weather   = {128, 384, 128, 128},
    harvest   = {256, 384, 128, 128},
    field     = {384, 384, 128, 128},
    report    = {512, 384, 128, 128},
    equipment = {640, 384, 128, 128},
    fuel      = {768, 384, 128, 128},
    building  = {896, 384, 128, 128},
    supply    = {  0, 512, 128, 128},
    schedule  = {128, 512, 128, 128},
    profit    = {256, 512, 128, 128},
    worker    = {384, 512, 128, 128},
    dealer    = {512, 512, 128, 128},
    soil      = {640, 512, 128, 128},
    season    = {768, 512, 128, 128},
    -- Interaction affordances (TASK-101 P1). Appended AFTER every pre-existing
    -- glyph so the UV layout order is stable; slots follow build_atlas.py's
    -- 8-per-row order.
    thumb_up   = {896, 512, 128, 128},
    thumb_down = {  0, 640, 128, 128},
    chat       = {128, 640, 128, 128},
    send       = {256, 640, 128, 128},
    gear       = {384, 640, 128, 128},
    close      = {512, 640, 128, 128},
    -- TASK-101 P2 (owner icon sheet 4). Same append-only rule: slots 29/30.
    snooze     = {640, 640, 128, 128},
    critical   = {768, 640, 128, 128},
}
-- The header banner: owner art in COLOUR (everything else in the atlas is
-- white-on-alpha). Blitted with a {1,1,1,1} tint. TWO packed sizes
-- (task103-item14, BP-070 R4): with no mipmaps, detailed colour art turns to
-- mush past ~2x minification, and the banner's draw width spans ~238 physical
-- px (1080p x0.72) to 990 (4K x1.5). drawBanner picks the smallest slot that
-- still covers the frame's actual pixel width. Both keep the plate's own
-- 5.16:1 aspect; the on-screen height derives from the panel width so the art
-- is never stretched. MIRRORS build_atlas.py's BANNER_XY/WH + BANNER_SM_XY/WH.
FarmManager25.UV_BANNER    = {0, 768, 1280, 248}
FarmManager25.UV_BANNER_SM = {1280, 768, 516, 100}


-- Design tokens. Pixels at the reference screen height; converted to
-- normalized space in loadMap so the panel is identical at 1080p and 4K.
FarmManager25.DESIGN = {
    panelWidthPx   = 330,
    -- Card interior paddings, MEASURED off the mockup at its 891px->330
    -- scale (S155, LT-2): x ~17 (icon left pad AND icon->text gap), y ~22
    -- (card edge to title top / body bottom). The old single 12 was a guess;
    -- the mockup is airier than it, not tighter.
    paddingXPx     = 17,
    paddingYPx     = 22,
    cardGlyphPx    = 40,     -- the card's glyph, drawn straight on the card bg (mockup-confirmed)
    iconGlyphPx    = 22,     -- affordance-row glyph
    titleSizePx    = 17,     -- mockup title cap-band 12.6dp -> ~17px em (was 15)
    bodySizePx     = 13,     -- mockup-confirmed
    timeSizePx     = 13,
    lineGapPx      = 3,
    titleGapPx     = 12,     -- mockup title-baseline -> body-top gap ~12-14dp (was 5)
    cardGapPx      = 9,      -- mockup-confirmed (9.6dp)
    -- S157: the visible card window is capped at a FIXED count, not the screen
    -- height. Before this, the only limit was "don't draw below the screen
    -- edge", so 8 modest cards legitimately filled ~80% of the screen. The cap
    -- is measured as this many AVERAGE cards' worth of height (renderStack), so
    -- it is a soft ~4, not a hard count: a stack of tall cards shows fewer, and
    -- older cards beyond the window scroll into view on the mouse wheel.
    maxVisibleCards = 4,
    pillGapPx      = 9,      -- gap between the banner header and the first card
    affordHeightPx = 26,     -- affordance button height
    affordWidthPx  = 40,
    affordGapPx    = 6,
    cardAlpha      = 0.92,
    timeColor      = {0.62, 0.68, 0.62, 1},
    -- Scrollbar (item 18): a click/drag affordance on the card window, drawn
    -- only when scrollMax > 0. A thin vertical bar at the panel's right inset,
    -- in its OWN reserved lane outside the content column (task103-item14,
    -- BP-070: gap >= the inter-card gap and >= 2x the track width) -- cards
    -- never share pixels with the track. The lane is reserved whether or not
    -- the bar is drawn, so card width never jumps when it appears.
    -- Track dim; thumb is the muted timeColor tone at full alpha so it reads
    -- against the track. Rides the button path, so it scrolls with zero camera
    -- movement (unlike the wheel). The hit rect is wider than the 4px visual
    -- (BP-070: 12-16 ref-px minimum target) -- grabbable without being fat.
    scrollBarWidthPx = 4,
    scrollThumbMinPx = 24,
    scrollGapPx      = 9,     -- card right edge -> track (= cardGapPx, >= 2x track)
    scrollHitWidthPx = 14,    -- click/drag target centred on the visual track
    scrollTrackColor = {0.24, 0.27, 0.24, 0.55},
    scrollThumbColor = {0.62, 0.68, 0.62, 0.95},
    -- Anchor: top-right, tucked under the money/clock bar, clear of the
    -- bottom-right minimap and of AutoDrive/Courseplay's left-side HUDs.
    anchorX        = FarmManager25.DEFAULT_ANCHOR_X,
    anchorY        = FarmManager25.DEFAULT_ANCHOR_Y,
    -- LT-7: one uniform scale on the whole overlay, applied at the single
    -- px->normalized chokepoint (buildOverlays). 0.72 is the owner's ~28%
    -- reduction -- the overlay dwarfed the neighbouring CP/AD HUDs. Tunable
    -- live via settings.xml (farmManager25.hud#scale), clamped 0.4-1.5.
    uiScale        = FarmManager25.DEFAULT_UI_SCALE,
}

-- ⛔⛔ DEC-216 (owner ruling 2026-09-17, "Convert them to match"): timeColor,
-- scrollTrackColor and scrollThumbColor are DISPLAY values and are converted
-- like every THEME colour. (Review M2 had left them unconverted for want of
-- provenance; the owner overruled that.)
-- ⛔ CONVERTED AT THE POINT OF USE, NEVER AS A COPY OF DESIGN. The SETTINGS tab
-- writes DESIGN at runtime; a converted snapshot would freeze the player's
-- settings at load values. The blit() sink converts the dismiss glyph and the
-- scrollbar; the two overflow lines are setTextColor calls, which bypass the
-- sink, so each converts at its own call site.

FarmManager25.filePath      = nil
FarmManager25.timeSinceCheck = 0
FarmManager25.queue         = {}
FarmManager25.stack         = {}      -- live cards, OLDEST FIRST (top of screen)
-- ⛔ THE TRANSCRIPT, and it is a DIFFERENT TABLE from `stack` ON PURPOSE
-- (TECH-DEBT-060). Cards that LEAVE the stack -- evicted, OFF-mode expired,
-- answered, dismissed, or wiped by the draw-failure latch -- land here instead
-- of being destroyed. Also OLDEST FIRST, so its cap drops the oldest exactly the
-- way MAX_STORE does.
-- ⛔ renderStack NEVER reads this table, and that is the invariant to protect:
-- retaining 100 cards must not put 100 cards on the player's HUD. If a future
-- change makes renderStack walk `retained`, the separation is gone and history
-- starts drawing itself onto the screen.
FarmManager25.retained      = {}
FarmManager25.overlaysOk    = false
FarmManager25.useNativeOnly = false   -- set true and latched if drawing ever throws
FarmManager25.atlasId       = nil
FarmManager25.stateFolder   = nil     -- modSettings/<MOD>/ -- where state.xml (the HUD block) lives; nil until loadMap
-- modSettings/<MOD>/<savegameKey>/ -- where THIS savegame's cards.xml,
-- notify.xml and replies.xml live. nil when the savegame has no directory yet
-- (a never-saved new game, or a multiplayer client on a remote host): that case
-- SKIPS persistence entirely and must never fall back to stateFolder, which is
-- exactly the shared file this scoping exists to eliminate.
FarmManager25.saveFolder    = nil
FarmManager25.headerRect    = nil     -- the drag handle's rect, recorded each drawn frame
FarmManager25.dragOffset    = nil     -- nil = not dragging; else grab offset from the anchor
-- The interactive layer (P2). affordanceRects mirrors headerRect's discipline:
-- rebuilt every drawn frame, nil on every path that does not draw -- an
-- invisible button must not be clickable.
FarmManager25.affordanceRects   = nil
FarmManager25.interactiveOk     = true   -- latched false if the layer ever fails; cards then render one-way
FarmManager25.hookInstalled     = false  -- the registerGlobalPlayerActionEvents hook goes in exactly once
-- The overlay mode (S155, LT-1). ON (the default) = persistent always-on
-- panel, cards never auto-expire; OFF = the original transient notifier.
-- Persisted in state.xml so the player's choice survives the session.
FarmManager25.overlayOn         = true
-- The reply bar's hit rect (LT-4). Same discipline as headerRect: recorded
-- each drawn frame, nil on every path that does not draw.
FarmManager25.inputBarRect      = nil
-- Uniquifies free-text reply ids within a session. ⛔ PERSISTED IN THE ROOT
-- state.xml, NOT in the per-savegame file, and that is a CORRECTNESS rule, not
-- a preference: the id is "text-<seq>" alone, so a counter that restarted per
-- savegame would let two saves both emit "text-5" and the (id, action) dedup in
-- writeReply would silently swallow the second message. Do not "tidy" this into
-- cards.xml.
FarmManager25.textReplySeq      = 0
-- LT-8: the coalesced-persist flag. Any stack mutation (arrival, eviction,
-- dismiss, answer, OFF-mode expiry) sets it; update() flushes state.xml once
-- per tick, so state.xml always mirrors the live stack.
FarmManager25.stateDirty        = false
-- S157: the mouse-wheel scroll offset -- how many of the NEWEST cards the
-- visible window is scrolled PAST. 0 = anchored on the newest (the default a
-- new arrival snaps back to); clamped each drawn frame in renderStack to a
-- full last page. panelRect is the whole-panel bounds the wheel hit-tests
-- against -- recorded each drawn frame, nil on every path that does not draw
-- (the headerRect discipline: an off-screen panel must not eat the wheel).
FarmManager25.scrollOffset      = 0
FarmManager25.panelRect         = nil
-- Scrollbar (item 18): the track + thumb hit rects and the in-flight drag,
-- same discipline as panelRect -- rebuilt every drawn frame, nil on every path
-- that does not draw. scrollDrag is nil unless a thumb-drag is in flight (then
-- { grab = cursorY - thumbBottomY }); scrollTravel/scrollRange carry the
-- render-time geometry the drag needs to map a thumb Y back to a scroll offset.
FarmManager25.scrollbarRect     = nil
FarmManager25.scrollThumbRect   = nil
FarmManager25.scrollDrag        = nil
FarmManager25.scrollTravel      = 0
FarmManager25.scrollRange       = 0
-- (`settingsGui` and `settingsGuiLoaded` stood here. Both were the S158 modal's
-- registration latch; deleting registerSettingsGui and repointing the keybind at
-- the in-game menu orphaned them, so they went with it. The keybind no longer
-- depends on anything having registered: the menu is the base game's own screen.)


-- ---------------------------------------------------------------------------
-- helpers
-- ---------------------------------------------------------------------------

local function clamp(v, lo, hi)
    if v < lo then return lo end
    if v > hi then return hi end
    return v
end

--- Show a notification through the game's own box. One line only -- the native
--  API takes exactly (type, text) -- so flatten, and prefix the title since there
--  is nowhere else to put it.
function FarmManager25.showNative(n)
    if g_currentMission == nil then
        return
    end
    local sev = FarmManager25.SEVERITIES[n.severity] or FarmManager25.SEVERITIES[FarmManager25.DEFAULT_SEVERITY]
    local flat = n.body:gsub("%s*\n%s*", "  ")
    g_currentMission:addIngameNotification(FarmManager25.resolveNativeType(sev.native),
                                           n.title .. ": " .. flat)
end

function FarmManager25.resolveNativeType(name)
    -- WARNING was not observed in any shipped mod, so it is not assumed to
    -- exist. Look it up; fall back to INFO if the engine does not define it.
    local t = FSBaseMission["INGAME_NOTIFICATION_" .. tostring(name)]
    if t == nil then
        t = FSBaseMission.INGAME_NOTIFICATION_INFO
    end
    return t
end

function FarmManager25.splitLines(text)
    local out = {}
    for line in (text .. "\n"):gmatch("([^\n]*)\n") do
        table.insert(out, (line:gsub("%s+$", "")))
    end
    -- drop trailing blank lines
    while #out > 0 and out[#out] == "" do
        table.remove(out)
    end
    return out
end

--- Word-wrap `text` to `maxWidth`, honouring explicit newlines.
--  Hard-breaks any single word wider than the panel rather than letting it
--  bleed outside the background.
function FarmManager25:wrapText(text, fontSize, maxWidth)
    local lines = {}
    for _, paragraph in ipairs(FarmManager25.splitLines(text)) do
        if paragraph == "" then
            table.insert(lines, "")
        else
            local line = nil
            for word in paragraph:gmatch("%S+") do
                local w = word
                local candidate = (line == nil) and w or (line .. " " .. w)
                if getTextWidth(fontSize, candidate) <= maxWidth then
                    line = candidate
                else
                    if line ~= nil then
                        table.insert(lines, line)
                        line = nil
                    end
                    -- a single word too wide for the panel: cut it
                    while getTextWidth(fontSize, w) > maxWidth and w:len() > 1 do
                        local cut = w:len()
                        while cut > 1 and getTextWidth(fontSize, w:sub(1, cut)) > maxWidth do
                            cut = cut - 1
                        end
                        table.insert(lines, w:sub(1, cut))
                        w = w:sub(cut + 1)
                    end
                    line = w
                end
            end
            if line ~= nil then
                table.insert(lines, line)
            end
        end
    end

    if #lines > FarmManager25.MAX_LINES then
        local trimmed = {}
        for i = 1, FarmManager25.MAX_LINES do
            trimmed[i] = lines[i]
        end
        -- Signal truncation rather than pretending the message ended here. The
        -- "make the ellipsis room first, then append it -- else it bleeds PAST
        -- the panel edge" logic lives in ellipsize now (the title reuses it).
        -- force=true because a dropped-lines tail must carry the mark even when
        -- the wrapped last line already fits maxWidth exactly.
        trimmed[FarmManager25.MAX_LINES] =
            FarmManager25.ellipsize(trimmed[FarmManager25.MAX_LINES], fontSize, maxWidth, true)
        return trimmed, true
    end
    return lines, false
end

--- Truncate `text` to a single line no wider than `maxWidth`, trimming from the
--  end and appending an ellipsis. Shared by the card title (which MUST stay one
--  line -- cardHeight budgets exactly one titleSize for it) and wrapText's
--  overflow tail, so the "give the ellipsis room, then append" measurement is
--  written once. `force` appends the ellipsis even when `text` already fits:
--  wrapText's dropped-lines case needs the mark regardless, while the title
--  omits it so a short title renders verbatim.
function FarmManager25.ellipsize(text, fontSize, maxWidth, force)
    if not force and getTextWidth(fontSize, text) <= maxWidth then
        return text
    end
    local ELL = " ..."
    local s = text
    while s:len() > 0 and getTextWidth(fontSize, s .. ELL) > maxWidth do
        s = s:sub(1, s:len() - 1)
    end
    return (s:gsub("%s+$", "")) .. ELL
end

--- Turn raw field values into a notification table. PURE -- no file I/O, no
--  engine calls -- so it is fully testable and so pollBridge stays a thin shell
--  around the XML reader.
--  Returns nil only when there is genuinely nothing to show.
function FarmManager25.buildNotification(severity, title, ttlRaw, bodyLines, icon, id, actions)
    local body = table.concat(bodyLines or {}, "\n")
    body = body:gsub("%s+$", "")
    if body == "" then
        return nil
    end

    severity = tostring(severity or ""):lower()
    if FarmManager25.SEVERITIES[severity] == nil then
        -- An unknown severity is a sender bug, not a reason to swallow the
        -- message. Show it as info rather than not at all.
        severity = FarmManager25.DEFAULT_SEVERITY
    end

    local displayTitle = tostring(title or "")
    if displayTitle == "" then
        displayTitle = FarmManager25.DEFAULT_TITLE
    end

    local ttlMs = tonumber(ttlRaw) or 0
    if ttlMs <= 0 then
        ttlMs = FarmManager25.MIN_TTL_MS + body:len() * FarmManager25.MS_PER_CHAR
    end
    ttlMs = clamp(ttlMs, FarmManager25.MIN_TTL_MS, FarmManager25.MAX_TTL_MS)

    -- An unknown icon name falls back to the severity's default rather than
    -- dropping the card or drawing nothing.
    local glyph = tostring(icon or ""):lower()
    if FarmManager25.ICONS[glyph] == nil then
        glyph = FarmManager25.SEVERITIES[severity].icon
    end

    -- Protocol 4. A card that offers <actions> MUST carry an id -- a reply
    -- needs something to reference. Enforced here, at build time, so later
    -- phases never see an id-less actions card. Trimmed first: a whitespace-only
    -- id="  " is no id at all, and surrounding whitespace must not make two
    -- copies of the same correlation id compare unequal.
    id = (tostring(id or ""):gsub("^%s*(.-)%s*$", "%1"))
    if id == "" then
        id = nil
    end
    if actions ~= nil and id == nil then
        print("FarmManager25: <actions> on a card with no id -- actions dropped (a reply would have nothing to reference)")
        actions = nil
    end

    return {
        severity = severity,
        title    = displayTitle:upper(),
        body     = body,
        icon     = glyph,
        ttl      = ttlMs,
        age      = 0,
        -- Stamped on ARRIVAL, not on draw: the time the farm manager said it,
        -- which is what a transcript means. Nil if the clock is unreadable.
        stamp    = FarmManager25.gameClock(),
        -- The DAY half of that same stamp, captured at the same moment so the
        -- two can never disagree about when a card arrived. Nil when the day is
        -- unreadable -- see gameDay(). MESSAGES groups on this.
        day      = FarmManager25.gameDay(),
        lines    = nil,   -- wrapped lazily in draw, where getTextWidth is meaningful
        -- Protocol 4: drawCard renders an affordance row for these, and a
        -- click echoes the id into replies.xml (the correlation key).
        id       = id,       -- correlation id; nil on protocol-3 cards
        actions  = actions,  -- parsed <actions> list; nil when absent/dropped
    }
end

--- Read the optional <actions> block (protocol 4). Returns a list of
--  { type = "...", options = {{value=..., label=...}, ...} } entries, or nil
--  when the block is absent or holds nothing usable. An <action> with no type
--  is a sender bug in ONE entry -- skip it, never drop the card over it.
--  Types and options are retained as sent, not validated against a taxonomy:
--  what is renderable is the render phase's decision, not the reader's.
function FarmManager25.parseActions(xml, root)
    local base = root .. ".actions"
    if not xml:hasProperty(base) then
        return nil
    end
    local actions = {}
    for i = 0, FarmManager25.MAX_ACTIONS - 1 do
        local key = string.format("%s.action(%d)", base, i)
        if not xml:hasProperty(key) then
            break
        end
        local actionType = xml:getString(key .. "#type")
        if actionType ~= nil and actionType ~= "" then
            local action = { type = actionType:lower() }
            local options = {}
            for j = 0, FarmManager25.MAX_ACTIONS - 1 do
                local optKey = string.format("%s.option(%d)", key, j)
                if not xml:hasProperty(optKey) then
                    break
                end
                table.insert(options, {
                    value = xml:getString(optKey .. "#value"),
                    label = xml:getString(optKey),
                })
            end
            -- Say when the bound cuts something off (LOW-2): rendering starts
            -- this phase, and a silently missing affordance would read as a
            -- sender bug rather than a cap.
            if xml:hasProperty(string.format("%s.option(%d)", key, FarmManager25.MAX_ACTIONS)) then
                print(string.format("FarmManager25: more than %d <option> elements on one <action> -- extras ignored",
                    FarmManager25.MAX_ACTIONS))
            end
            if #options > 0 then
                action.options = options
            end
            table.insert(actions, action)
        end
    end
    if xml:hasProperty(string.format("%s.action(%d)", base, FarmManager25.MAX_ACTIONS)) then
        print(string.format("FarmManager25: more than %d <action> elements on one card -- extras ignored",
            FarmManager25.MAX_ACTIONS))
    end
    if #actions == 0 then
        return nil
    end
    return actions
end


-- ---------------------------------------------------------------------------
-- lifecycle
-- ---------------------------------------------------------------------------

--- Consume the bridge. Returns true if it no longer holds a notification.
--
--  deleteFile called from a mod's own environment is REFUSED for modSettings
--  paths -- the real game says:
--      Error: No access to folder '...modSettings/FarmManager25/notify.xml'
--  ...450 times, because the file survived and every 200ms poll re-read the same
--  message, refilled the queue and re-showed the panel.
--
--  FS25 hands mods a SANDBOXED global environment. getfenv(0) reaches the
--  engine's real one. AutoDrive does exactly this to delete its own route files
--  under modSettings/FS25_AutoDrive/routesManager/routes/ (RoutesManager.lua:162
--  and :75) and never calls plain deleteFile -- two getfenv(0).deleteFile sites,
--  zero plain ones. That asymmetry WAS the answer, and it was in its source the
--  whole time.
function FarmManager25.consumeBridge(path)
    local ok = pcall(function() getfenv(0).deleteFile(path) end)
    if ok and not fileExists(path) then
        return true
    end

    -- Fallback: overwrite with a valid but EMPTY document. Write mode is the one
    -- thing FS25's io sandbox does permit. It must stay valid XML -- truncating
    -- to zero bytes would make every future poll fail to parse and spam the log.
    -- A spent bridge is then simply ignored (see pollBridge), never re-consumed,
    -- so a failing delete can never become a 5x/sec retry loop.
    pcall(function()
        local f = io.open(path, "w")
        if f ~= nil then
            f:write("<farmManager25/>")
            f:close()
        end
    end)
    return not fileExists(path)
end


function FarmManager25:loadSettings(folder)
    local path = folder .. FarmManager25.SETTINGS_NAME
    if not fileExists(path) then
        return
    end
    -- Wrapped: a corrupt settings file must not take the notifier down with it.
    local ok, err = pcall(function()
        local xml = loadXMLFile("FarmManager25Settings", path)
        if xml == nil or xml == 0 then
            return
        end
        local d = FarmManager25.DESIGN
        d.anchorX      = getXMLFloat(xml, "farmManager25.hud#anchorX")      or d.anchorX
        d.anchorY      = getXMLFloat(xml, "farmManager25.hud#anchorY")      or d.anchorY
        d.panelWidthPx = getXMLFloat(xml, "farmManager25.hud#widthPx")      or d.panelWidthPx
        d.bodySizePx   = getXMLFloat(xml, "farmManager25.hud#textSizePx")   or d.bodySizePx
        -- LT-7: the overlay scale, tunable live between owner looks without a
        -- rebuild. Clamped 0.4-1.5 (buildOverlays clamps again defensively).
        local scale    = getXMLFloat(xml, "farmManager25.hud#scale")
        if scale ~= nil then d.uiScale = clamp(scale, 0.4, 1.5) end
        -- F-T101-1: this wrote to d.bgColor, a key DESIGN has never had -- the
        -- real field is cardAlpha (the one drawCard multiplies in). Indexing the
        -- nil bgColor threw inside this pcall, so ANY settings.xml that set
        -- bgAlpha silently aborted the whole settings load.
        local a        = getXMLFloat(xml, "farmManager25.hud#bgAlpha")
        if a ~= nil then d.cardAlpha = clamp(a, 0, 1) end

        -- Timing: tune how long messages linger without touching the mod.
        local minTtl   = getXMLFloat(xml, "farmManager25.timing#minMs")
        local maxTtl   = getXMLFloat(xml, "farmManager25.timing#maxMs")
        local perChar  = getXMLFloat(xml, "farmManager25.timing#msPerChar")
        if minTtl  ~= nil then FarmManager25.MIN_TTL_MS  = minTtl end
        if maxTtl  ~= nil then FarmManager25.MAX_TTL_MS  = maxTtl end
        if perChar ~= nil then FarmManager25.MS_PER_CHAR = perChar end

        -- TECH-DEBT-060: the transcript cap and the HUD severity floor are
        -- seedable here like every other knob, so a power-user file keeps
        -- working. The live store (state.xml, loaded AFTER this) still wins --
        -- see loadState. Clamped into [0, RETENTION_MAX] so a hand-edited cap
        -- can never exceed the bound loadCards reads back at.
        local keep = getXMLFloat(xml, "farmManager25.messages#retain")
        if keep ~= nil then
            FarmManager25.retentionCap =
                clamp(math.floor(keep), 0, FarmManager25.RETENTION_MAX)
        end
        local minSev = getXMLString(xml, "farmManager25.messages#minSeverity")
        if minSev ~= nil then
            if FarmManager25.severityRank(minSev) > 0 then
                FarmManager25.minSeverity = minSev
            else
                -- Say so. An unrecognised severity NAME is a typo the player
                -- would otherwise never find -- their filter would simply not
                -- work, which reads as the mod ignoring them. Keeping the
                -- default silently is how absence starts looking like data.
                print("FarmManager25: settings.xml messages#minSeverity '"
                    .. tostring(minSev) .. "' is not a known severity -- ignored")
            end
        end
        delete(xml)
    end)
    if not ok then
        print("FarmManager25: settings.xml unreadable, using defaults -- " .. tostring(err))
    end
end

--- Load the mod-written client store -- the HUD block ONLY. Runs AFTER
--  loadSettings so the live store (a position the player dragged to) wins over
--  the hand-edited seed. Same engine XML API and the same discipline as
--  loadSettings: wrapped, and a corrupt file costs the stored position/mode,
--  never the notifier.
--
--  `folder` is the ROOT modSettings/<MOD>/ folder, machine-global on purpose:
--  panel position, scale and TTLs are a function of the monitor, not of a farm.
--  The CARDS moved out to loadCards() and the per-savegame cards.xml.
--
--  The legacy <cards> element written by <= v3.0.0.0 lives in this same file and
--  is now simply NEVER READ. That is the migration: those cards carry no
--  savegame stamp, no map id and no farm id, so attributing them to whichever
--  save loads first would stamp one farm's plans as another's -- a visible bug
--  converted into an invisible one. They discard themselves.
function FarmManager25:loadState(folder)
    local path = folder .. FarmManager25.STATE_NAME
    if not fileExists(path) then
        return
    end
    local ok, err = pcall(function()
        local xml = loadXMLFile("FarmManager25State", path)
        if xml == nil or xml == 0 then
            return
        end
        local d = FarmManager25.DESIGN
        d.anchorX = getXMLFloat(xml, "farmManager25State.hud#anchorX") or d.anchorX
        d.anchorY = getXMLFloat(xml, "farmManager25State.hud#anchorY") or d.anchorY
        local mode = getXMLString(xml, "farmManager25State.hud#overlayOn")
        if mode ~= nil then
            FarmManager25.overlayOn = (mode ~= "false")
        end
        -- The free-text reply counter is monotonic ACROSS sessions: with a
        -- dead clock the id is "text-<seq>" alone, and a counter that reset
        -- on relog would re-emit an old id -- the (id, action) dedup would
        -- then silently swallow the new message. floor(): the engine hands
        -- floats back; the id must never render as "4.0".
        local seq = getXMLFloat(xml, "farmManager25State.hud#textReplySeq")
        if seq ~= nil then
            FarmManager25.textReplySeq = math.floor(seq)
        end
        -- S158: settings-page scale + OFF-mode linger. Scale is clamped to the
        -- buildOverlays range (loadState runs BEFORE buildOverlays, so the
        -- persisted scale seeds the first geometry build).
        local uiScale = getXMLFloat(xml, "farmManager25State.hud#uiScale")
        if uiScale ~= nil then d.uiScale = clamp(uiScale, 0.4, 1.5) end
        local minTtl = getXMLFloat(xml, "farmManager25State.hud#minTtlMs")
        if minTtl ~= nil then FarmManager25.MIN_TTL_MS = minTtl end
        local maxTtl = getXMLFloat(xml, "farmManager25State.hud#maxTtlMs")
        if maxTtl ~= nil then FarmManager25.MAX_TTL_MS = maxTtl end
        -- SETTINGS_ROWS 4/5/6: the three knobs loadSettings has always honoured
        -- but no GUI could reach. Now that a menu row can change them they need
        -- a LIVE store, exactly like uiScale above -- settings.xml stays the
        -- hand-edited seed, state.xml (read after it) wins, so a menu change
        -- survives a relog instead of being shadowed by the seed on next load.
        local widthPx = getXMLFloat(xml, "farmManager25State.hud#widthPx")
        if widthPx ~= nil then d.panelWidthPx = widthPx end
        local textPx = getXMLFloat(xml, "farmManager25State.hud#textSizePx")
        if textPx ~= nil then d.bodySizePx = textPx end
        local alpha = getXMLFloat(xml, "farmManager25State.hud#cardAlpha")
        if alpha ~= nil then d.cardAlpha = clamp(alpha, 0, 1) end
        -- SETTINGS_ROWS 8/9. Clamped/validated on the way in for the same reason
        -- loadSettings does it: state.xml is ours, but a corrupt one must not be
        -- able to put retentionCap above the bound loadCards reads back at --
        -- loadState runs BEFORE loadCards, so this value is already live there.
        local keep = getXMLFloat(xml, "farmManager25State.messages#retain")
        if keep ~= nil then
            FarmManager25.retentionCap =
                clamp(math.floor(keep), 0, FarmManager25.RETENTION_MAX)
        end
        local minSev = getXMLString(xml, "farmManager25State.messages#minSeverity")
        if minSev ~= nil and FarmManager25.severityRank(minSev) > 0 then
            FarmManager25.minSeverity = minSev
        end
        delete(xml)
    end)
    if not ok then
        print("FarmManager25: state.xml unreadable, using defaults -- " .. tostring(err))
    end
end

--- Load THIS SAVEGAME's un-dismissed cards. Split out of loadState so the card
--  stack is per-savegame while the HUD block stays machine-global (see
--  CARDS_NAME). `folder` is modSettings/<MOD>/<savegameKey>/ and is NEVER the
--  root: the caller does not call this at all when the key is nil.
--
--  S155 (LT-1/LT-8): EVERY un-dismissed card (info AND action) survives a relog
--  -- an unanswered question, and any card the player has not cleared. Counts
--  are written explicitly (#lineCount etc.) so an empty <line/> cannot silently
--  truncate the read (the pollBridge blank-line lesson, applied to our own file).
--  Wrapped like loadState: a corrupt file costs the stored cards, never the
--  notifier.
function FarmManager25:loadCards(folder)
    local path = folder .. FarmManager25.CARDS_NAME
    if not fileExists(path) then
        return
    end
    local ok, err = pcall(function()
        local xml = loadXMLFile("FarmManager25Cards", path)
        if xml == nil or xml == 0 then
            return
        end
        local count = getXMLFloat(xml, "farmManager25Cards#count") or 0
        -- ⛔ storeBound(), NOT MAX_STORE. Retention raised what saveCards writes;
        -- a read cap left at MAX_STORE would silently truncate the transcript on
        -- every restart -- a defect invisible until a reload. ONE function feeds
        -- both ends so the two can never disagree (TECH-DEBT-060).
        for i = 0, math.min(count, FarmManager25.storeBound()) - 1 do
            local key = string.format("farmManager25Cards.card(%d)", i)
            local lines = {}
            for j = 0, (getXMLFloat(xml, key .. "#lineCount") or 0) - 1 do
                table.insert(lines, getXMLString(xml, string.format("%s.line(%d)", key, j)) or "")
            end
            local actions = {}
            for k = 0, (getXMLFloat(xml, key .. "#actionCount") or 0) - 1 do
                local akey = string.format("%s.action(%d)", key, k)
                local action = { type = getXMLString(xml, akey .. "#type") or "" }
                local options = {}
                for m = 0, (getXMLFloat(xml, akey .. "#optionCount") or 0) - 1 do
                    local okey = string.format("%s.option(%d)", akey, m)
                    table.insert(options, {
                        value = getXMLString(xml, okey .. "#value"),
                        label = getXMLString(xml, okey .. "#label"),
                    })
                end
                if #options > 0 then
                    action.options = options
                end
                table.insert(actions, action)
            end
            -- Rebuilt through the ONE card constructor, so a persisted card
            -- obeys every rule a bridge card does (id trim, actions-need-id,
            -- ttl clamp). buildNotification re-stamps arrival; the ORIGINAL
            -- stamp -- when the farm manager actually said it -- wins.
            local n = FarmManager25.buildNotification(
                getXMLString(xml, key .. "#severity"),
                getXMLString(xml, key .. "#title"),
                nil, lines,
                getXMLString(xml, key .. "#icon"),
                getXMLString(xml, key .. "#id"),
                #actions > 0 and actions or nil)
            -- LT-8: restore EVERY persisted card (info AND action). The
            -- original stamp -- when the farm manager said it -- wins over the
            -- arrival re-stamp buildNotification applies; a card saved with a
            -- dead clock has no #stamp, so keep the constructor's value then.
            if n ~= nil then
                local savedStamp = getXMLString(xml, key .. "#stamp")
                if savedStamp ~= nil then
                    n.stamp = savedStamp
                end
                -- Same rule as #stamp: the day the card was FIRST said wins
                -- over the arrival re-stamp. Absent #day means the card was
                -- written with a dead clock, or by a build older than this
                -- field -- both restore as nil, which groups under EARLIER.
                local savedDay = getXMLFloat(xml, key .. "#day")
                if type(savedDay) == "number" then
                    n.day = math.floor(savedDay)
                else
                    n.day = nil
                end
                -- TECH-DEBT-060: a card carries the status it LEFT the stack
                -- with, and that status is what routes it on the way back in.
                -- No #status at all means the card was live when it was written
                -- -- which is also every card written by a pre-retention build,
                -- so an old cards.xml restores exactly as it always did. The
                -- transcript never reaches `stack`, so a restored log draws
                -- nothing: the live/retained separation survives the round trip,
                -- which is the half of the invariant a reload could break.
                local status = getXMLString(xml, key .. "#status")
                if status ~= nil and status ~= FarmManager25.STATUS_LIVE then
                    n.status = status
                    table.insert(self.retained, n)
                else
                    table.insert(self.stack, n)
                end
            end
        end
        -- The cap can be LOWERED between sessions (settings row 8), so a file
        -- written under a larger one is trimmed on the way IN, oldest first.
        -- Trimming here rather than at the read bound above keeps that bound a
        -- fixed structural constant no live setting can invalidate.
        while #self.retained > FarmManager25.retentionCap do
            table.remove(self.retained, 1)
        end
        delete(xml)
    end)
    if not ok then
        print("FarmManager25: cards.xml unreadable, starting with no cards -- " .. tostring(err))
    end
end

--- Write the client store -- the HUD block ONLY. Called on drag-end, on mode
--  toggle and on map exit. ContractBoost's modSettings write pattern:
--  createXMLFile + setters + saveXMLFile + delete. Wrapped: a failed save costs
--  persistence, nothing else.
--
--  Writes to the ROOT modSettings/<MOD>/state.xml on every savegame, including
--  the one with no savegame directory yet -- the panel position must not depend
--  on which farm you happen to be in. The CARDS are in saveCards().
function FarmManager25:saveState()
    if self.stateFolder == nil then
        return
    end
    local ok, err = pcall(function()
        local d = FarmManager25.DESIGN
        local xml = createXMLFile("FarmManager25State",
            self.stateFolder .. FarmManager25.STATE_NAME, "farmManager25State")
        setXMLFloat(xml, "farmManager25State.hud#anchorX", d.anchorX)
        setXMLFloat(xml, "farmManager25State.hud#anchorY", d.anchorY)
        setXMLString(xml, "farmManager25State.hud#overlayOn",
            FarmManager25.overlayOn and "true" or "false")
        setXMLFloat(xml, "farmManager25State.hud#textReplySeq",
            FarmManager25.textReplySeq)
        -- S158: the settings page's scale + OFF-mode linger are live-tunable, so
        -- the live store carries them (like anchorX/anchorY). settings.xml stays
        -- the hand-edited seed; state.xml (loaded after) wins, so a menu change
        -- survives a relog.
        setXMLFloat(xml, "farmManager25State.hud#uiScale", d.uiScale)
        setXMLFloat(xml, "farmManager25State.hud#minTtlMs", FarmManager25.MIN_TTL_MS)
        setXMLFloat(xml, "farmManager25State.hud#maxTtlMs", FarmManager25.MAX_TTL_MS)
        -- SETTINGS_ROWS 4/5/6/8/9. Every settings row round-trips through this
        -- file: a row the menu can change but the store does not carry would
        -- revert on the next load, which is a defect that only shows up after a
        -- restart -- the class this file already learned the hard way.
        setXMLFloat(xml, "farmManager25State.hud#widthPx", d.panelWidthPx)
        setXMLFloat(xml, "farmManager25State.hud#textSizePx", d.bodySizePx)
        setXMLFloat(xml, "farmManager25State.hud#cardAlpha", d.cardAlpha)
        setXMLFloat(xml, "farmManager25State.messages#retain",
            FarmManager25.retentionCap)
        setXMLString(xml, "farmManager25State.messages#minSeverity",
            FarmManager25.minSeverity)
        saveXMLFile(xml)
        delete(xml)
    end)
    if not ok then
        print("FarmManager25: could not save state.xml -- " .. tostring(err))
    end
end

--- Write THIS SAVEGAME's card stack to modSettings/<MOD>/<savegameKey>/cards.xml.
--  Called on map exit and (LT-8) on any stack change via update()'s coalesced
--  dirty-flush. Same write idiom and the same pcall discipline as saveState.
--
--  EVERY card in the live stack is written (LT-8, supersedes O5's action-only
--  rule) -- cards.xml mirrors the stack, so a dismissed/answered card is gone and
--  an un-dismissed info card survives a restart. Info cards carry no id/actions:
--  their minimal shape is severity/title/icon/stamp/lines.
--
--  ⛔ saveFolder nil (a never-saved new game, or a multiplayer client) means the
--  savegame has no directory to scope to. We SKIP the write; we do NOT fall back
--  to the root, because a shared card file is precisely the defect this split
--  exists to remove. loadMap says so on the status line so the skip is visible.
function FarmManager25:saveCards()
    if self.saveFolder == nil then
        return
    end
    local ok, err = pcall(function()
        local xml = createXMLFile("FarmManager25Cards",
            self.saveFolder .. FarmManager25.CARDS_NAME, "farmManager25Cards")
        -- Live cards FIRST, then the transcript. ONE document, because they are
        -- one savegame's history and a second file would be a second thing to
        -- keep in sync; `#status` is what tells them apart again in loadCards.
        -- Both tables are already bounded (MAX_STORE / retentionCap), so the
        -- total can never exceed the storeBound() loadCards reads back.
        local toWrite = {}
        for _, n in ipairs(self.stack) do
            toWrite[#toWrite + 1] = { card = n, status = FarmManager25.STATUS_LIVE }
        end
        for _, n in ipairs(self.retained) do
            toWrite[#toWrite + 1] = { card = n, status = n.status }
        end
        local i = 0
        for _, entry in ipairs(toWrite) do
            local n = entry.card
            -- The "no manager is set up for <save>" notice loadMap inserts is
            -- recomputed every load, never stored: a self-restoring card is the
            -- shape of the bug this file split exists to fix.
            if not n.ephemeral then
                local key = string.format("farmManager25Cards.card(%d)", i)
                setXMLString(xml, key .. "#status", entry.status)
                setXMLString(xml, key .. "#severity", n.severity)
                setXMLString(xml, key .. "#title", n.title)
                setXMLString(xml, key .. "#icon", n.icon)
                -- Info cards have no correlation id; write it only when present so
                -- a restored info card round-trips as id=nil (a valid passive card).
                if n.id ~= nil then
                    setXMLString(xml, key .. "#id", n.id)
                end
                if n.stamp ~= nil then
                    setXMLString(xml, key .. "#stamp", n.stamp)
                end
                -- Written only when known, exactly like #stamp above. A card
                -- saved with an unreadable day has no #day, and restores with
                -- day = nil -- which the MESSAGES tab groups under EARLIER
                -- rather than inventing one. Cards written by any build before
                -- this field existed behave identically, so an old cards.xml
                -- needs no migration.
                if n.day ~= nil then
                    setXMLFloat(xml, key .. "#day", n.day)
                end
                local lines = FarmManager25.splitLines(n.body)
                setXMLFloat(xml, key .. "#lineCount", #lines)
                for j, line in ipairs(lines) do
                    setXMLString(xml, string.format("%s.line(%d)", key, j - 1), line)
                end
                setXMLFloat(xml, key .. "#actionCount", n.actions ~= nil and #n.actions or 0)
                for k, action in ipairs(n.actions or {}) do
                    local akey = string.format("%s.action(%d)", key, k - 1)
                    setXMLString(xml, akey .. "#type", action.type)
                    local options = action.options or {}
                    setXMLFloat(xml, akey .. "#optionCount", #options)
                    for m, opt in ipairs(options) do
                        local okey = string.format("%s.option(%d)", akey, m - 1)
                        if opt.value ~= nil then
                            setXMLString(xml, okey .. "#value", opt.value)
                        end
                        if opt.label ~= nil then
                            setXMLString(xml, okey .. "#label", opt.label)
                        end
                    end
                end
                i = i + 1
            end
        end
        setXMLFloat(xml, "farmManager25Cards#count", i)
        saveXMLFile(xml)
        delete(xml)
    end)
    if not ok then
        print("FarmManager25: could not save cards.xml -- " .. tostring(err))
    end
end


--- Write the live contract rewards for THIS savegame. `rows` is an INPUT --
--  FarmManager25.contractRows produced it -- so this whole function is headless
--  and the engine stays on the other side of saveContracts below.
--
--  ⛔ THE GUARD IS THE SAME GUARD, AND IT IS DELIBERATE. saveFolder nil means a
--  never-saved new game or a multiplayer client: there is no savegame directory
--  to scope to, so we SKIP the write and do NOT fall back to the root. A shared
--  contracts.xml would report one farm's payouts as another's -- the BUG-027
--  class the card store was split to close.
--
--  Structure copied wholesale from saveCards (the guard, the pcall, the
--  indexed-key setters, saveXMLFile/delete, and the error print that contains a
--  failure instead of letting it reach the caller). A contracts write that threw
--  out of a GUI-path callback would cost far more than a missing reward.
function FarmManager25:writeContracts(rows)
    if self.saveFolder == nil then
        return false
    end
    local ok, err = pcall(function()
        local xml = createXMLFile("FarmManager25Contracts",
            self.saveFolder .. FarmManager25.CONTRACTS_NAME, "farmManager25Contracts")

        -- Provenance, both halves of it. The savegame key is what lets the
        -- reader REFUSE a file left behind by another save rather than merge it;
        -- the stamp is how a reader can say how old the figure is instead of
        -- implying it is current. getDate is wrapped exactly as writeReply
        -- wraps it -- a missing clock costs the stamp, never the document.
        local key = FarmManager25.savegameKey()
        if key ~= nil then
            setXMLString(xml, "farmManager25Contracts#savegame", key)
        end
        local okDate, stamp = pcall(function() return getDate("%Y-%m-%d %H:%M:%S") end)
        if okDate and stamp ~= nil then
            setXMLString(xml, "farmManager25Contracts#generatedAt", stamp)
        end

        local i = 0
        for _, row in ipairs(rows or {}) do
            if row.id ~= nil and row.reward ~= nil then
                local k = string.format("farmManager25Contracts.contract(%d)", i)
                setXMLString(xml, k .. "#uniqueId", row.id)
                setXMLFloat(xml, k .. "#reward", row.reward)
                i = i + 1
            end
        end
        setXMLFloat(xml, "farmManager25Contracts#count", i)
        saveXMLFile(xml)
        delete(xml)
    end)
    if not ok then
        print("FarmManager25: could not save contracts.xml -- " .. tostring(err))
        return false
    end
    return true
end


--- THE ENGINE SEAM for the contract rewards, and the only part of item 5a a
--  headless test cannot honestly gate.
--
--  ⛔ NOT STUBBED ANYWHERE. Acquiring the mission list is an engine call, so
--  whether the figure it yields is the figure the player sees in the contract
--  screen is settled by the owner's live test and by nothing in the suite. The
--  two halves that CAN be gated -- the reduction (contractRows) and the write
--  (writeContracts) -- are, and they are on the other side of this boundary.
--
--  ⚠ NOTHING IS WRITTEN WHEN THE ENGINE COULD NOT BE ASKED. `rows` stays nil on
--  a missing global, a missing method or a throw, and a nil rows means no file
--  -- never an empty document carrying a fresh timestamp, which would read as
--  "asked, and there were none".
function FarmManager25:saveContracts()
    if self.saveFolder == nil then
        return false
    end

    local rows = nil
    local ok = pcall(function()
        local farmId = nil
        if g_currentMission ~= nil and g_currentMission.getFarmId ~= nil then
            farmId = g_currentMission:getFarmId()
        end
        if farmId == nil or farmId == 0
                or g_missionManager == nil
                or g_missionManager.getMissionsByFarmId == nil then
            return
        end

        local missions = g_missionManager:getMissionsByFarmId(farmId)
        if type(missions) ~= "table" then
            return
        end
        rows = FarmManager25.contractRows(missions)
    end)

    if not ok then
        print("FarmManager25: a live contracts lookup failed -- no reward is "
            .. "published this session, and the skill reports them as unknown")
        return false
    end
    if rows == nil then
        return false
    end
    return self:writeContracts(rows)
end

--- Append one reply to replies.xml. Returns true when the reply is recorded
--  (or was already recorded -- idempotent by (id, action)); false when the
--  write failed, so the caller keeps the card and the player can retry. A
--  reply that silently vanished would be the reverse of the "sends into a
--  void" failure the notifier exists to prevent.
--
--  Append = read-modify-rewrite, because FS25's io sandbox is write-only:
--  read back via XMLFile.load (the pollBridge idiom), rewrite via
--  createXMLFile + setters + saveXMLFile (the saveState idiom; indexed
--  "path(i)" setter precedent: AutoDrive RoutesManager.lua:220). The skill
--  only ever truncates-after-read, we only ever append -- a lost race
--  re-reads a reply, and the (id, action) dedup keeps it from double-counting.
function FarmManager25:writeReply(id, action, lines)
    -- saveFolder, not stateFolder: a reply belongs to ONE savegame. An unscoped
    -- replies.xml was already leaking -- two un-ingested acks for one farm sat in
    -- the root file waiting to be claimed as whichever farm ran the skill next.
    if self.saveFolder == nil then
        return false
    end
    local path = self.saveFolder .. FarmManager25.REPLIES_NAME
    local ok, err = pcall(function()
        local entries = {}
        if fileExists(path) then
            -- An unparseable replies.xml loads as nil: entries stay empty and
            -- the rewrite below REPLACES the corrupt file -- a wedged reply
            -- log must not swallow every future reply.
            local xml = XMLFile.load("FarmManager25Replies", path)
            if xml ~= nil then
                -- finally-equivalent: the handle is freed whether the read
                -- body returns or throws, THEN the throw is re-raised for the
                -- outer pcall. A throw between load and delete must never
                -- leak the engine handle (the F-P1-3 class).
                local okRead, errRead = pcall(function()
                    for i = 0, FarmManager25.MAX_REPLIES - 1 do
                        local key = string.format("farmManager25Replies.reply(%d)", i)
                        if not xml:hasProperty(key) then
                            break
                        end
                        local e = {
                            id       = xml:getString(key .. "#id"),
                            action   = xml:getString(key .. "#action"),
                            gameTime = xml:getString(key .. "#gameTime"),
                            realTime = xml:getString(key .. "#realTime"),
                            lines    = {},
                        }
                        -- Text replies carry <line> children (protocol 4); a
                        -- rewrite that dropped them would corrupt a reply we
                        -- did not write. Preserve, bounded like the bridge
                        -- reader.
                        for j = 0, FarmManager25.MAX_BODY_LINES - 1 do
                            local lk = string.format("%s.line(%d)", key, j)
                            if not xml:hasProperty(lk) then
                                break
                            end
                            table.insert(e.lines, xml:getString(lk) or "")
                        end
                        table.insert(entries, e)
                    end
                end)
                -- The delete is guarded too: on a double fault (body threw
                -- AND delete threw) the ORIGINAL error must surface, not the
                -- delete-time one. Level 0 on the re-raise: the message
                -- already carries its file:line -- a second prepend would
                -- muddy the exact diagnostic this shape exists to protect.
                local okDel = pcall(function() xml:delete() end)
                if not okRead then
                    error(errRead, 0)
                elseif not okDel then
                    error("replies.xml read handle delete failed", 0)
                end
            end
        end

        -- THE IDEMPOTENCY CONTRACT: (id, action) is the key. A double-click
        -- is not two answers, and distinct live card instances sharing an id
        -- are the same logical notification -- their same-action answers
        -- collapse to ONE recorded reply (each card is still dismissed as
        -- answered by its own click). A sender that emits duplicate live ids
        -- is contract-violating; the id is the correlation key and must be
        -- unique per logical card.
        for _, e in ipairs(entries) do
            if e.id == id and e.action == action then
                return   -- already recorded
            end
        end

        while #entries >= FarmManager25.MAX_REPLIES do
            table.remove(entries, 1)
            print("FarmManager25: replies.xml full, dropped the oldest reply -- has the skill stopped ingesting?")
        end

        -- Real-wall-clock stamp for ordering context. getDate is the engine's
        -- verified surface (AutoDrive RoutesManager.lua:131); a clock failure
        -- must not cost the reply, so it is probed, never trusted.
        local realTime = nil
        local okDate, stamp = pcall(function() return getDate("%Y-%m-%d %H:%M:%S") end)
        if okDate and type(stamp) == "string" then
            realTime = stamp
        end
        table.insert(entries, {
            id       = id,
            action   = action,
            gameTime = FarmManager25.gameClock(),
            realTime = realTime,
            -- Free-text replies (LT-4) carry their text as <line> children --
            -- the shape the read-preserve loop above and the skill's reader
            -- already round-trip. Affordance replies pass nothing.
            lines    = lines or {},
        })

        local xml = createXMLFile("FarmManager25Replies", path, "farmManager25Replies")
        -- Same finally-equivalent on the write side: a setter/save throw is
        -- caught, the handle freed, the error re-raised -- the outer pcall
        -- still keeps the card, and no handle leaks.
        local okWrite, errWrite = pcall(function()
            for i, e in ipairs(entries) do
                local key = string.format("farmManager25Replies.reply(%d)", i - 1)
                setXMLString(xml, key .. "#id", e.id or "")
                setXMLString(xml, key .. "#action", e.action or "")
                if e.gameTime ~= nil then
                    setXMLString(xml, key .. "#gameTime", e.gameTime)
                end
                if e.realTime ~= nil then
                    setXMLString(xml, key .. "#realTime", e.realTime)
                end
                for j, line in ipairs(e.lines) do
                    setXMLString(xml, string.format("%s.line(%d)", key, j - 1), line)
                end
            end
            saveXMLFile(xml)
        end)
        -- Same double-fault discipline as the read side: original error
        -- first, delete failure second, no re-prepended location.
        local okDel = pcall(function() delete(xml) end)
        if not okWrite then
            error(errWrite, 0)
        elseif not okDel then
            error("replies.xml write handle delete failed", 0)
        end
    end)
    if not ok then
        print("FarmManager25: could not write replies.xml -- the reply was NOT recorded, the card stays -- " .. tostring(err))
        return false
    end
    return true
end

--- Is the ENGINE's shared mouse cursor on screen? Click-gating only ever
--  READS the state every mod shares (g_inputBinding:getShowMouseCursor();
--  the gate AutoDrive uses at AutoDrive.lua:596-601 and Courseplay consumes
--  vehicle-wide). Whoever raised the cursor -- AutoDrive MMB, Courseplay
--  RMB, any cursor mod, or this mod's own Ctrl+Comma cursor toggle
--  (FM25_TOGGLE_CURSOR, below) -- owns hiding it.
function FarmManager25:cursorIsShown()
    return g_inputBinding ~= nil and g_inputBinding:getShowMouseCursor()
end

--- The overlay mode toggle (FM25_TOGGLE_OVERLAY, default Ctrl+Period):
--  flip the panel between persistent (ON, the default) and transient (OFF).
--  This toggle never writes the engine cursor (only FM25_TOGGLE_CURSOR does)
--  -- whoever raises it (AutoDrive's MMB, Courseplay's RMB, that key, any
--  cursor mod) owns it; click-gating reads cursorIsShown() like every other
--  consumer. Guarded while a real menu owns
--  the screen (a keypress under a menu is the menu's, not ours). Switching
--  to OFF re-arms every live card with a fresh read window: their ages
--  predate the mode and would otherwise expire them on the spot. The new
--  mode is persisted immediately -- a toggle that forgot itself on relog
--  would read as the S153 one-shot bug all over again.
--- Set the overlay mode and persist it. The single flip shared by the
--  keybind (onToggleOverlay) and the settings page (the dialog's
--  onOverlayChanged calls this directly), so the OFF-mode re-arm + saveState
--  happen identically however the mode is changed. Deliberately WITHOUT the
--  gui-visible guard: the settings dialog IS a visible GUI, so onToggleOverlay's
--  guard would wrongly no-op the in-dialog toggle. The guard stays on the
--  keybind path where it belongs.
function FarmManager25:setOverlayOn(on)
    FarmManager25.overlayOn = on
    if not FarmManager25.overlayOn then
        for _, n in ipairs(self.stack) do
            n.ttl = n.age + FarmManager25.MIN_TTL_MS
        end
    end
    self:saveState()
end

function FarmManager25:onToggleOverlay()
    local ok, err = pcall(function()
        if g_gui ~= nil and g_gui:getIsGuiVisible() then
            return
        end
        self:setOverlayOn(not FarmManager25.overlayOn)
    end)
    if not ok then
        print("FarmManager25: overlay toggle failed -- " .. tostring(err))
    end
end

--- The standalone cursor toggle (FM25_TOGGLE_CURSOR, default Ctrl+Comma):
--  raise/lower the ENGINE's shared mouse cursor so the overlay is reachable
--  ON FOOT. The S155 design assumed AutoDrive's MMB / Courseplay's RMB would
--  always be on hand to raise the cursor; the owner's on-foot playtest
--  disproved it -- both are VEHICLE-context bindings, so out of a vehicle the
--  cursor could not come up at all and the overlay was dead. This is the ONE
--  place the mod WRITES the shared cursor; every gate elsewhere still only
--  READS it (cursorIsShown), so read-only consumers are unaffected.
--
--  Toggles off the SAME shared state every consumer reads, so it cooperates
--  instead of fighting: whoever last set the cursor (AD, CP, any cursor mod,
--  or this key), one press reads the live state and flips it. Works
--  identically in a vehicle. Unlike the click-driven open/close the BP-064
--  next-tick defer was written for, this action is KEY-triggered -- there is
--  no closing click for setShowMouseCursor(false) to eat, so it applies
--  inline with no defer. Guarded while a real menu owns the screen (that
--  keypress is the menu's, exactly like onToggleOverlay) and nil-tolerant on
--  g_inputBinding (absent input surface => no-op, never a raise on nothing).
function FarmManager25:onToggleCursor()
    local ok, err = pcall(function()
        if g_inputBinding == nil then
            return
        end
        if g_gui ~= nil and g_gui:getIsGuiVisible() then
            return
        end
        local show = not g_inputBinding:getShowMouseCursor()
        g_inputBinding:setShowMouseCursor(show)
    end)
    if not ok then
        print("FarmManager25: cursor toggle failed -- " .. tostring(err))
    end
end

-- ---------------------------------------------------------------------------
-- settings page: the apply logic lives here as plain methods on FarmManager25
-- so it is lupa-testable, and SETTINGS_ROWS below publishes them as ordered data.
-- The consumer is now the in-game menu page (gui/InGameMenuFarmManager25.lua);
-- the S158 DialogElement controller that used to call these was retired in
-- Stage 1 along with its modal.
-- ---------------------------------------------------------------------------

-- Index of the preset nearest to `current` (ties -> first). Backs the settings
-- dialog's index-addressable steppers (getScaleIndex/getLingerIndex): "nearest"
-- so a value that drifted off the preset grid (a hand-edited settings.xml scale,
-- say) still resolves to a sensible index instead of snapping to preset 1.
local function nearestIndex(list, current)
    local bestI, bestD = 1, math.huge
    for i, v in ipairs(list) do
        local d = math.abs(v - (current or v))
        if d < bestD then
            bestI, bestD = i, d
        end
    end
    return bestI
end

-- Wrap a 1-based index into [1, #list] in BOTH directions (0 -> last,
-- #list+1 -> first). Lua's floored % keeps negatives positive, so this also
-- absorbs any out-of-range index a stepper could hand us.
local function wrapIndex(i, n)
    return ((i - 1) % n) + 1
end

-- The settings dialog's native ‹value› steppers apply by an explicit 1-based
-- state index (bidirectional). getScaleIndex/getLingerIndex give the dialog the
-- current state to setState() on open; cfgSetScaleIndex/cfgSetLingerIndex apply
-- + persist the chosen index. Index wraps both ways so a stepper can never
-- drive an out-of-range value. (The overlay stepper flips via setOverlayOn.)

--- Current SCALE_PRESETS index for the live uiScale (nearest, for setState).
function FarmManager25:getScaleIndex()
    return nearestIndex(FarmManager25.SCALE_PRESETS, FarmManager25.DESIGN.uiScale)
end

--- Current LINGER_PRESETS_MS index for the live MIN_TTL_MS (nearest).
function FarmManager25:getLingerIndex()
    return nearestIndex(FarmManager25.LINGER_PRESETS_MS, FarmManager25.MIN_TTL_MS)
end

--- Apply SCALE_PRESETS[i], then rebuild geometry (uiScale is precomputed in
--  buildOverlays, the same call loadMap makes) and persist.
function FarmManager25:cfgSetScaleIndex(i)
    local list = FarmManager25.SCALE_PRESETS
    FarmManager25.DESIGN.uiScale = list[wrapIndex(i, #list)]
    self:buildOverlays()
    self:saveState()
end

--- Apply LINGER_PRESETS_MS[i], keeping MAX_TTL_MS >= MIN so the
--  buildNotification clamp can never invert, and persist.
function FarmManager25:cfgSetLingerIndex(i)
    local list = FarmManager25.LINGER_PRESETS_MS
    FarmManager25.MIN_TTL_MS = list[wrapIndex(i, #list)]
    if FarmManager25.MAX_TTL_MS < FarmManager25.MIN_TTL_MS then
        FarmManager25.MAX_TTL_MS = FarmManager25.MIN_TTL_MS
    end
    self:saveState()
end

--- Reset the overlay to its factory anchor (top-right). Uses the DEFAULT_*
--  constants, not the live DESIGN values, which may have been dragged/loaded
--  away. panelLeft/panelTop are recomputed only once buildOverlays has run
--  (panelW known) -- before that, loadMap's build applies the anchor anyway.
function FarmManager25:cfgResetPosition()
    local d = FarmManager25.DESIGN
    d.anchorX = FarmManager25.DEFAULT_ANCHOR_X
    d.anchorY = FarmManager25.DEFAULT_ANCHOR_Y
    if self.panelW ~= nil then
        self.panelLeft = d.anchorX - self.panelW
        self.panelTop  = d.anchorY
    end
    self:saveState()
end

--- Build a stepper's choice labels as L10N KEYS, one per preset.
--
--  ⛔ EVERY entry is a key -- never a display string, not even a bare numeral.
--  An untranslated "ON"/"OFF" or a "60" that should read "60 s" in one language
--  and "60 с" in another is the SAME defect as an untranslated row title, only
--  smaller and easier to miss. "core hardcodes no user-visible text" has to
--  cover choice labels or the invariant does not hold at all.
--
--  The key is DERIVED from the preset value (`prefix .. the number`), so the
--  list and its keys cannot drift: add a preset and its key appears, with the
--  translation files as the single place that then needs updating. `mul`
--  converts the stored unit into the one the key is named for (ms -> s,
--  0..1 -> percent), so the key reads as the player-facing quantity.
local function stepKeys(prefix, list, mul)
    local out = {}
    for i, v in ipairs(list) do
        out[i] = prefix .. string.format("%d", math.floor(v * (mul or 1) + 0.5))
    end
    return out
end

--- Severity stepper labels, DERIVED from SEVERITY_ORDER so the two can never
--  fall out of step. Keys, not text -- the page resolves them.
local function severityTexts()
    local out = {}
    for i, key in ipairs(FarmManager25.SEVERITY_ORDER) do
        out[i] = "fm25_severity_" .. key
    end
    return out
end

--- Current index helpers for the knobs added here (the nearestIndex idiom the
--  scale/linger steppers already use, so a hand-edited value that is not exactly
--  a preset still opens the stepper somewhere sensible instead of at step 1).
function FarmManager25:getWidthIndex()
    return nearestIndex(FarmManager25.WIDTH_PRESETS_PX, FarmManager25.DESIGN.panelWidthPx)
end

function FarmManager25:getTextSizeIndex()
    return nearestIndex(FarmManager25.TEXTSIZE_PRESETS_PX, FarmManager25.DESIGN.bodySizePx)
end

function FarmManager25:getAlphaIndex()
    return nearestIndex(FarmManager25.ALPHA_PRESETS, FarmManager25.DESIGN.cardAlpha)
end

function FarmManager25:getMaxTtlIndex()
    return nearestIndex(FarmManager25.MAXTTL_PRESETS_MS, FarmManager25.MAX_TTL_MS)
end

function FarmManager25:getRetentionIndex()
    return nearestIndex(FarmManager25.RETENTION_PRESETS, FarmManager25.retentionCap)
end

--- The severity floor is an ORDERED enum, not a numeric preset, so its index IS
--  its rank. An unknown stored value ranks 0; clamp to 1 ("show everything")
--  rather than hand the stepper an out-of-range state.
function FarmManager25:getMinSeverityIndex()
    return math.max(1, FarmManager25.severityRank(FarmManager25.minSeverity))
end

--- Panel width and body text size are PRECOMPUTED in buildOverlays (the single
--  px->normalized chokepoint), so changing either has no effect until geometry
--  is rebuilt -- the same call cfgSetScaleIndex makes for exactly this reason.
function FarmManager25:cfgSetWidthIndex(i)
    local list = FarmManager25.WIDTH_PRESETS_PX
    FarmManager25.DESIGN.panelWidthPx = list[wrapIndex(i, #list)]
    self:buildOverlays()
    self:saveState()
end

function FarmManager25:cfgSetTextSizeIndex(i)
    local list = FarmManager25.TEXTSIZE_PRESETS_PX
    FarmManager25.DESIGN.bodySizePx = list[wrapIndex(i, #list)]
    self:buildOverlays()
    self:saveState()
end

--- cardAlpha is multiplied in at DRAW time, not precomputed, so this one needs
--  no geometry rebuild. ⚠ This is the knob whose settings.xml path once wrote to
--  a `bgColor` key DESIGN never had (F-T101-1) -- indexing the nil threw inside
--  loadSettings' pcall, so ANY settings.xml that set bgAlpha silently aborted the
--  WHOLE settings load. Exposing it as a row retires the hand-edit that caused it.
function FarmManager25:cfgSetAlphaIndex(i)
    local list = FarmManager25.ALPHA_PRESETS
    FarmManager25.DESIGN.cardAlpha = list[wrapIndex(i, #list)]
    self:saveState()
end

--- The OFF-mode ceiling. Kept >= MIN_TTL_MS so buildNotification's clamp can
--  never invert -- the mirror of cfgSetLingerIndex's guard on the floor.
--  ⛔ timing#msPerChar is deliberately NOT a row: min and max already bound the
--  duration meaningfully and a third interacting knob only confuses.
function FarmManager25:cfgSetMaxTtlIndex(i)
    local list = FarmManager25.MAXTTL_PRESETS_MS
    FarmManager25.MAX_TTL_MS = list[wrapIndex(i, #list)]
    if FarmManager25.MAX_TTL_MS < FarmManager25.MIN_TTL_MS then
        FarmManager25.MAX_TTL_MS = FarmManager25.MIN_TTL_MS
    end
    self:saveState()
end

--- The transcript cap. Lowering it must take effect NOW, not at the next
--  eviction: a player who cuts 200 to 25 has asked for the history to be that
--  short. Trimmed oldest-first, then BOTH files are written -- state.xml carries
--  the setting, cards.xml carries the transcript the setting just resized, and
--  leaving the second unwritten would restore the trimmed cards on the next load.
function FarmManager25:cfgSetRetentionIndex(i)
    local list = FarmManager25.RETENTION_PRESETS
    FarmManager25.retentionCap = list[wrapIndex(i, #list)]
    while #self.retained > FarmManager25.retentionCap do
        table.remove(self.retained, 1)
    end
    self:saveState()
    self:saveCards()
end

--- The HUD severity floor. ⛔ RENDER ONLY -- nothing is deleted and nothing is
--  hidden from getMessageLog. A card below the floor still arrives, still
--  persists, still ages and still retains; alphaOf simply draws it at 0.
function FarmManager25:cfgSetMinSeverityIndex(i)
    local list = FarmManager25.SEVERITY_ORDER
    FarmManager25.minSeverity = list[wrapIndex(i, #list)]
    self:saveState()
end

--- ⛔ THE SETTINGS SEAM. Ten ordered rows, consumed by the in-game menu page.
--  Shape: { key, kind = "stepper"|"action", l10nName, texts, getIndex, setIndex,
--  invoke }. A stepper carries texts/getIndex/setIndex; an action carries invoke.
--
--  ⛔ NO USER-VISIBLE TEXT LIVES HERE, AND THERE IS NO EXCEPTION TO CHECK FOR.
--  `l10nName` is an l10n key and EVERY entry of `texts` is an l10n key. The
--  consumer resolves both the same way, unconditionally -- there is no "is this
--  one already a display value?" branch, because a rule with an exception in it
--  is a rule someone gets wrong. An earlier draft let numeric rows carry bare
--  numerals; that made an untranslatable "60" indistinguishable from a
--  translatable one, so it was retired.
--
--  Rows 1-3 and 10 are the three preferences and the Reset action the old modal
--  dialog carried. Rows 4-7 are the knobs loadSettings ALREADY honours that no
--  GUI has ever exposed -- zero new behaviour, only reachability. Rows 8-9 are
--  what retention requires.
--
--  Every row round-trips: each setIndex/invoke ends in saveState (and saveCards
--  where it changed the transcript), and loadState reads every one of them back.
--- ⛔ `helpKey` IS A KEY, NOT PROSE. chosen.html SETTINGS asks for "a help
--  text for each of the 10 settings"; the detail pane resolves this key and
--  renders BLANK when a row has none. ⛔ It must never fall back to restating
--  the title: a restated title reads as an explanation and teaches nothing,
--  which is worse than an honest empty line.
FarmManager25.SETTINGS_ROWS = {
    { key = "overlay", kind = "stepper", l10nName = "fm25_setting_overlay", helpKey = "fm25_help_overlay",
      texts = {"fm25_toggle_off", "fm25_toggle_on"},
      getIndex = function(self) return FarmManager25.overlayOn and 2 or 1 end,
      setIndex = function(self, i) self:setOverlayOn(wrapIndex(i, 2) == 2) end },

    { key = "scale", kind = "stepper", l10nName = "fm25_setting_scale", helpKey = "fm25_help_scale",
      texts = stepKeys("fm25_scale_", FarmManager25.SCALE_PRESETS, 100),
      getIndex = function(self) return self:getScaleIndex() end,
      setIndex = function(self, i) self:cfgSetScaleIndex(i) end },

    { key = "width", kind = "stepper", l10nName = "fm25_setting_width", helpKey = "fm25_help_width",
      texts = stepKeys("fm25_width_", FarmManager25.WIDTH_PRESETS_PX),
      getIndex = function(self) return self:getWidthIndex() end,
      setIndex = function(self, i) self:cfgSetWidthIndex(i) end },

    { key = "textSize", kind = "stepper", l10nName = "fm25_setting_text_size", helpKey = "fm25_help_text_size",
      texts = stepKeys("fm25_text_size_", FarmManager25.TEXTSIZE_PRESETS_PX),
      getIndex = function(self) return self:getTextSizeIndex() end,
      setIndex = function(self, i) self:cfgSetTextSizeIndex(i) end },

    { key = "cardAlpha", kind = "stepper", l10nName = "fm25_setting_card_alpha", helpKey = "fm25_help_card_alpha",
      texts = stepKeys("fm25_card_alpha_", FarmManager25.ALPHA_PRESETS, 100),
      getIndex = function(self) return self:getAlphaIndex() end,
      setIndex = function(self, i) self:cfgSetAlphaIndex(i) end },

    { key = "linger", kind = "stepper", l10nName = "fm25_setting_linger", helpKey = "fm25_help_linger",
      texts = stepKeys("fm25_linger_", FarmManager25.LINGER_PRESETS_MS, 0.001),
      getIndex = function(self) return self:getLingerIndex() end,
      setIndex = function(self, i) self:cfgSetLingerIndex(i) end },

    { key = "maxTtl", kind = "stepper", l10nName = "fm25_setting_max_ttl", helpKey = "fm25_help_max_ttl",
      texts = stepKeys("fm25_max_ttl_", FarmManager25.MAXTTL_PRESETS_MS, 0.001),
      getIndex = function(self) return self:getMaxTtlIndex() end,
      setIndex = function(self, i) self:cfgSetMaxTtlIndex(i) end },

    { key = "retention", kind = "stepper", l10nName = "fm25_setting_retention", helpKey = "fm25_help_retention",
      texts = stepKeys("fm25_retention_", FarmManager25.RETENTION_PRESETS),
      getIndex = function(self) return self:getRetentionIndex() end,
      setIndex = function(self, i) self:cfgSetRetentionIndex(i) end },

    { key = "minSeverity", kind = "stepper", l10nName = "fm25_setting_min_severity", helpKey = "fm25_help_min_severity",
      texts = severityTexts(),
      getIndex = function(self) return self:getMinSeverityIndex() end,
      setIndex = function(self, i) self:cfgSetMinSeverityIndex(i) end },

    { key = "resetPosition", kind = "action", l10nName = "fm25_setting_reset_position", helpKey = "fm25_help_reset_position",
      invoke = function(self) self:cfgResetPosition() end },
}

--- ⛔ THE MESSAGE LOG SEAM. Newest-first array of plain tables:
--    { whenText, day, fromText, messageText, statusText, severity, answered }
--
--  ⛔ PLAIN DATA, ZERO ENGINE CALLS -- no g_i18n, no g_currentMission, no clock
--  read. Safe to call from a page's onOpen at any time, including before loadMap
--  has run. That is the contract, not an implementation detail: the consuming
--  page is being built against it in parallel.
--
--  ⛔ `statusText` IS AN L10N KEY (the STATUS_* constants), not text -- the page
--  resolves it. The rest is SENDER data and passes through raw: the card's own
--  stamp, title and body, and the severity KEY. `whenText` is "" when the card
--  was stamped with a dead clock -- an empty field the page can style, never a
--  hardcoded English fallback sentence.
--  ⛔ AND "THE PAGE CAN STYLE IT" IS AN OBLIGATION, NOT A PERMISSION. An empty
--  whenText MUST render as the flagged unknown word, never as a blank cell: a
--  blank reads as midnight, or as a column that failed to draw. The page shipped
--  the blank until 2026-09-12; chosen.html:640 rules it and DEC-001 requires it.
--  Regression test: tests/test_message_groups_seam.py.
--  `day` follows the same rule in a different shape: nil, never 0.
--
--  LIVE CARDS ARE INCLUDED, tagged STATUS_LIVE: a log that omitted what is on
--  screen would make the newest exchange the one you cannot read back.
--  ⛔ NOTHING IS FILTERED BY minSeverity -- that is a HUD floor. A transcript
--  that hid messages would rebuild the hole retention exists to fill.
--
--  ORDER, stated honestly: the live stack newest-first, THEN the transcript
--  newest-first. It is NOT a strict global recency sort, and cannot be -- an
--  action card never expires in OFF mode, so a newer info card can reach the
--  transcript while an older question is still on screen. Live-then-history is
--  the ordering; `stamp` is the field to sort on if a page wants otherwise.
function FarmManager25:getMessageLog()
    local log = {}
    local function add(n, status)
        log[#log + 1] = {
            whenText    = n.stamp or "",
            -- The DAY the card was said, or nil when it was never readable.
            -- ⛔ NIL IS PUBLISHED AS NIL, never as 0 and never as "today": the
            -- page has to be able to tell "I know the day" from "I cannot tell",
            -- and a zero would be indistinguishable from a real day 0.
            day         = n.day,
            fromText    = n.title or "",
            messageText = n.body or "",
            statusText  = status,
            severity    = n.severity,
            -- Derived here, from the status, and NOWHERE else -- see retain().
            answered    = (status == FarmManager25.STATUS_ANSWERED),
        }
    end
    for i = #self.stack, 1, -1 do
        add(self.stack[i], FarmManager25.STATUS_LIVE)
    end
    for i = #self.retained, 1, -1 do
        add(self.retained[i], self.retained[i].status)
    end
    return log
end

-- ---------------------------------------------------------------------------
-- THE FARM TABLE -- the FOURTH published seam (plan item 11).
--
-- Shape follows getMessageLog() above, deliberately: a METHOD that rebuilds its
-- ordered array on every call, NOT a static table like SETTINGS_ROWS. That is
-- not a style choice. Group A is LIVE money; a table built once at loadMap
-- would freeze it and then label the stale figure "Live", which is exactly the
-- guard-7 failure two frictions already caught (F-117, F-410).
--
-- ⛔ THE MENU MAKES NO ENGINE CALL FOR THIS. It calls getFarmRows() and renders
-- what it gets (DEC-128 ②). Every engine read lives below, in core, where a
-- failed lookup is CAUGHT and published as `unknown` rather than thrown from a
-- GUI callback -- the position that produced the 57% load freeze.
--
-- ⛔ SPLIT ON PURPOSE: ASSEMBLY vs ACQUISITION.
--   buildFarmRows()  -- PURE. Zero engine references. Takes a values table and
--                       produces the ordered rows, applying guards 7 and 8.
--                       This is what the headless lupa test drives, with no
--                       g_* stub anywhere, and it is where a mutated ANSWER
--                       must turn the suite red.
--   readLiveValues() -- the engine boundary. Thin, total, guarded. Doctrine
--                       says never stub the boundary under test, so this half
--                       is gated by the OWNER'S LIVE TEST and by nothing else.
-- Decision ②'s testability argument survives that split; stubbing g_* to fake
-- a headless pass over the engine half would have destroyed it.
-- ---------------------------------------------------------------------------

--- Every FARM line, in render order. DATA, not code: `live` decides whether a
--  row is read from the engine now or from farm.xml as-of the last skill run,
--  so moving a whole group between transports is an edit to this table.
--  Ids match the RESEARCH doc's A1..E4 so a row traces to its citation.
--
--  ⭐ TRANSPORT IS PER-GROUP, AND IT FOLLOWS THE EVIDENCE -- ruled 2026-09-02.
--  A (money) and D (contracts) are LIVE; B, C and E cross in farm.xml.
--  D is live because D is live-only: `read_missions.py` records that a
--  field-tied contract's reward is "UNKNOWN, not zero -- computed by the game
--  at accept-time and not written to the save while the contract is only
--  offered" (FRICTION-LOG F-025, a defect we shipped once: reporting "$0"
--  would talk the player out of the only work their fleet can do). There is no
--  deadline field in the save either. Routing D through the file would have
--  discarded the very real-body engine evidence that made it the strongest
--  group and shipped it reading half `unknown`.
FarmManager25.FARM_ROW_SPEC = {
    { id = "a1", group = "a_money",       labelKey = "fm25_farm_a1_balance",     kind = "money", live = true  },
    { id = "a2", group = "a_money",       labelKey = "fm25_farm_a2_loan",        kind = "money", live = true  },
    { id = "a3", group = "a_money",       labelKey = "fm25_farm_a3_equity",      kind = "money", live = true  },
    { id = "a4", group = "a_money",       labelKey = "fm25_farm_a4_interest",    kind = "money", live = true  },

    { id = "b1", group = "b_land",        labelKey = "fm25_farm_b1_parcels",     kind = "count", live = false },
    { id = "b2", group = "b_land",        labelKey = "fm25_farm_b2_area",        kind = "area",  live = false },
    { id = "b3", group = "b_land",        labelKey = "fm25_farm_b3_value",       kind = "money", live = false },

    { id = "c1", group = "c_productions", labelKey = "fm25_farm_c1_points",      kind = "count", live = false },
    -- F7 (BUG-030 FARM): `refusal` is this row's STATIC refusal kind -- the key into the
    -- menu's REFUSAL_TAG_KEYS. The producer's reason PROSE is never rendered; the row
    -- publishes only WHICH kind of refusal explains its `unknown`, and only when the
    -- document carried an <unknown> element for it. c2/c3 need a capacity the emitter
    -- deliberately does not fetch; e4 needs a tank capacity the store-XML pass may not
    -- resolve. Every one of them is a refused CAPACITY. Zero new strings ([[DEC-211]]).
    { id = "c2", group = "c_productions", labelKey = "fm25_farm_c2_fill",        kind = "pct",   live = false, refusal = "capacity" },
    { id = "c3", group = "c_productions", labelKey = "fm25_farm_c3_atcap",       kind = "count", live = false, refusal = "capacity" },

    { id = "d1", group = "d_contracts",   labelKey = "fm25_farm_d1_active",      kind = "count", live = true  },
    { id = "d2", group = "d_contracts",   labelKey = "fm25_farm_d2_reward",      kind = "money", live = true  },
    { id = "d3", group = "d_contracts",   labelKey = "fm25_farm_d3_deadline",    kind = "mins",  live = true  },
    { id = "d4", group = "d_contracts",   labelKey = "fm25_farm_d4_completion",  kind = "pct",   live = true  },

    -- D-3 ([[DEC-222]]): "Vehicles owned" counted every pallet as a vehicle. THREE
    -- rows, ONE value each (GUARD 9), in the order the owner named them. e1 keeps its id
    -- and is now MACHINES; e5/e6 are new ids, placed here so the detail list reads
    -- Machines, Pallets, Bales.
    { id = "e1", group = "e_fleet",       labelKey = "fm25_farm_e1_vehicles",    kind = "count", live = false },
    { id = "e5", group = "e_fleet",       labelKey = "fm25_farm_e5_pallets",     kind = "count", live = false },
    { id = "e6", group = "e_fleet",       labelKey = "fm25_farm_e6_bales",       kind = "count", live = false },
    { id = "e2", group = "e_fleet",       labelKey = "fm25_farm_e2_repair",      kind = "count", live = false },
    { id = "e3", group = "e_fleet",       labelKey = "fm25_farm_e3_hours",       kind = "hours", live = false },
    { id = "e4", group = "e_fleet",       labelKey = "fm25_farm_e4_fuel",        kind = "count", live = false, refusal = "capacity" },
}

FarmManager25.FARM_FRESH_LIVE = "live"
FarmManager25.FARM_FRESH_ASOF = "asof"

--- 1234567 -> "1,234,567". Written here rather than calling g_i18n:formatMoney
--  because this half must run headlessly with no engine present, and because
--  formatMoney is NOT in the fs25-lookup corpus (searched 2026-09-02) -- the
--  menu already calls it guarded, on a shipped mod's evidence alone.
--  ⚠ COST, stated not hidden: no locale currency symbol on FARM rows. That is
--  a deliberate ship-then-polish trade; wiring formatMoney back in is a change
--  to the menu's render, not to this contract.
local function groupDigits(n)
    local neg = n < 0
    local s = string.format("%d", math.floor(math.abs(n) + 0.5))
    local grouped = s:reverse():gsub("(%d%d%d)", "%1,")
    local out = grouped:reverse()
    if out:sub(1, 1) == "," then
        out = out:sub(2)
    end
    return (neg and "-" or "") .. out
end

--- Minutes -> "3d 4h" / "5h 20m" / "45m". Whole units only; a deadline shown to
--  the minute implies a precision the save file does not carry.
local function formatMinutes(m)
    m = math.floor(m + 0.5)
    if m < 0 then m = 0 end
    local d = math.floor(m / 1440)
    local h = math.floor((m % 1440) / 60)
    local mi = m % 60
    if d > 0 then return string.format("%dd %dh", d, h) end
    if h > 0 then return string.format("%dh %dm", h, mi) end
    return string.format("%dm", mi)
end

--- Resolve one value into what the row publishes: (valueNumber, valueText).
--
--  ⭐ MONEY IS PUBLISHED AS A RAW NUMBER AND FORMATTED BY THE MENU. Ruled
--  2026-09-02, and it is the same contract as labelKey: core publishes DATA,
--  the menu owns PRESENTATION. The menu already formats money at
--  InGameMenuFarmManager25.lua:503-506 -- `g_i18n:formatMoney(v, 0, true, true)`
--  guarded, with a string.format fallback -- so reusing it costs no new code,
--  keeps every engine call out of this assembler (which is what makes it
--  stub-free and testable), and above all stops the header balance chip and the
--  FARM money rows rendering the SAME figure in TWO different formats on one
--  screen. That inconsistency class is exactly what this work removed elsewhere.
--
--  Non-money kinds are formatted here: they need no locale and no engine, so
--  formatting them in core keeps the menu dumb and keeps the answer assertable.
--
--  ⛔ NEITHER RETURN IS EVER 0, "", or "-" FOR ABSENCE. 0 is a real balance a
--  real farm can have; a real contract count can be 0 too. Absence returns
--  (nil, nil) and the caller publishes `unknown`.
local function resolveFarmValue(kind, v)
    if type(v) ~= "number" then
        return nil, nil
    end
    if v ~= v then          -- NaN never equals itself
        return nil, nil
    end
    if kind == "money" then
        return v, nil       -- the MENU formats this one
    elseif kind == "count" or kind == "hours" then
        return nil, groupDigits(v)
    elseif kind == "area" then
        return nil, string.format("%.1f", v)
    elseif kind == "pct" then
        return nil, string.format("%d%%", math.floor(v + 0.5))
    elseif kind == "mins" then
        return nil, formatMinutes(v)
    end
    return nil, nil
end

--- ⭐ THE PURE ASSEMBLER. No engine reference of any kind lives below this
--  line and above its `end` -- that is what makes it lupa-testable without a
--  single g_* stub, and it is deliberate.
--
--  GUARD 8: a value that is not a number publishes `unknown = true` and NO
--  valueText. The menu renders the word. Never blank, never an em dash.
--  GUARD 7: every row carries `freshness`, and an as-of row carries the stamp
--  it is as of. A row can never be rendered without one.
--  GUARD 9: this ALWAYS returns every row of FARM_ROW_SPEC (20 since D-3). A fresh farm
--  with no data yet gets 20 honest `unknown`s, never a blank screen.
--- ⛔ FRESHNESS MARKS RENDER A TIME ONLY -- owner ruling, 2026-09-06. Applied
--  here rather than in the menu for the reason resolveFarmValue already gives
--  one function up: money crosses the seam raw because it needs a LOCALE, and
--  everything else is formatted in core because it needs neither a locale nor
--  an engine. A stamp is the second kind, and formatting it here keeps the one
--  answer a player reads about staleness inside the half a test can drive.
--
--  ⭐ ONE CALL, NO SECOND IMPLEMENTATION. stampText() is the same function the
--  PRODUCTIONS tab uses; both consumers of this stamp (the FARM header and the
--  header balance chip, which reads it off row a1) get it from the row, so
--  neither menu site needed touching.
--
--  ⚠ `nowText` IS AN ARGUMENT, NOT A CLOCK READ. Reading the clock here would
--  destroy the one property that makes this assembler gateable -- it is called
--  with NO g_* stub anywhere. The engine read lives in getFarmRows(), the
--  acquisition half, exactly as the split at the top of this section requires.
--  nil is legitimate and means "this caller could not say what now is": the
--  mark then carries the time alone and claims no age.
--  ⭐ `values._partial` ({id = true}) is F8's LOWER-BOUND flag: the skill
--  published a count of the KNOWN cases because some vehicles' tanks could not
--  be measured (encrypted DLC), so the figure is "at least N". A count row
--  renders "N+" -- a plain N would claim a completeness nobody measured. Zero
--  new strings: "+" is a numeral suffix, not language. It rides INSIDE the
--  values table, under a key no row id can equal, so readFarmFile's and this
--  function's signatures -- and every caller of them -- are unchanged. Ignored
--  for any kind but "count", and for an unknown row (no number to be a bound on).
function FarmManager25.buildFarmRows(values, asOfText, nowText)
    values = values or {}
    local partials = type(values._partial) == "table" and values._partial or {}
    local refused = type(values._refused) == "table" and values._refused or {}
    local rows = {}
    asOfText = FarmManager25.stampText(asOfText, nowText)

    for i = 1, #FarmManager25.FARM_ROW_SPEC do
        local spec = FarmManager25.FARM_ROW_SPEC[i]
        local number, text = resolveFarmValue(spec.kind, values[spec.id])
        if text ~= nil and spec.kind == "count" and partials[spec.id] then
            text = text .. "+"
        end

        local unknownRow = (number == nil and text == nil)
        rows[#rows + 1] = {
            id        = spec.id,
            group     = spec.group,
            labelKey  = spec.labelKey,
            kind      = spec.kind,
            -- F7: WHICH refusal explains this unknown, or nil. Set only for an unknown row
            -- whose <unknown> element the document carried (a refused figure); a row that
            -- is unknown because the file never arrived keeps the plain word.
            refusalKind = (unknownRow and refused[spec.id] == true) and spec.refusal or nil,
            -- Exactly one of these is ever set. valueNumber means "money, and
            -- the menu must format it"; valueText means "already presentable".
            valueNumber = number,
            valueText = text,
            unknown   = unknownRow,
            freshness = spec.live and FarmManager25.FARM_FRESH_LIVE
                                   or FarmManager25.FARM_FRESH_ASOF,
            -- Only an as-of row carries a stamp. A live row that carried one
            -- would be claiming its figure is older than it is.
            asOfText  = (not spec.live) and asOfText or nil,
        }
    end

    return rows
end

--- Read the values Cyrus published for THIS savegame.
--
--  ⛔ THIS FILE IS PERSISTENT AND IS NEVER CONSUMED. notify.xml is a single-slot
--  bridge that is consumed-and-deleted on read; farm.xml is NOT. If this ever
--  called consumeBridge, the FARM tab would populate exactly once and then be
--  empty forever -- and an empty FARM tab is indistinguishable from the fresh
--  farm that guard 9 says is legitimate. That confusion is the whole reason
--  this comment is here.
--
--  ⚠ A LIFETIME NOTHING ELSE IN THIS MOD HAS: written by the Python half,
--  read-only to Lua, durable. cards.xml is Lua-to-Lua; notify.xml is transient.
--
--  Shape (schema 1):
--    <farmManager25Farm generatedAt="..."><value id="b1" num="18"/>...</...>
--  A value whose `num` is missing or not a number is simply absent from the
--  returned table, which the assembler turns into `unknown`. Absence must not
--  be mistakable for data, so nothing is defaulted to 0 here.
--
--  Returns (values, asOfText). `values._refused` is F7's {id = true} set of rows the document
--  carried an <unknown> element for. `values._partial` is F8's {id = true} set of counts
--  published as lower bounds (`partial="true"`). Both nil-safe: an absent or corrupt file yields
--  an EMPTY table, never a partial-looking one, and the tab renders 20 unknowns.
--- `expectedKey` is the savegame this session belongs to, or nil when the
--  caller cannot say. See the provenance block inside for what each attribute
--  is worth.
function FarmManager25.readFarmFile(path, expectedKey)
    local values = {}
    local asOfText = nil
    local rejected = nil

    if path == nil or not fileExists(path) then
        return values, nil
    end

    local xml = XMLFile.load("FarmManager25Farm", path)
    if xml == nil then
        print("FarmManager25: could not parse " .. tostring(path)
            .. " as XML -- the FARM tab will show 'unknown' until it is rewritten")
        return values, nil
    end

    -- Same finally-equivalent shape as loadReplies: free the handle whether the
    -- body returns or throws, then re-raise. A throw between load and delete
    -- must never leak the engine handle (the F-P1-3 class).
    local okRead, errRead = pcall(function()
        -- ⛔ PROVENANCE, CHECKED. Both attributes were WRITTEN AND NEVER READ:
        -- the one field that could catch a wrong-savegame document was ignored.
        -- An unread stamp is worse than no stamp, because it creates the
        -- appearance of a check. Written-and-unread was the one indefensible
        -- state, so each is now either honoured here or retired at the writer.
        --
        -- ⚠ A MISMATCH IS PROOF; ABSENCE IS NOT. An attribute that is present
        -- and WRONG says this document is not ours. An attribute that is simply
        -- missing says only that an older writer produced it -- refusing that
        -- would break a working install on upgrade to buy nothing. So each
        -- check fires on disagreement and stays silent on absence.
        --
        -- Refusing fails SAFE: no values, no as-of, and guard 8 renders
        -- `unknown`. A wrong number is unacceptable; a missing one is not.
        -- ⚠ ONE REFUSAL POINT, DELIBERATELY. These checks RECORD a rejection
        -- and read on; the single gate at the end of this function is what
        -- withholds the document. An earlier draft returned early from here,
        -- and the mutation driver showed why that was wrong: with nothing yet
        -- read at the point of return, NO mutation of the refusal could change
        -- an answer -- corrupting it, deleting it, or making it hand back the
        -- freshness stamp all left the suite green. The branch that mattered
        -- most was the one branch no test could reach. Reading a document we
        -- are about to discard costs a few attribute lookups and buys a gate
        -- that can actually be proved.
        local schema = xml:getString("farmManager25Farm#schema")
        if schema ~= nil and schema ~= tostring(FarmManager25.FARM_SCHEMA) then
            rejected = "schema " .. tostring(schema) .. ", but this build reads "
                .. tostring(FarmManager25.FARM_SCHEMA)
        end

        -- The threat this one closes is REAL and this codebase has already been
        -- bitten by its class: the pre-scoping replies.xml let acks earned on
        -- one farm be claimed by whichever save ran the skill next (see
        -- discardLegacyReplies). The path is per-savegame keyed, so this does
        -- not guard against a wrong PATH -- it guards against a wrong FILE at
        -- the right path: `emit_farm_xml.py --out` will publish any savegame's
        -- figures anywhere it is pointed, and a copied modSettings folder does
        -- the same by hand.
        local stamped = xml:getString("farmManager25Farm#savegame")
        if rejected == nil and stamped ~= nil and expectedKey ~= nil
                and stamped ~= expectedKey then
            rejected = "stamped for " .. tostring(stamped) .. ", but this is "
                .. tostring(expectedKey)
        end

        asOfText = xml:getString("farmManager25Farm#generatedAt")

        for i = 0, #FarmManager25.FARM_ROW_SPEC - 1 do
            local key = string.format("farmManager25Farm.value(%d)", i)
            if not xml:hasProperty(key) then
                break
            end
            local id  = xml:getString(key .. "#id")
            local num = tonumber(xml:getString(key .. "#num"))
            if id ~= nil and num ~= nil and id ~= "_partial" and id ~= "_refused" then
                values[id] = num
                -- F8: a published count that is only a lower bound.
                if xml:getString(key .. "#partial") == "true" then
                    values._partial = values._partial or {}
                    values._partial[id] = true
                end
            end
        end

        -- F7 (BUG-030 FARM, BUG-039 render half): the emitter has always written
        -- <unknown id=".." reason=".."/> for a row it refuses to publish, and this reader
        -- ignored it -- the reason died on the way to the screen. Only PRESENCE is read
        -- here; the reason prose is English and open-ended and is never rendered. It rides
        -- in the values table under a key no row id can equal, exactly as `_partial` does,
        -- so no signature changes.
        for i = 0, #FarmManager25.FARM_ROW_SPEC - 1 do
            local key = string.format("farmManager25Farm.unknown(%d)", i)
            if not xml:hasProperty(key) then
                break
            end
            local id = xml:getString(key .. "#id")
            if id ~= nil and id ~= "_partial" and id ~= "_refused" then
                values._refused = values._refused or {}
                values._refused[id] = true
            end
        end
    end)

    local okDel = pcall(function() xml:delete() end)

    if not okRead then
        print("FarmManager25: farm.xml read failed (" .. tostring(errRead)
            .. ") -- the FARM tab will show 'unknown'")
        return {}, nil
    end
    if not okDel then
        print("FarmManager25: farm.xml handle could not be released")
    end

    if rejected ~= nil then
        print("FarmManager25: refusing " .. tostring(path) .. " -- " .. rejected
            .. " -- the FARM tab will show 'unknown' rather than another "
            .. "savegame's figures")
        return {}, nil
    end

    return values, asOfText
end

--- Calls ONE mission getter totally. nil means "this mission did not tell us",
--  and absence, a throw and a non-number all collapse to exactly that. None of
--  them may be mistaken for a figure (DEC-001).
--
--  ⚠ THE EXISTENCE PROBE THIS REPLACES COULD NOT SEE THE REAL FAILURE.
--  `m.getReward ~= nil` passes, because the method is REAL -- it throws instead
--  of returning. Probing for the method and then calling it outside a pcall
--  checks the one thing that was never in doubt.
function FarmManager25.askMission(m, name)
    return tonumber(FarmManager25.askMissionRaw(m, name))
end

--- The RAW twin: the same total pcall body, returning the getter's value
--  UNCOERCED. [[BUG-040]] ⛔ `tonumber(true)` is nil, so asking a BOOLEAN
--  getter (`getIsRunning`) or a STRING one (`getTitle`) through askMission
--  answers nil on every mission -- which is how the contract read was dead on
--  every farm. Boolean and string getters go through HERE; figures go through
--  askMission.
function FarmManager25.askMissionRaw(m, name)
    local ok, v = pcall(function()
        local fn = m[name]
        if fn == nil then
            return nil
        end
        return fn(m)
    end)
    if not ok then
        return nil
    end
    return v
end


--- The STRING twin of askMission, for the one identifier we need. Separate
--  because askMission ends in `tonumber(v)`, which turns a mission id into nil
--  -- the coercion that makes it safe for a figure destroys a key.
--
--  Grounded, not recalled (FS25-Community-LUADOC @ 24afb18e7cfb,
--  Missions/AbstractMission.md): `getUniqueId()` is documented "Gets this
--  mission's unique id" and its body is `return self.uniqueId` -- the SAME
--  field `saveToXMLFile` writes to `key#uniqueId`, which is the `uniqueId`
--  attribute read_missions.py already reads out of missions.xml. That shared
--  origin is what makes the join sound; a positional index would credit one
--  contract's payout to another.
--- ⛔⛔ THE FIELD id A MISSION IS ON -- **NOT** the mission's own id.
--  askMissionId() below returns `getUniqueId()`, the MISSION's identity, and it
--  is a STRING. Feeding that into a field lookup is the exact defect
--  FS25_YieldTracker ships: it puts a farmland id and a field id into one
--  variable named `fieldID`. Two id spaces, one name, and the join silently
--  matches nothing -- which renders as "no contract on any field", a clean,
--  plausible, entirely wrong answer.
--  ⭐ THE FIELD ID COMES FROM `getField():getId()` and from nowhere else.
--  Totally guarded, like every other mission read here: an offered mission has
--  no field yet, so `getField()` returning nil is ORDINARY, not exceptional.
function FarmManager25.askMissionFieldId(m)
    local ok, v = pcall(function()
        local fn = m.getField
        if fn == nil then
            return nil
        end
        local field = fn(m)
        if field == nil or field.getId == nil then
            return nil
        end
        return field:getId()
    end)
    if not ok then
        return nil
    end
    return tonumber(v)
end

function FarmManager25.askMissionId(m)
    local ok, v = pcall(function()
        local fn = m.getUniqueId
        if fn == nil then
            return nil
        end
        return fn(m)
    end)
    if not ok or type(v) ~= "string" or v == "" then
        return nil
    end
    return v
end


--- PURE. Reduces mission objects to the (id, reward) rows the skill merges,
--  plus a count of the missions that could not answer. Same split, and for the
--  same reason, as summarizeMissions: `missions` is an INPUT, so a fixture can
--  hand this a mission whose getter throws without faking one engine call.
--
--  ⛔ A ROW IS WRITTEN ONLY WHEN BOTH HALVES ANSWER, and only for a POSITIVE
--  reward. Three refusals, each for a different wrong answer:
--    * no id            -> nothing to join to; a positional write would move a
--                          payout onto the wrong contract.
--    * a throw          -> the measured engine case. AbstractFieldMission's
--                          getReward indexes self.field:getAreaHa(), and an
--                          offered mission has no field yet. Its neighbours
--                          keep their figures; only it is dropped.
--    * reward <= 0      -> `AbstractMission:getReward()` is the literal
--                          `return 0` (same corpus page), so 0 means "this
--                          mission type never overrode the base class" just as
--                          readily as it means a payout. Ambiguous therefore
--                          UNKNOWN -- publishing it would recreate the exact
--                          "$0" defect F-025 exists to prevent, one layer down.
--  A dropped row is not a silent loss: it simply never appears in the file, and
--  read_missions.py reports that contract's reward as UNKNOWN with its note --
--  which is what it already does today for every contract.
function FarmManager25.contractRows(missions)
    local rows, dropped = {}, 0
    if type(missions) ~= "table" then
        return rows, dropped
    end

    for i = 1, #missions do
        local m = missions[i]
        local id, reward = nil, nil
        if type(m) == "table" then
            id = FarmManager25.askMissionId(m)
            reward = FarmManager25.askMission(m, "getReward")
        end
        if id ~= nil and reward ~= nil and reward > 0 then
            rows[#rows + 1] = { id = id, reward = reward }
        else
            dropped = dropped + 1
        end
    end

    return rows, dropped
end


--- PURE. Reduces a list of mission objects to the four contract figures,
--  returning d1, d2, d3, d4 -- any of d2..d4 nil when nothing answered it.
--
--  ⭐ WHY THIS IS SPLIT OUT, and why it is not abstraction for its own sake. It
--  is the same split buildFarmRows already uses: the half a headless test can
--  honestly gate is gated, and the engine half -- obtaining the list -- stays
--  with the owner's live test. `missions` is an INPUT here, not a stubbed
--  boundary, so a fixture can hand this a mission whose getter throws without
--  faking a single engine call.
--
--  ⛔ THE DEFECT THIS EXISTS TO FIX (owner live test, savegame3 / MapUS): the
--  FARM tab rendered d1 = 12 with d2, d3 and d4 all `unknown` -- TOGETHER. That
--  pattern is not three getters returning nil. AbstractMission:getReward()
--  returns 0 and :getCompletion() returns 0.0 -- LITERAL CONSTANTS, never nil
--  -- so a nil return could not have blanked d2 and d4; they would have read 0.
--  What blanks all three at once is a THROW: one mission raises, the single
--  enclosing pcall unwinds, and every figure is lost along with the missions
--  never reached. d1 survived only because it is assigned before the loop.
--
--  The throw is expected, not exotic. getMissionsByFarmId returns
--  `mission.farmId == nil or mission.farmId == farmId` -- the engine's own
--  comment is "All missions, but only for active it needs to match the farm" --
--  so the list carries OFFERED contracts, which no farm owns and which were
--  never started. AbstractFieldMission:getReward indexes `self.field:getAreaHa()`
--  and :getCompletion reaches `#self.completionPartitions` by way of
--  getFieldCompletion; on a mission never started, those are the fields that do
--  not exist yet. Isolating each call keeps ONE throw from costing the OTHER
--  missions their figures. It does NOT make a call harmless.
--
--  ⛔ [[BUG-052]] A `pcall` CONTAINS A THROW; IT DOES NOT UNDO STATE SET BEFORE
--  THE THROW. This comment used to end "Isolating each call costs the other
--  missions nothing", and for :getCompletion that was false. Measured in the
--  engine source (gameSource.zip, AbstractFieldMission.lua:460-464):
--  getFieldCompletion runs `self:initializeModifier()` and THEN sets
--  `self.isFieldCompletionInitialized = true`. On an offered mission
--  `completionModifier` is nil (createModifier runs only in prepare(), :243),
--  so initializeModifier builds no `completionPartitions`, the flag is set
--  anyway, and the call then throws -- which the pcall swallowed. The flag
--  stays true for the life of the session, so once the player ACCEPTS the
--  contract nothing ever builds the partitions and every update fails
--  (`AbstractFieldMission.lua:493 ... ipairs (table expected, got nil)`, every
--  frame). The engine itself asks :getCompletion only of RUNNING missions
--  (AbstractMission.lua:409-414, updateTick). So completion is asked ONLY of a
--  mission whose :getIsRunning() is the boolean true. :getIsRunning is
--  `return self.status == MissionStatus.RUNNING` (AbstractMission.lua:796-798):
--  a pure read, safe to ask of an offered mission.
function FarmManager25.summarizeMissions(missions)
    if type(missions) ~= "table" then
        return nil, nil, nil, nil, nil
    end

    -- D1: a real 0 is DATA -- a farm can legitimately hold no contracts, and
    -- that is not the same as "we could not ask".
    local count = #missions

    local rewardTotal, rewardSeen = 0, 0
    local soonest, deadlineSeen = nil, 0
    local completionTotal, completionSeen = 0, 0

    for i = 1, count do
        local m = missions[i]
        if type(m) == "table" then
            local r = FarmManager25.askMission(m, "getReward")
            if r ~= nil then
                rewardTotal = rewardTotal + r
                rewardSeen = rewardSeen + 1
            end

            local mins = FarmManager25.askMission(m, "getMinutesLeft")
            if mins ~= nil then
                deadlineSeen = deadlineSeen + 1
                if soonest == nil or mins < soonest then
                    soonest = mins
                end
            end

            -- ⛔ [[BUG-052]] COMPLETION IS ASKED ONLY OF A RUNNING MISSION.
            -- `== true`, not truthiness: askMissionRaw returns the getter's
            -- value uncoerced, and a getter that threw answers nil, which is
            -- NOT running. An offered mission is never asked; see the comment
            -- above summarizeMissions for the engine state a single call on one
            -- would change.
            if FarmManager25.askMissionRaw(m, "getIsRunning") == true then
                local c = FarmManager25.askMission(m, "getCompletion")
                if c ~= nil then
                    completionTotal = completionTotal + c
                    completionSeen = completionSeen + 1
                end
            end
        end
    end

    -- Each figure is published ONLY if at least one mission answered it. A sum
    -- over zero readable rewards is 0, and publishing that would be the exact
    -- "$0" F-025 warns about -- absence dressed as data.
    --
    -- ⏳ DEFERRED, NOT MISSED -- PARTIAL SUMS UNDER TOTAL LABELS.
    -- This separates NONE-answered from SOME-answered. It does NOT separate
    -- SOME from ALL. If 3 of 12 contracts answer, a player reads a figure
    -- labelled as a total that covers a quarter of their contracts.
    --
    -- ⛔ THE SCOPE IS WIDER THAN IT LOOKS, and this note exists because the
    -- original brief got it wrong in three places:
    --   * d2 is a partial SUM -- it understates, predictably.
    --   * d4 is a partial AVERAGE over answerers, NOT a sum. That is worse: a
    --     partial sum always understates and can be reasoned about, while a
    --     partial average can land anywhere and looks entirely plausible.
    --   * d3 IS IN SCOPE. It was ruled out for being a min rather than a sum.
    --     The direction of harm is what matters: a min over a SUBSET is always
    --     >= the true min, so the row tells the player they have MORE time than
    --     they do -- on the one row they act on under time pressure.
    --   * e2 and e3 have the same shape but live in PYTHON, in
    --     emit_farm_xml.py (saw_damage / saw_hours), not in this file.
    --
    -- Deferred deliberately by the owner-facing gate, not overlooked: after the
    -- per-getter isolation above, "partial" is probably the NORMAL case rather
    -- than an edge, because offered contracts appear structurally unable to
    -- answer. Publishing `unknown` for a partial would then blank d2 and d4 on
    -- a healthy farm -- identical to the broken output this fix just repaired.
    -- FarmManager25.contractsDiagnostic reports, per figure, how many of the
    -- contracts answered it, so ONE live test decides this with a measurement
    -- instead of a guess ([[DEC-080]]).
    --
    -- ⚠ THIS COMMENT USED TO SAY THE LINE BELOW ALREADY DID THAT, AND IT WAS
    -- FALSE IN BOTH HALVES. The line fired only when a figure was COMPLETELY
    -- unanswered -- silent on exactly the partial this note calls the normal
    -- case -- and when it did fire it printed `count`, the TOTAL, under the
    -- words "contract(s) answered". The counters it claimed to report were
    -- locals that were never returned. It had zero test coverage.
    local reward = nil
    if rewardSeen > 0 then
        reward = rewardTotal
    end

    local completion = nil
    if completionSeen > 0 then
        -- getCompletion() is documented 0..1; render as a percentage.
        completion = (completionTotal / completionSeen) * 100
    end

    -- The 5th return is the DIAGNOSTIC channel, deliberately separate from the
    -- four published figures: it says how many contracts answered each one, so
    -- a partial can be told from a full answer. It changes nothing a player
    -- sees -- d2/d3/d4 above are byte-for-byte the values this returned before.
    return count, reward, soonest, completion, {
        reward = rewardSeen,
        deadline = deadlineSeen,
        completion = completionSeen,
    }
end


--- PURE. Builds the in-band contracts diagnostic line, or nil when there is
--  nothing to report.
--
--  ⭐ WHY THIS IS A FUNCTION AND NOT A `print` AT THE CALL SITE. The emitted
--  LINE is the artifact a live test reads. Assembling it inside the engine-only
--  pcall below put both the fire condition and the numbers somewhere no
--  headless test could reach -- which is precisely how a diagnostic that
--  printed the TOTAL under the words "contract(s) answered", and that stayed
--  silent on every partial, shipped with zero coverage. Returning the string
--  gates the document itself; the caller only prints it.
function FarmManager25.contractsDiagnostic(count, answered)
    if type(count) ~= "number" or type(answered) ~= "table" then
        return nil
    end

    local r = tonumber(answered.reward) or 0
    local s = tonumber(answered.deadline) or 0
    local c = tonumber(answered.completion) or 0

    -- A PARTIAL is the case this instrument exists to measure, and the case the
    -- original condition was silent for. `count == 0` stays a trigger so that
    -- nothing which used to report stops reporting: a farm with no contracts
    -- answers no figure, and that is still worth one line to a live test.
    local partial = r < count or s < count or c < count
    if not partial and count > 0 then
        return nil
    end

    return "FarmManager25: contracts " .. tostring(count)
        .. " -- reward " .. tostring(r) .. "/" .. tostring(count)
        .. " deadline " .. tostring(s) .. "/" .. tostring(count)
        .. " completion " .. tostring(c) .. "/" .. tostring(count)
end


--- THE ENGINE BOUNDARY. Fills the `live = true` ids in `values`, in place.
--
--  ⛔ NOT HEADLESSLY TESTABLE, AND DELIBERATELY NOT STUBBED. Doctrine: never
--  stub the boundary under test -- for engine behaviour the real runtime is the
--  gate, a live test or nothing. Everything here is total: any missing global,
--  missing method or thrown lookup leaves the id absent, and the assembler
--  publishes `unknown`. A wrong number is unacceptable; a missing one is not.
--  ⚠ "Total" was once true only per GROUP, not per FIGURE: one thrown getter
--  inside group D unwound the whole group and blanked three ids at once. That
--  is the defect summarizeMissions was extracted to close.
--
--  A1 is ADAPTED, not invented: it is the shipped InGameMenuFarmManager25
--  getFarmBalance() logic moved into core -- documented Farm:getBalance() first,
--  FOD's undocumented farm.money kept only as the fallback behind it, and nil
--  rather than 0 on failure. Moving it here is what lets the menu stop calling
--  the engine at all (DEC-128 ②); it also retires that call site rather than
--  adding a second one beside it.
function FarmManager25.readLiveValues(values)
    values = values or {}

    local ok = pcall(function()
        local farmId = nil
        if g_currentMission ~= nil and g_currentMission.getFarmId ~= nil then
            farmId = g_currentMission:getFarmId()
        end

        local farm = nil
        if farmId ~= nil and farmId ~= 0
                and g_farmManager ~= nil and g_farmManager.getFarmById ~= nil then
            farm = g_farmManager:getFarmById(farmId)
        end

        if farm ~= nil then
            -- A2-A4 are LUADOC-ONLY (Farm.lua is absent from the archive), so
            -- each is probed for existence before it is called. If a getter is
            -- not there at runtime the row reads `unknown` -- which is guard 8
            -- doing its job, not a defect.
            if farm.getBalance ~= nil then
                values.a1 = tonumber(farm:getBalance())
            elseif farm.money ~= nil then
                values.a1 = tonumber(farm.money)
            end
            if farm.getLoan ~= nil then
                values.a2 = tonumber(farm:getLoan())
            end
            if farm.getEquity ~= nil then
                values.a3 = tonumber(farm:getEquity())
            end
            if farm.calculateDailyLoanInterest ~= nil then
                values.a4 = tonumber(farm:calculateDailyLoanInterest())
            end
        end

        -- Last resort for the balance only, exactly as the shipped menu code
        -- had it: g_currentMission:getMoney() is FOD's route and is undocumented.
        if values.a1 == nil and g_currentMission ~= nil and g_currentMission.getMoney ~= nil then
            values.a1 = tonumber(g_currentMission:getMoney())
        end
    end)

    if not ok then
        -- Caught, never thrown. An engine lookup that throws from a GUI-path
        -- callback is what killed the load at 57%.
        print("FarmManager25: a live money lookup failed -- those rows read 'unknown'")
    end

    -- GROUP D -- CONTRACTS. Its own pcall, not folded into the money block:
    -- a contracts failure must not cost us the balance we already read.
    --
    -- ⭐ LIVE BECAUSE D IS LIVE-ONLY. D2 (reward) is not merely missing from
    -- our parser -- it is ABSENT FROM THE SAVEGAME: the game computes a
    -- field-tied reward at accept-time, and read_missions.py refuses to report
    -- the placeholder as "$0" (FRICTION-LOG F-025). D3 (deadline) has no save
    -- field at all. Both have real bodies in the archive
    -- (AbstractFieldMission.lua:550-561, AbstractMission.lua:723-751), so the
    -- engine is the only place either can be known.
    --
    -- ⚠ ARCHIVE-EVIDENCED, NOT RUNTIME-PROVEN. Every getter call is ISOLATED,
    -- so a mission that cannot answer -- whether the method is missing, returns
    -- nothing, or THROWS -- leaves only its own contribution out, and guard 8
    -- renders `unknown` for a figure nobody answered. The probe that used to
    -- stand here checked existence, which was never the thing failing; see
    -- FarmManager25.summarizeMissions. The owner's live test confirms these four.
    local okD = pcall(function()
        local farmId = nil
        if g_currentMission ~= nil and g_currentMission.getFarmId ~= nil then
            farmId = g_currentMission:getFarmId()
        end
        if farmId == nil or farmId == 0
                or g_missionManager == nil
                or g_missionManager.getMissionsByFarmId == nil then
            return
        end

        local missions = g_missionManager:getMissionsByFarmId(farmId)
        if type(missions) ~= "table" then
            return
        end

        -- The reduction itself is pure and headlessly gated; see
        -- FarmManager25.summarizeMissions. Only ACQUIRING the list is engine.
        local d1, d2, d3, d4, answered = FarmManager25.summarizeMissions(missions)
        values.d1 = d1
        if d2 ~= nil then values.d2 = d2 end
        if d3 ~= nil then values.d3 = d3 end
        if d4 ~= nil then values.d4 = d4 end

        -- ⚠ IN-BAND REPORT OF A DEGRADED MEASUREMENT. Before the per-getter
        -- isolation below, an unanswered figure and a THROWN one were the same
        -- silent `unknown`, so a live test could not tell them apart. It can
        -- now: this reports, per figure, how many of the contracts answered it,
        -- which is what separates a PARTIAL from a full answer.
        local msg = FarmManager25.contractsDiagnostic(d1, answered)
        if msg ~= nil then
            print(msg)
        end
    end)

    if not okD then
        print("FarmManager25: a live contracts lookup failed -- those rows read 'unknown'")
    end

    return values
end

--- ⭐ THE PUBLISHED SEAM. The menu calls exactly this and renders what it gets.
--  Rebuilt per call so the live rows are actually live.
function FarmManager25:getFarmRows()
    local values, asOfText = {}, nil

    if self.saveFolder ~= nil then
        values, asOfText = FarmManager25.readFarmFile(
            self.saveFolder .. FarmManager25.FARM_NAME,
            FarmManager25.savegameKey())
    end

    FarmManager25.readLiveValues(values)

    -- Publish the per-contract rewards while the engine is already answering.
    -- ⭐ WHY HERE. This is the menu's ONE read per page open
    -- (InGameMenuFarmManager25.lua:441), i.e. human cadence -- the same cadence
    -- the card store is flushed at, never a per-frame write. The rewards are
    -- live-only and go stale as contracts expire and respawn, so a load-time
    -- write alone would publish yesterday's offers; deleteMap catches the
    -- player who quits without opening the tab.
    self:saveContracts()

    return FarmManager25.buildFarmRows(values, asOfText, FarmManager25.nowStamp())
end

-- ---------------------------------------------------------------------------
-- THE PRODUCTIONS TABLE -- the FIFTH published seam (SPEC Block D, item D5).
--
-- ⛔ THE FIFTH, NOT THE SIXTH, AND THERE IS NOTHING NAMED getFieldRows TO COPY.
-- The spec originally called this "the sixth seam alongside getFieldRows()";
-- `getFieldRows` is ZERO across mod/source, measured, with the four real seams
-- -- getMessageLog, SETTINGS_ROWS, register, getFarmRows -- firing as a
-- control. This follows getFarmRows() instead, and follows it deliberately.
--
-- ⛔ THE SPLIT IS THE SAME ONE, FOR THE SAME REASON: ASSEMBLY vs ACQUISITION.
--   buildProductionRows() -- PURE. Zero engine references. Takes the parsed
--                            document and produces the rendered rows. This is
--                            what the headless lupa suite drives, and it is
--                            where a mutated ANSWER must turn the suite red.
--   readProductionsFile() -- the engine XML boundary, thin and guarded.
--
-- ⛔ AND ONE THING getFarmRows() DOES NOT NEED: TWO RETURN VALUES.
-- `#rows == 0` is ITSELF an answer here -- a farm can legitimately own no
-- production points -- so "no productions" and "could not ask" need separate
-- channels or the tab renders a farm with 27 buildings identically to a broken
-- read. `meta.status` is that channel. FARM never had the problem: its 20 rows
-- are a fixed spec and an empty read still publishes 20 honest `unknown`s.
--
-- ⛔ EVERY FIGURE HERE IS FILE / AS-OF. There is no live half, so freshness is
-- a PER-TAB property and one header serves the page -- but it carries TWO
-- stamps, not one: `asOfText` for savegame-derived figures and `defsAsOfText`
-- for definition-derived ones. They can differ by weeks, and rendering one
-- would let month-old definition data borrow a savegame read's freshness.
-- ---------------------------------------------------------------------------

--- The PRODUCTIONS document emit_productions_xml.py publishes for THIS
--  savegame. ⛔ PERSISTENT and NEVER consumed, for the same reason farm.xml is:
--  a consumed bridge would populate the tab once and leave it empty forever,
--  indistinguishable from the legitimate no-productions state.
FarmManager25.PRODUCTIONS_NAME   = "productions.xml"
--- Must track SCHEMA_VERSION in emit_productions_xml.py. A document stamped
--  anything else is refused rather than read with v1 semantics.
FarmManager25.PRODUCTIONS_SCHEMA = 1
-- Bounds on what we will read out of one document. Not a screen bound -- the
-- list scrolls -- but a memory bound, the same shape as MAX_STORE: a corrupt or
-- hostile file must not be able to make this loop forever.
FarmManager25.MAX_POINTS       = 64
FarmManager25.MAX_POINT_ROWS   = 32       -- per section, per point

--- ⛔ THE RUNWAY BAR'S FIXED HORIZON, IN HOURS. One in-game week.
--  A bar normalised to the largest value ON SCREEN makes the healthiest chain
--  look full and the whole farm look fine; the comparison must be against a
--  CONSTANT so a half-full bar means the same thing on every point. The owner
--  adjusts this in his live test -- it is the one number here that is a design
--  choice rather than a measurement.
FarmManager25.RUNWAY_HORIZON_H = 168

--- ⛔ THE FOOTER'S URGENCY CUT-OFF, IN IN-GAME HOURS. [[DEC-196]], and it lives
--  HERE rather than in FarmManagerTheme.lua by that ruling: that file holds
--  visual values, and a cut-off decides what is TRUE about the farm, not how it
--  looks. This is NOT the bar horizon above -- the bar is normalised to a week
--  so half-full means the same thing everywhere; this is the line below which a
--  point is called out.
--
--  ⭐ 24 IS MEASURED, NOT PICKED. savegame1, read 2026-09-11: runways cluster
--  below 11.29 h and then nothing until 52.20 h, so 24 sits mid-gap -- and it
--  is exactly one in-game day. 6/12/24/48 all flag the same handful today, so
--  counts cannot separate them; 6 h and 12 h are disqualified ON FUNCTION,
--  because 89.4% of the owner's elapsed game time arrived via sleep or skip at
--  ~22 game-hours a go, so a point can go from unflagged to starved without the
--  warning ever being on screen.
FarmManager25.RUNWAY_CUTOFF_H = 24

--- 1234.5 -> "1,235". Litres and hours are read as magnitudes, not to the
--  decimal. Reuses the same digit grouping the FARM table publishes so one
--  farm's numbers do not render two ways on two tabs.
local function groupLitres(n)
    local neg = n < 0
    local s = string.format("%d", math.floor(math.abs(n) + 0.5))
    local grouped = s:reverse():gsub("(%d%d%d)", "%1,")
    local out = grouped:reverse()
    if out:sub(1, 1) == "," then
        out = out:sub(2)
    end
    return (neg and "-" or "") .. out
end

--- Hours -> "0.0" / "12.5" / "318". ⛔ ONE DECIMAL BELOW 100 AND NONE ABOVE,
--  deliberately: `0.0` is THE most important state on this tab (starved right
--  now) and rounding it to a bare "0" would make it read like a missing value
--  in a column whose other cells carry decimals. Above 100 hours the decimal is
--  precision the join does not have.
local function formatHours(h)
    if h < 100 then
        return string.format("%.1f", h)
    end
    return groupLitres(h)
end

-- ---------------------------------------------------------------------------
-- ⛔ FRESHNESS MARKS RENDER A TIME ONLY -- NO DATES. Owner ruling, 2026-09-06:
-- "LIVE / AS-OF shows a time only, no dates on messages tab only." Dates belong
-- to the MESSAGES tab and nowhere else.
--
-- ⛔ WHY THE FORMATTING LIVES IN CORE AND NOT IN THE MENU. This is the same
-- boundary resolveFarmValue already draws: money crosses the seam as a raw
-- number because it needs a LOCALE, and every other kind is formatted here
-- because it needs neither a locale nor an engine. A stamp is the second kind.
-- Formatting it in the menu would put the one answer a player reads about
-- staleness inside the one half of this codebase no test can drive.
--
-- ⚠⚠ AND HERE IS THE CASE THE RULING'S ONE SENTENCE DOES NOT COVER, HANDLED
-- RATHER THAN GUESSED AT. The PRODUCTIONS tab carries TWO stamps and they are
-- not the same kind of fact:
--
--   generatedAt -- when the skill last read the savegame. Refreshed whenever
--                  the emitter runs, so in ordinary use it is from today and a
--                  bare time is exactly right.
--   defsAsOf    -- when the production_defs CACHE was generated. It is
--                  regenerated only by a 900-second walk of the whole install
--                  tree, so it is EXPECTED to be days or weeks old.
--
-- MEASURED on the owner's live farm today: generatedAt 2026-09-06 13:59,
-- defsAsOf 2026-08-20 02:10 -- SEVENTEEN DAYS APART. Rendered as bare times
-- those read "13:59" and "02:10", and a player sees a seventeen-day-old
-- capacity figure presented as if it were from eleven hours ago. That is a
-- stale figure wearing a fresh mark, which is the precise failure the two
-- stamps were split apart to prevent.
--
-- ⭐ SO: A TIME, ALWAYS -- plus a DAY COUNT when, and only when, the stamp does
-- not fall on the same day as the document that carries it. A day count is not
-- a date: it names an AGE, which is the fact the player needs and the fact a
-- bare time silently misstates. On a healthy farm both stamps are from the same
-- day and both render as bare times, exactly as ruled -- the qualifier appears
-- only in the case that would otherwise lie.
-- ⚠ THIS IS AN INTERPRETATION OF A TERSE RULING AND IS FLAGGED AS ONE. If the
-- owner wants the bare time even at seventeen days, deleting the suffix is one
-- branch in stampText().
-- ---------------------------------------------------------------------------

--- Today, as a stamp stampAgeDays() can read, or nil.
--  ⛔ THE ONLY ENGINE CALL IN THIS FEATURE, and it is isolated to one line so
--  the assemblers that consume its result stay pure. `getDate` is already this
--  mod's established clock -- writeReply and saveCards both call it under
--  exactly this pcall shape -- so this reuses a call that already ships rather
--  than introducing a second way to ask the time.
--  ⚠ A DEAD CLOCK RETURNS nil AND THAT IS HANDLED, not defaulted: the caller
--  then renders a bare time and claims no age. Inventing "now" would let a
--  week-old document mark itself current, which is the whole failure this
--  feature exists to prevent.
function FarmManager25.nowStamp()
    local ok, stamp = pcall(function() return getDate("%Y-%m-%d %H:%M:%S") end)
    if ok and type(stamp) == "string" then
        return stamp
    end
    return nil
end

--- Pull (year, month, day, hour, minute) out of a stamp, or nil.
--  ⛔ TOTAL AND FORMAT-AGNOSTIC BY CONSTRUCTION. Two writers produce these and
--  they do NOT agree on shape: emit_productions_xml.py writes
--  "2026-09-06 13:59 UTC" and the cache's own cache_entry carries
--  "2026-08-20T02:10:37.942Z". Matching the digits rather than a layout is what
--  makes one reader serve both -- and an unparseable stamp returns nil, which
--  the caller turns into `unknown`. ⛔ It NEVER falls back to "now": a stamp we
--  could not read must not be able to claim freshness.
local function stampParts(stamp)
    if type(stamp) ~= "string" then
        return nil
    end
    local y, mo, d = stamp:match("(%d%d%d%d)-(%d%d)-(%d%d)")
    local h, mi = stamp:match("(%d%d):(%d%d)")
    if y == nil or h == nil then
        return nil
    end
    return tonumber(y), tonumber(mo), tonumber(d), tonumber(h), tonumber(mi)
end

--- Days from the civil epoch. Hinnant's algorithm, integer arithmetic only --
--  no os.date, no os.time, no engine clock, so this half stays pure and
--  headlessly assertable. Only DIFFERENCES of the result are ever used, so the
--  epoch it counts from does not matter.
local function daysFromCivil(y, m, d)
    y = (m <= 2) and (y - 1) or y
    local era = math.floor(y / 400)
    local yoe = y - era * 400
    local doy = math.floor((153 * (m + ((m > 2) and -3 or 9)) + 2) / 5) + d - 1
    local doe = yoe * 365 + math.floor(yoe / 4) - math.floor(yoe / 100) + doy
    return era * 146097 + doe - 719468
end

--- Whole days `stamp` falls BEFORE `reference`. nil when either is unreadable.
--  ⚠ Negative is clamped to 0: a defs cache stamped AFTER the document that
--  cites it is a clock problem, not an age, and reporting "-3d" would invite a
--  reader to treat it as a measurement.
function FarmManager25.stampAgeDays(stamp, reference)
    local y1, m1, d1 = stampParts(stamp)
    local y2, m2, d2 = stampParts(reference)
    if y1 == nil or y2 == nil then
        return nil
    end
    local diff = daysFromCivil(y2, m2, d2) - daysFromCivil(y1, m1, d1)
    return diff > 0 and diff or 0
end

--- The rendered freshness mark: "13:59", or "02:10 (17d)" when the stamp is
--  older than the document quoting it. Returns nil when unreadable, and the
--  menu renders the word `unknown` -- never a blank, never a fabricated time.
--  `reference` may be nil, in which case no age can be computed and the bare
--  time is all that is claimed.
function FarmManager25.stampText(stamp, reference)
    local _y, _m, _d, h, mi = stampParts(stamp)
    if h == nil then
        return nil
    end
    local text = string.format("%02d:%02d", h, mi)
    local age = reference ~= nil and FarmManager25.stampAgeDays(stamp, reference) or nil
    if age ~= nil and age > 0 then
        text = text .. string.format(" (%dd)", age)
    end
    return text
end

--- ⭐ THE PURE ASSEMBLER. No engine reference of any kind lives below this line
--  and above its `end`. Takes the parsed document and returns (rows, meta).
--
--  ⛔ ABSENCE IS A FLAG, NEVER A VALUE. Every cell publishes `unknown = true`
--  and NO text when the document did not carry it; the menu renders the WORD,
--  from l10n. Never blank, never a dash, never a zero.
--
--  ⛔ AND A KNOWN ZERO IS NOT ABSENCE. `hoursToEmpty="0.0"` is a real measured
--  value meaning STARVED RIGHT NOW -- the most important state on the tab. It
--  publishes runwayUnknown = false, a runway text of "0.0" and a ratio of 0,
--  which the menu draws as an EMPTY FILL INSIDE A VISIBLE TRACK. An unknown
--  runway publishes no ratio at all and the menu hides the track entirely.
--  A 0-width bar and an absent bar look identical, so they must be told apart
--  before the pixels, not at them (DEC-001 in pixels).
--
--  ⛔ p2, THE MASTER LIST'S RUNWAY, IS DERIVED HERE FROM THE POINT'S OWN INPUT
--  ROWS -- it is deliberately NOT a second figure carried on the document.
--  A `shortestRunway` attribute would be a second answer to a question the
--  input rows already answer, and the two could disagree; a player who opens a
--  point and reads a different number from the one in the list he clicked has
--  been told the manager cannot count.
function FarmManager25.buildProductionRows(doc, meta, nowText)
    local rows = {}
    doc = doc or {}
    meta = meta or {}

    for _, point in ipairs(doc) do
        local row = {
            id          = point.id,
            name        = point.name,
            nameDerived = (point.nameSource == "derived"),
            inputs      = {},
            lines       = {},
            outputs     = {},
        }

        local shortest = nil
        for _, i in ipairs(point.inputs or {}) do
            local held      = tonumber(i.held)
            local perHour   = tonumber(i.perHour)
            local hours     = tonumber(i.hoursToEmpty)
            -- NaN never equals itself. Normalised ONCE, here, so runwayUnknown,
            -- runwayText and the bar ratio cannot disagree about whether this
            -- row has a runway -- three fields bearing one answer with only one
            -- of them checked is this project's founding defect class.
            if hours ~= hours then hours = nil end
            local ratio     = nil
            if hours ~= nil then
                if shortest == nil or hours < shortest then
                    shortest = hours
                end
                ratio = hours / FarmManager25.RUNWAY_HORIZON_H
                if ratio > 1 then ratio = 1 end
                if ratio < 0 then ratio = 0 end
            end
            table.insert(row.inputs, {
                label        = i.label or i.ft or "",
                -- ⛔ THE TOKEN, KEPT BESIDE THE LABEL AND NEVER INSTEAD OF IT.
                -- [[DEC-195]]: the row icon is resolved by fill-type TOKEN, never
                -- by the display label -- the label is a title and would not
                -- match in another language. nil when the document carried none,
                -- which resolves to no icon and therefore the dimmed glyph.
                ft           = i.ft,
                heldText     = held ~= nil and groupLitres(held) or nil,
                heldUnknown  = held == nil,
                burnText     = perHour ~= nil and groupLitres(perHour) or nil,
                burnUnknown  = perHour == nil,
                runwayText   = hours ~= nil and formatHours(hours) or nil,
                runwayUnknown = hours == nil,
                -- nil ratio = draw NO bar. 0 = draw an empty bar in a visible
                -- track. The two are different facts (rules 4 and 5).
                ratio        = ratio,
                rate         = i.rate,
                reason       = i.reason,
                -- [[DEC-197]] passes through UNINTERPRETED. Core does not
                -- decide what `stocked`/`empty`/`notStarted`/`unknown` mean --
                -- the emitter's classify_absent_stock owns that verdict, and
                -- the page owns the appearance. A nil here is a document that
                -- predates the field, which the page renders as `unknown`.
                stockState   = i.stockState,
                stateReason  = i.stateReason,
                heldReason   = i.heldReason,
            })
        end

        row.runwayText    = shortest ~= nil and formatHours(shortest) or nil
        row.runwayUnknown = (shortest == nil)
        -- ⭐ THE NUMBER THE TEXT WAS MADE FROM, not a second answer to the same
        -- question. The footer has to COUNT points under a cut-off, and parsing
        -- "11.3 h" back out of the rendered string to do it would be a second
        -- derivation that could disagree with the first -- the exact defect the
        -- p2 comment above refuses. So the source value is published and the
        -- text stays derived from it. nil whenever runwayUnknown is true, and
        -- the two are set from one variable so they cannot drift.
        row.runwayHours   = shortest

        for _, l in ipairs(point.lines or {}) do
            local out = tonumber(l.outPerHour)
            -- ⛔ `On` / `Off`, NEVER `Running` / `Idle`. `enabled` is read from
            -- placeables.xml and says "is this line switched on". Running/Idle
            -- is "is it producing right now", a DIFFERENT fact, and it is killed
            -- by owner ruling. A lane copying Distribution Redux's STATUS column
            -- brings Running/Idle/Off across; that is the line to refuse.
            local enabled = nil
            if l.enabled == "true" then
                enabled = true
            elseif l.enabled == "false" then
                enabled = false
            end
            table.insert(row.lines, {
                name        = l.name or l.id or "",
                nameDerived = (l.nameSource == "derived"),
                enabled     = enabled,
                enabledUnknown = (enabled == nil),
                outText     = out ~= nil and groupLitres(out) or nil,
                outUnknown  = (out == nil),
                limitingText = l.limitingInput,
                limitingUnknown = (l.limitingInput == nil),
                reason      = l.outReason,
            })
        end

        for _, o in ipairs(point.outputs or {}) do
            local held = tonumber(o.held)
            local cap  = tonumber(o.capacity)
            -- ⛔ THE RATIO NEEDS BOTH TERMS. A held level presented as a
            -- percentage against a guessed ceiling is the over-claim
            -- read_productions.py refuses to make on its own; the join belongs
            -- to the consumer and this is the consumer, but doing it without a
            -- capacity is the defect, not the feature.
            local pct, ratio = nil, nil
            if held ~= nil and cap ~= nil and cap > 0 then
                ratio = held / cap
                if ratio > 1 then ratio = 1 end
                if ratio < 0 then ratio = 0 end
                pct = string.format("%d%%", math.floor(ratio * 100 + 0.5))
            end
            table.insert(row.outputs, {
                label       = o.label or o.ft or "",
                -- Same rule as the input rows above (DEC-195).
                ft          = o.ft,
                heldText    = held ~= nil and groupLitres(held) or nil,
                heldUnknown = (held == nil),
                capText     = cap ~= nil and groupLitres(cap) or nil,
                capUnknown  = (cap == nil),
                pctText     = pct,
                pctUnknown  = (pct == nil),
                ratio       = ratio,
                reason      = o.capacityReason,
                -- ⚠ NO stockState ON AN OUTPUT ROW -- see the reader. The
                -- refusal is carried by heldReason instead, and `held="0.0"`
                -- is a real measured zero ([[DEC-203]]).
                heldReason  = o.heldReason,
            })
        end

        table.insert(rows, row)
    end

    -- ⛔ TIME ONLY, NO DATES (owner, 2026-09-06) -- and the DEFINITIONS stamp is
    -- aged against the DOCUMENT'S OWN stamp, not against a clock. That keeps
    -- this assembler pure, and it is also the comparison that actually matters:
    -- how much older the definition data is than the savegame read beside it.
    -- generatedAt is written at emit time, so it IS "now" for this document.
    -- ⚠ THE TWO STAMPS ARE AGED AGAINST DIFFERENT REFERENCES, ON PURPOSE.
    -- generatedAt is aged against the CLOCK: a productions.xml nobody has
    -- regenerated for a week is stale, and a bare time would hide that.
    -- defsAsOf is aged against generatedAt -- the document's own "now" -- because
    -- the fact a player needs there is how much older the DEFINITIONS are than
    -- the savegame read printed beside them.
    local asOf = FarmManager25.stampText(meta.asOfText, nowText)
    local defsAsOf = FarmManager25.stampText(meta.defsAsOfText, meta.asOfText)

    return rows, {
        status        = meta.status or "ok",
        asOfText      = asOf,
        defsAsOfText  = defsAsOf,
        -- The raw stamps, carried but NOT rendered. A reader that needs the
        -- date (a log line, a defect report) must not have to re-parse the
        -- rendered mark to get it back -- and nothing on screen reads these.
        asOfRaw       = meta.asOfText,
        defsAsOfRaw   = meta.defsAsOfText,
        reason        = meta.reason,
        sourceKey     = meta.sourceKey,
    }
end

--- Read the productions document Cyrus published for THIS savegame.
--  Returns (doc, meta). ⛔ Never throws, never returns nil: an absent, corrupt
--  or wrong-savegame document yields an EMPTY doc and a meta that SAYS SO --
--  `status = "unavailable"` -- so the tab can tell "you own no productions"
--  from "we could not ask". Those are different facts and they must not render
--  the same way.
function FarmManager25.readProductionsFile(path, expectedKey)
    local meta = { status = "unavailable", sourceKey = expectedKey }

    if path == nil or not fileExists(path) then
        meta.reason = "notPublished"
        return {}, meta
    end

    local xml = XMLFile.load("FarmManager25Productions", path)
    if xml == nil then
        print("FarmManager25: could not parse " .. tostring(path)
            .. " as XML -- the PRODUCTIONS tab will say so rather than show an "
            .. "empty farm")
        meta.reason = "unreadable"
        return {}, meta
    end

    local doc = {}
    local rejected = nil

    -- Same finally-equivalent shape as readFarmFile: free the handle whether the
    -- body returns or throws. A throw between load and delete must never leak
    -- the engine handle.
    local okRead, errRead = pcall(function()
        -- ⛔ ONE REFUSAL POINT, DELIBERATELY -- readFarmFile's own lesson. These
        -- checks RECORD a rejection and read on; the single gate after the loop
        -- withholds the document. Returning early from here leaves nothing read
        -- at the point of return, so NO mutation of the refusal could change an
        -- answer and the branch that matters most is the one no test can reach.
        --
        -- ⚠ A MISMATCH IS PROOF; ABSENCE IS NOT. A present-and-WRONG attribute
        -- says this document is not ours. A missing one says only that an older
        -- writer produced it, and refusing that would break a working install on
        -- upgrade to buy nothing.
        local schema = xml:getString("farmManager25Productions#schema")
        if schema ~= nil and schema ~= tostring(FarmManager25.PRODUCTIONS_SCHEMA) then
            rejected = "schema " .. tostring(schema) .. ", but this build reads "
                .. tostring(FarmManager25.PRODUCTIONS_SCHEMA)
        end

        local stamped = xml:getString("farmManager25Productions#savegame")
        if rejected == nil and stamped ~= nil and expectedKey ~= nil
                and stamped ~= expectedKey then
            rejected = "stamped for " .. tostring(stamped) .. ", but this is "
                .. tostring(expectedKey)
        end

        meta.asOfText     = xml:getString("farmManager25Productions#generatedAt")
        meta.defsAsOfText = xml:getString("farmManager25Productions#defsAsOf")

        for p = 0, FarmManager25.MAX_POINTS - 1 do
            local pk = string.format("farmManager25Productions.point(%d)", p)
            if not xml:hasProperty(pk) then
                break
            end
            local point = {
                id         = xml:getString(pk .. "#id"),
                name       = xml:getString(pk .. "#name"),
                nameSource = xml:getString(pk .. "#nameSource"),
                inputs = {}, lines = {}, outputs = {},
            }
            for i = 0, FarmManager25.MAX_POINT_ROWS - 1 do
                local k = string.format("%s.input(%d)", pk, i)
                if not xml:hasProperty(k) then break end
                table.insert(point.inputs, {
                    ft           = xml:getString(k .. "#ft"),
                    label        = xml:getString(k .. "#label"),
                    held         = xml:getString(k .. "#held"),
                    perHour      = xml:getString(k .. "#perHour"),
                    hoursToEmpty = xml:getString(k .. "#hoursToEmpty"),
                    rate         = xml:getString(k .. "#rate"),
                    reason       = xml:getString(k .. "#reason"),
                    -- [[DEC-197]]. ⛔ THE DOCUMENT CARRIED THESE AND THIS READER
                    -- DROPPED THEM. The emitter has published `stockState` since
                    -- the TD-139 fix; nothing here lifted it off the document,
                    -- so the ruling could not reach the tab however correctly
                    -- the page rendered it. An attribute nobody parses is
                    -- indistinguishable from an attribute nobody emits, and
                    -- neither says a word in log.txt.
                    stockState   = xml:getString(k .. "#stockState"),
                    stateReason  = xml:getString(k .. "#stateReason"),
                    heldReason   = xml:getString(k .. "#heldReason"),
                })
            end
            for i = 0, FarmManager25.MAX_POINT_ROWS - 1 do
                local k = string.format("%s.line(%d)", pk, i)
                if not xml:hasProperty(k) then break end
                table.insert(point.lines, {
                    id            = xml:getString(k .. "#id"),
                    name          = xml:getString(k .. "#name"),
                    nameSource    = xml:getString(k .. "#nameSource"),
                    enabled       = xml:getString(k .. "#enabled"),
                    outPerHour    = xml:getString(k .. "#outPerHour"),
                    limitingInput = xml:getString(k .. "#limitingInput"),
                    outReason     = xml:getString(k .. "#outReason"),
                })
            end
            for i = 0, FarmManager25.MAX_POINT_ROWS - 1 do
                local k = string.format("%s.output(%d)", pk, i)
                if not xml:hasProperty(k) then break end
                table.insert(point.outputs, {
                    ft             = xml:getString(k .. "#ft"),
                    label          = xml:getString(k .. "#label"),
                    held           = xml:getString(k .. "#held"),
                    capacity       = xml:getString(k .. "#capacity"),
                    capacityReason = xml:getString(k .. "#capacityReason"),
                    -- ⚠ AN OUTPUT ROW CARRIES NO `stockState` AND THAT IS THE
                    -- CONTRACT, NOT AN OMISSION ([[DEC-203]], emitter :1116):
                    -- an output has no urgency to carry, so `held="0.0"` IS the
                    -- measured zero and an ABSENT `held` WITH a `heldReason` is
                    -- the refusal. The two are distinguishable without a third
                    -- attribute. ⛔ So heldReason must be read: it is what tells
                    -- a missing `held` apart from a zero one. It has ZERO live
                    -- instances on savegame1 today, which is not the same as
                    -- absent -- it is still emitted on an unreadable stock index
                    -- or a case-differing spelling.
                    heldReason     = xml:getString(k .. "#heldReason"),
                })
            end
            table.insert(doc, point)
        end
    end)

    local okDel = pcall(function() xml:delete() end)

    if not okRead then
        print("FarmManager25: productions.xml read failed (" .. tostring(errRead)
            .. ") -- the PRODUCTIONS tab will say it could not read the file")
        meta.reason = "unreadable"
        return {}, meta
    end
    if not okDel then
        print("FarmManager25: productions.xml handle could not be released")
    end

    if rejected ~= nil then
        print("FarmManager25: refusing " .. tostring(path) .. " -- " .. rejected
            .. " -- the PRODUCTIONS tab will say so rather than show another "
            .. "savegame's productions")
        meta.reason = "rejected"
        meta.asOfText, meta.defsAsOfText = nil, nil
        return {}, meta
    end

    -- ⭐ THE READ SUCCEEDED. Zero points here is a real answer -- a farm that
    -- owns no production buildings -- and it must NOT be reported as a failure.
    meta.status = "ok"
    return doc, meta
end

--- ⭐ THE PUBLISHED SEAM (D5). The menu calls exactly this and renders what it
--  gets. Rebuilt per call, once per switchTab() into PRODUCTIONS.
--  ⛔ NEVER THROWS. NEVER RETURNS nil. Returns (rows, meta), always both.
function FarmManager25:getProductionRows()
    local doc, meta = {}, { status = "unavailable", reason = "notPublished" }

    if self.saveFolder ~= nil then
        local ok, a, b = pcall(function()
            return FarmManager25.readProductionsFile(
                self.saveFolder .. FarmManager25.PRODUCTIONS_NAME,
                FarmManager25.savegameKey())
        end)
        -- pcall over a function returning two values hands them back in order.
        -- A throw anywhere below leaves the unavailable default standing, which
        -- is the honest answer: we could not ask.
        if ok and type(a) == "table" then
            doc = a
            if type(b) == "table" then meta = b end
        end
    end

    return FarmManager25.buildProductionRows(doc, meta, FarmManager25.nowStamp())
end

-- ---------------------------------------------------------------------------
-- THE FIELDS TABLE -- the SIXTH published seam (item C1/C4/C5, CONTRACT sec. 5.2).
--
-- ⛔ CONTRACT-fields-core-row-2026-09-04.md GOVERNS THIS (DEC-140). Where this
-- and the build spec disagree, the CONTRACT wins.
--
-- ⛔ THE SAME ASSEMBLY vs ACQUISITION SPLIT as FARM and PRODUCTIONS:
--   buildFieldRows()    -- PURE. Zero engine references. Cannot fail: malformed
--                          input yields `unknown` cells, never a throw.
--   readFieldsFile()    -- the FILE boundary. Total; never throws.
--   readLiveContracts() -- the ENGINE boundary, isolated PER MISSION.
--   getFieldRows()      -- the seam, returning (rows, meta).
--
-- ⛔ TWO TRANSPORTS ON ONE ROW, and that is why freshness is per CELL here.
-- name/area/owned are FILE/AS-OF; the contract column is LIVE. A row-level badge
-- would be a false claim about three of its four cells. The three AS-OF columns
-- sit under one `as of` header and the contract cell carries LIVE in-cell --
-- one label, not 104.
-- ---------------------------------------------------------------------------

FarmManager25.FIELDS_NAME   = "fields.xml"
FarmManager25.FIELDS_SCHEMA = 1
FarmManager25.MAX_FIELDS    = 256      -- memory bound, not a screen bound
FarmManager25.MAX_SUBIDS    = 16

--- ⛔ OWNED-ONLY, AND IT IS A NAMED CONSTANT SO THE OWNER CAN FLIP IT IN A LIVE
--  TEST. The seam publishes EVERY row with `owned` on it -- all 104 cross in the
--  file at a measured ~11 KB -- so this is a filter, never a second fetch.
--  His own words scope the tab: "fields is for the users field he owns". 104
--  rows of which 26 are his would bury them.
--  ⚠ NOT A SETTINGS TOGGLE. That would be designing for a preference nobody has
--  stated; this is one constant and one live test.
FarmManager25.FIELDS_OWNED_ONLY = true

--- The seven detail lines of block 1, in render order, with the l10n key the
--  menu resolves. ⛔ DATA, NOT CODE: adding a line is an edit to this table.
--  ⛔ NO ROLLER RUNG AND NO STUBBLE RUNG -- PLAN-FARM-DATA-LAYER sec. 2.2a:376,
--  binding. `rollerLevel` is INVERTED relative to plough and lime and rests on a
--  single witness; `stubbleShredLevel` is ungrounded. Polarity is not uniform
--  across these fields and the inconsistent ones are declared on adjacent lines
--  of the same source, so grounding one and generalising to its neighbour is
--  exactly backwards while looking right in review.
--  ⚠ d3 (harvest ready) IS ABSENT: its only honest source is the foliageState
--  membership test, which the parser reports as unavailable on this install. The
--  ground-type marker rule is REFUTED (12 of 24 positives wrong) and must never
--  be substituted for it.
FarmManager25.FIELD_DETAIL_SPEC = {
    { key = "crop",   labelKey = "fm25_field_d_crop"   },   -- d1
    { key = "growth", labelKey = "fm25_field_d_growth" },   -- d2
    { key = "ground", labelKey = "fm25_field_d_ground" },   -- d4
    { key = "weeds",  labelKey = "fm25_field_d_weeds"  },   -- d5
    { key = "plow",   labelKey = "fm25_field_d_plow"   },   -- d6
    { key = "lime",   labelKey = "fm25_field_d_lime"   },   -- d7
}

--- 30.0626 -> "30.06". Two decimals: the parser resolves to four and the extra
--  two are precision a player cannot act on.
local function formatHa(n)
    return string.format("%.2f", n)
end

--- ⛔ THE MERGED-DISAGREEMENT RULE (CONTRACT sec. 3.3 rules 4-5, sec. 3.4).
--  A merged row reports the AGREEING value, and reports disagreement AS
--  DISAGREEMENT -- ⛔ never by silently picking the canonical sub-id's answer,
--  never by averaging, never by majority vote.
--
--  ⭐ WHY SURFACING IT IS RIGHT RATHER THAN NOISY: the house rule
--  `one_crop_per_combined_field` says a merged field is planted with exactly one
--  crop across all its sub-parcels, never split. So a disagreement MEANS
--  something, and hiding it discards a signal.
--  ⚠ IT IS LIVE TODAY on the one field item 17 names: 45 OAT/7, 46 OAT/7,
--  36 UNKNOWN/0.
--
--  Returns (text, unknown, differs, partsText, parts).
--
--  ⭐ F12: `parts` is the SAME disagreement as a STRUCTURED array,
--  { {sub = 45, value = "OAT"}, ... } (value nil when that sub-parcel did not
--  report). It travels ALONGSIDE `partsText`, never replacing it: partsText is pinned
--  in five test files, and this assembler is deliberately pure -- no g_*, so it CANNOT
--  translate. The RENDER side turns each value into a crop name or a ground label;
--  core keeps publishing the raw token, which is also what the row icon resolves by.
local function agreeOrDiffer(states, key)
    local seen, order = {}, {}
    for _, s in ipairs(states) do
        local v = s[key]
        if seen[v == nil and "\0nil" or v] == nil then
            seen[v == nil and "\0nil" or v] = true
            table.insert(order, v)
        end
    end
    if #order == 0 then
        return nil, true, false, nil
    end
    if #order == 1 then
        -- ⚠ A SINGLE AGREED *ABSENCE* IS STILL UNKNOWN. Every sub-id failing to
        -- report is agreement about nothing.
        if order[1] == nil then
            return nil, true, false, nil
        end
        return tostring(order[1]), false, false, nil
    end
    -- They disagree. Name every sub-id and what it said.
    local parts, structured = {}, {}
    for _, s in ipairs(states) do
        table.insert(parts, tostring(s.sub) .. " " .. tostring(s[key] or "?"))
        table.insert(structured, { sub = s.sub, value = s[key] })
    end
    return nil, false, true, table.concat(parts, "  "), structured
end

--- ⭐ THE PURE ASSEMBLER (CONTRACT sec. 5.2 ①). Arity 3, returns ONE value: the
--  ordered array of rows. ⛔ CANNOT FAIL -- zero engine references above its
--  `end`, which is what makes it lupa-testable with no stub anywhere.
--
--  `merges` is `{ [canonicalId] = { subIds… } }`; nil is treated as `{}`, and
--  ⛔ NO MERGES IS A LEGITIMATE SAVE -- every non-Montana save is exactly that.
function FarmManager25.buildFieldRows(fields, merges, asOfText, nowText)
    fields = fields or {}
    merges = merges or {}
    local rows = {}
    local stamp = FarmManager25.stampText(asOfText, nowText)

    for _, f in ipairs(fields) do
        local subs = merges[f.id] or f.subIds or { f.id }
        local area = tonumber(f.areaHa)
        if area ~= nil and area ~= area then area = nil end

        -- ⛔ owned IS A TRISTATE AND IT MUST STAY ONE. `false` and "we could not
        -- resolve it" are different facts, and defaulting the second to the
        -- first tells the player he owns nothing -- BUG-016's exact shape.
        local owned = nil
        if f.owned == "true" or f.owned == true then
            owned = true
        elseif f.owned == "false" or f.owned == false then
            owned = false
        end

        local row = {
            id       = f.id,
            name     = f.name or ("Field " .. tostring(f.id)),
            subIds   = subs,
            -- ⛔ `merged` IS DERIVED FROM #subIds, NEVER FROM MERGE STATE. Under
            -- that definition the `(n)` marker means exactly "this row sums n
            -- savegame parcels", so an UNMARKED row is a true statement rather
            -- than an omission -- which is what makes the two PLANNED merges
            -- correct as six plain rows.
            merged   = (#subs > 1),
            subCount = #subs,
            areaText    = area ~= nil and formatHa(area) or nil,
            areaUnknown = (area == nil),
            -- The number areaText was rendered from. The FIELDS footer has to
            -- SUM areas, and summing parsed-back display strings would be a
            -- second derivation that could disagree with the first. Set from
            -- the same `area` local as the two fields above, so all three
            -- carry one answer. nil exactly when areaUnknown is true.
            areaHa      = area,
            areaReason  = f.areaReason,
            owned        = owned,
            ownedUnknown = (owned == nil),
            ownedReason  = f.ownedReason,
            -- ⛔ THE CONTRACT CELL STARTS UNKNOWN, NOT EMPTY. readLiveContracts
            -- sets contractKnown; if the engine never answers, every row keeps
            -- `contractKnown = false` and renders `unknown` -- not one row is
            -- silently left with a nil that reads as "no contract".
            contract      = nil,
            hasContract   = false,
            contractKnown = false,
            asOfText      = stamp,
            detail        = {},
        }

        local states = f.states or {}
        for _, spec in ipairs(FarmManager25.FIELD_DETAIL_SPEC) do
            local text, unknown, differs, parts, partsList = agreeOrDiffer(states, spec.key)
            table.insert(row.detail, {
                key = spec.key, labelKey = spec.labelKey,
                text = text, unknown = unknown,
                differs = differs, partsText = parts,
                parts = partsList,
            })
            -- ⛔ THE CROP TOKEN, PUBLISHED SEPARATELY FOR THE ROW ICON
            -- ([[DEC-195]]). `#crop` is a TOKEN, not translated text, which is
            -- exactly why the icon may be resolved from it -- the display
            -- label would not match in another language.
            -- ⛔ SET ONLY WHEN THE PARTS AGREE AND THE ANSWER IS KNOWN. A
            -- merged field whose sub-parcels disagree has no single crop, and
            -- publishing any one of them would put ANOTHER crop's picture on
            -- the row -- which DEC-195 forbids by name. Absent here means the
            -- page draws the dimmed glyph, which is the ruled fallback.
            if spec.key == "crop" and not unknown and not differs then
                row.cropToken = text
            end
        end

        -- d8, PLANNED NEXT CROP, and the field's NOTES: shown exactly as the emitter
        -- published them, never computed here. nil = the document carried no such
        -- element (an older emitter), which the pane words as OUR gap, not as `none`.
        row.plan  = f.plan
        row.notes = f.notes

        table.insert(rows, row)
    end

    return rows
end

--- Read the FIELDS document Cyrus published for THIS savegame (CONTRACT sec. 5.2 ②).
--  Returns `(fields, merges, asOfText)`. ⛔ Total. Never throws. On any failure:
--  `({}, {}, nil)` -- empty, never partial-looking.
function FarmManager25.readFieldsFile(path, expectedKey)
    local fields, merges = {}, {}

    if path == nil or not fileExists(path) then
        return {}, {}, nil
    end

    local xml = XMLFile.load("FarmManager25Fields", path)
    if xml == nil then
        print("FarmManager25: could not parse " .. tostring(path)
            .. " as XML -- the FIELDS tab will say so rather than show an empty farm")
        return {}, {}, nil
    end

    local asOfText, rejected = nil, nil

    local okRead, errRead = pcall(function()
        -- ⛔ ONE REFUSAL POINT. These checks RECORD a rejection and read on; the
        -- gate after the loop withholds the document. An early return leaves
        -- nothing read at the point of return, so NO mutation of the refusal
        -- could change an answer -- the branch that matters most becomes the one
        -- branch no test can reach.
        -- ⚠ A MISMATCH IS PROOF; ABSENCE IS NOT. `savegame` and `schema` are
        -- READ, not merely written: an unread stamp is worse than no stamp,
        -- because it creates the appearance of a check.
        local schema = xml:getString("farmManager25Fields#schema")
        if schema ~= nil and schema ~= tostring(FarmManager25.FIELDS_SCHEMA) then
            rejected = "schema " .. tostring(schema) .. ", but this build reads "
                .. tostring(FarmManager25.FIELDS_SCHEMA)
        end
        local stamped = xml:getString("farmManager25Fields#savegame")
        if rejected == nil and stamped ~= nil and expectedKey ~= nil
                and stamped ~= expectedKey then
            rejected = "stamped for " .. tostring(stamped) .. ", but this is "
                .. tostring(expectedKey)
        end

        asOfText = xml:getString("farmManager25Fields#generatedAt")

        for i = 0, FarmManager25.MAX_FIELDS - 1 do
            local key = string.format("farmManager25Fields.field(%d)", i)
            if not xml:hasProperty(key) then
                break
            end
            local id = tonumber(xml:getString(key .. "#id"))
            if id ~= nil then
                -- ⛔ `subIds` OMITTED MEANS `{id}`, NOT ABSENCE OF DATA. The
                -- writer omits it for a single field and the reader's default is
                -- what keeps the array TOTAL, so no consumer ever handles nil.
                local subs = { id }
                local raw = xml:getString(key .. "#subIds")
                if raw ~= nil then
                    subs = {}
                    for token in tostring(raw):gmatch("%d+") do
                        if #subs < FarmManager25.MAX_SUBIDS then
                            table.insert(subs, tonumber(token))
                        end
                    end
                    if #subs == 0 then subs = { id } end
                    if #subs > 1 then merges[id] = subs end
                end

                local states = {}
                for s = 0, FarmManager25.MAX_SUBIDS - 1 do
                    local sk = string.format("%s.state(%d)", key, s)
                    if not xml:hasProperty(sk) then break end
                    table.insert(states, {
                        sub    = tonumber(xml:getString(sk .. "#sub")),
                        crop   = xml:getString(sk .. "#crop"),
                        growth = xml:getString(sk .. "#growth"),
                        ground = xml:getString(sk .. "#ground"),
                        weeds  = xml:getString(sk .. "#weeds"),
                        plow   = xml:getString(sk .. "#plow"),
                        lime   = xml:getString(sk .. "#lime"),
                    })
                end

                -- ⛔ PLAN AND NOTES, AS PUBLISHED. An element ABSENT from the document is
                -- what an older emitter's file looks like: it stays nil here so the pane can
                -- say "Not available yet." (our gap), never `none` (a statement about the
                -- field). A state this build does not recognise becomes `unknown`.
                local function readFact(tag, known)
                    local fk = key .. "." .. tag
                    if not xml:hasProperty(fk) then return nil end
                    local state = xml:getString(fk .. "#state")
                    local reason = xml:getString(fk .. "#reason")
                    if state == nil or not known[state] then
                        state = "unknown"
                        reason = reason or ("unrecognised " .. tag .. " state")
                    end
                    return {
                        state = state,
                        reason = reason,
                        crop = xml:getString(fk .. "#crop"),
                        window = xml:getString(fk .. "#window"),
                        plannedOn = xml:getString(fk .. "#plannedOn"),
                        text = xml:getString(fk .. "#text"),
                        truncated = xml:getString(fk .. "#truncated") == "true",
                    }
                end
                local planFact = readFact("plan",
                    { reviewed = true, unreviewed = true, none = true, unknown = true })
                local notesFact = readFact("notes",
                    { note = true, none = true, unknown = true })

                table.insert(fields, {
                    id = id,
                    plan = planFact,
                    notes = notesFact,
                    name = xml:getString(key .. "#name"),
                    areaHa = xml:getString(key .. "#areaHa"),
                    owned = xml:getString(key .. "#owned"),
                    areaReason = xml:getString(key .. "#areaReason"),
                    ownedReason = xml:getString(key .. "#ownedReason"),
                    subIds = subs,
                    states = states,
                })
            end
        end
    end)

    local okDel = pcall(function() xml:delete() end)

    if not okRead then
        print("FarmManager25: fields.xml read failed (" .. tostring(errRead)
            .. ") -- the FIELDS tab will say it could not read the file")
        return {}, {}, nil
    end
    if not okDel then
        print("FarmManager25: fields.xml handle could not be released")
    end
    if rejected ~= nil then
        print("FarmManager25: refusing " .. tostring(path) .. " -- " .. rejected
            .. " -- the FIELDS tab will say so rather than show another "
            .. "savegame's fields")
        return {}, {}, nil
    end

    return fields, merges, asOfText
end

--- The ENGINE boundary (CONTRACT sec. 5.2 ③). Mutates `rows` in place, returns them.
--  ⛔ TOTAL, AND ISOLATED PER MISSION. A mission whose getter throws costs only
--  its own contribution.
--  ⚠ NOT THEORETICAL: on savegame3 one thrown getter inside a single enclosing
--  pcall blanked three FARM rows together, and the existence probe
--  `m.getReward ~= nil` could never catch it BECAUSE THE METHOD IS REAL -- it
--  throws instead of returning.
--  ⛔ ON TOTAL FAILURE every row keeps `contractKnown = false`; not one row is
--  left with a nil that a reader could mistake for "no contract".
function FarmManager25.readLiveContracts(rows)
    if type(rows) ~= "table" then
        return rows
    end

    local ok = pcall(function()
        local farmId = g_currentMission ~= nil and g_currentMission:getFarmId() or nil
        if farmId == nil or farmId == 0
                or g_missionManager == nil
                or g_missionManager.getMissionsByFarmId == nil then
            return
        end
        local missions = g_missionManager:getMissionsByFarmId(farmId)
        if type(missions) ~= "table" then
            return
        end

        -- fieldId -> { title, reward } for RUNNING missions only.
        local byField = {}
        -- [[BUG-040]] architect R-3: "no contract" is KNOWN only if EVERY
        -- mission answered getIsRunning with a boolean AND every running
        -- FIELD mission's field resolved. Zero missions is vacuously known.
        -- Owner-approved reading (FS25 ae5b5b7): a running mission with NO
        -- getField (deadwood, destructibleRock, treeTransport -- getField is
        -- defined only on AbstractFieldMission.lua:86) is on no field and is
        -- SKIPPED; one whose getField exists but returns nil or throws still
        -- makes every row without a found contract unknown.
        local allKnown = true
        for _, m in ipairs(missions) do
            -- ⛔⛔ OFFERED IS NOT ACTIVE. getMissionsByFarmId returns
            -- `mission.farmId == nil or mission.farmId == farmId` -- the engine's
            -- own comment is "All missions, but only for active it needs to match
            -- the farm" -- so this list carries OFFERED contracts, which no farm
            -- owns. A column headed "active contract" that rendered every offer
            -- would mark most of the map as under contract. That is why FARM's
            -- d1 had to be relabelled "Contracts offered or active".
            -- ⛔ FILTERED ON getIsRunning(), inside the total pcall shape and
            -- NEVER behind an existence probe.
            -- [[BUG-040]] getIsRunning() returns a BOOLEAN
            -- (AbstractMission.lua:796), so it is read RAW and compared
            -- `== true`; through askMission's tonumber it was nil on every farm.
            local running = FarmManager25.askMissionRaw(m, "getIsRunning")
            if type(running) ~= "boolean" then
                allKnown = false
            elseif running == true and m.getField ~= nil then
                local fieldId = FarmManager25.askMissionFieldId(m)
                if fieldId == nil then
                    -- A running contract we cannot place: its field must not
                    -- read "no contract", and neither may any other.
                    allKnown = false
                else
                    -- ⛔ THE NAME IS getTitle(), the engine's LOCALISED title
                    -- (AbstractMission.lua:868, set from g_i18n in each
                    -- mission's constructor). NOT getTypeName (0 definitions
                    -- in the engine) and NOT m.type.name (the internal save
                    -- key, e.g. "harvestMission").
                    local title = FarmManager25.askMissionRaw(m, "getTitle")
                    if type(title) ~= "string" or title == "" then
                        title = nil
                    end
                    byField[fieldId] = {
                        title = title,
                        reward = FarmManager25.askMission(m, "getReward"),
                    }
                end
            end
        end

        for _, row in ipairs(rows) do
            -- A row with a FOUND contract is known whatever else failed; a row
            -- without one may claim "no contract" only when allKnown.
            row.contractKnown = allKnown
            for _, sub in ipairs(row.subIds or {}) do
                -- ⛔ THE UNION OVER subIds (CONTRACT sec. 3.3 rule 5): a contract
                -- on ANY sub-id is a contract on the row. A harvest mission on
                -- field 36 shows on row #45.
                local hit = byField[sub]
                if hit ~= nil then
                    -- ⛔ TWO FACTS, TWO FIELDS. `hasContract` says a running
                    -- mission was found on this row; `contract` is its NAME.
                    -- Collapsing them would make an unnameable contract render
                    -- identically to no contract at all -- the tab would say
                    -- "no contract" about a field that is under one.
                    row.contractKnown = true
                    row.hasContract = true
                    row.contract = hit.title
                    row.contractReward = hit.reward
                    break
                end
            end
        end
    end)

    if not ok then
        print("FarmManager25: a live contracts lookup failed -- the FIELDS "
            .. "contract column reads 'unknown'")
        for _, row in ipairs(rows) do
            row.contractKnown = false
            row.contract = nil
            row.hasContract = nil
        end
    end
    return rows
end

--- The meta channel. ⛔ `#rows == 0` HAS TWO IRRECONCILABLE MEANINGS and they
--  must not collapse: a farm that genuinely has no fields, and a document we
--  could not read. An empty array alone cannot carry that (DEC-001 at the
--  row-set level), so it needs a channel of its own.
--
--  ⛔ F11 / SEAM-4 (BUG-036): the stamp goes through stampText(), like FARM's
--  and PRODUCTIONS'. It was published raw ("2026-09-07 18:42 UTC"), so a tab
--  eleven days stale showed no age; it now reads "18:42 (11d)". An unreadable
--  stamp becomes nil and the menu prints the word `unknown`.
function FarmManager25.fieldsMeta(fields, asOfText, saveFolder, nowText)
    if saveFolder == nil then
        return { status = "unavailable", reason = "noSaveFolder" }
    end
    if asOfText == nil and (fields == nil or #fields == 0) then
        return { status = "unavailable", reason = "notPublished" }
    end
    return { status = "ok", asOfText = FarmManager25.stampText(asOfText, nowText),
             sourceKey = FarmManager25.savegameKey() }
end

--- ⭐ THE PUBLISHED SEAM (CONTRACT sec. 5.2 ④). Returns (rows, meta), always
--  both. ⛔ Never throws. Never returns nil. Caller:
--  InGameMenuFarmManager25:refreshFieldData() -- and nothing else, ever.
function FarmManager25:getFieldRows()
    local fields, merges, asOfText = {}, {}, nil

    if self.saveFolder ~= nil then
        local ok, a, b, c = pcall(function()
            return FarmManager25.readFieldsFile(
                self.saveFolder .. FarmManager25.FIELDS_NAME,
                FarmManager25.savegameKey())
        end)
        if ok and type(a) == "table" then
            fields = a
            if type(b) == "table" then merges = b end
            asOfText = c
        end
    end

    local nowText = FarmManager25.nowStamp()
    local rows = FarmManager25.buildFieldRows(fields, merges, asOfText, nowText)
    FarmManager25.readLiveContracts(rows)
    return rows, FarmManager25.fieldsMeta(fields, asOfText, self.saveFolder, nowText)
end


--- Open the in-game menu (FM25_TOGGLE_SETTINGS, default Ctrl+Alt+Period), where
--  registerMenuPage has spliced our page in as a tab.
--
--  ⛔ THE GUARD IS DELIBERATELY UNCHANGED. `getIsGuiVisible()` is documented as
--  *"Determine if any menu or dialog is visible"* (Gui.md; its body is
--  `self.currentGui ~= nil or self:getIsDialogVisible()`), so it also blocks the
--  press while the in-game menu is ALREADY open. That is the ruled behaviour,
--  not an oversight: the tab is visible and clickable once the menu is up, so
--  the blocked case has a working route, and narrowing the guard is a change we
--  can make later with no rework.
--
--  ⛔ AND WE DO NOT DEEP-LINK TO OUR TAB. `TabbedMenu:goToPage` is in the corpus
--  with NO Description, and `classify "InGameMenu page registration addPage"`
--  returns exit 1 -- ZERO documented pages. Jumping straight to the page would
--  be a guess dressed as a feature. Open the menu; let the player click.
--
--  The open itself belongs to the GUI lane: InGameMenuFarmManager25.open() shows
--  the menu (Gui:showGui, corpus-documented) and then best-effort selects our
--  tab. It takes no arguments, returns nothing, and is pcall'd on its own side.
--
--  ⛔ ONE CALL, NO MACHINERY AROUND IT. open() may fail to land on our tab --
--  `TabbedMenu:goToPage` is signature-only in the corpus, no Description, so
--  that is unverified in BOTH directions. There is deliberately NO retry, NO
--  fallback page-selection and NO did-it-work check here: the owner's live test
--  is the only authority on whether the tab lands, and apparatus built on an
--  unverified engine call is a guess with moving parts. If it no-ops the page is
--  still one click away on the tab, which is a working route.
--
--  ⚠ The nil check below is NOT a did-it-work check. It is presence-testing OUR
--  OWN module -- absent in a headless test, on a dedicated server, or in a
--  package built without the page file -- and it is the same nil-tolerance
--  registerMenuPage uses. Without it the key would throw into the pcall and
--  print a failure on every press in exactly the contexts where there is no
--  screen to draw on anyway.
function FarmManager25:onToggleSettings()
    local ok, err = pcall(function()
        if g_gui == nil then
            return
        end
        if g_gui:getIsGuiVisible() then
            return
        end
        if InGameMenuFarmManager25 == nil or InGameMenuFarmManager25.open == nil then
            return
        end
        InGameMenuFarmManager25.open()
    end)
    if not ok then
        print("FarmManager25: settings open failed -- " .. tostring(err))
    end
end

--- Register all GLOBAL keybinds (FM25_TOGGLE_OVERLAY, FM25_TOGGLE_CURSOR,
--  FM25_TOGGLE_SETTINGS) so
--  they SURVIVE engine input-context rebuilds -- the S153 live-test root
--  cause. The engine re-runs
--  PlayerInputComponent.registerGlobalPlayerActionEvents on every rebuild and
--  a one-shot registerActionEvent at load is silently discarded with it; the
--  fix is Courseplay's shape (Courseplay.lua:141-152, installed from
--  loadMap->setupGui at Courseplay.lua:111): overwrite the engine pass so our
--  registration is re-applied every time it runs. superFunc FIRST, then ours.
--  The hint text is left visible on purpose (unlike CP, which hides its own).
--
--  Failure/absence costs ONLY the affected key: the overlay stays in whatever
--  mode state.xml loaded, clicks still route off any raised cursor (from the
--  cursor key or AD/CP), nothing latches.
function FarmManager25:installOverlayToggleHook()
    if self.hookInstalled then
        return   -- idempotent across map loads; one wrap, ever
    end
    if PlayerInputComponent == nil or Utils == nil
            or Utils.overwrittenFunction == nil then
        print("FarmManager25: player input surface unavailable -- the overlay mode key is off; the panel stays in its current mode")
        return
    end
    local ok, err = pcall(function()
        PlayerInputComponent.registerGlobalPlayerActionEvents = Utils.overwrittenFunction(
            PlayerInputComponent.registerGlobalPlayerActionEvents,
            function(inputSelf, superFunc, ...)
                if superFunc ~= nil then
                    superFunc(inputSelf, ...)
                end
                local okR, errR = pcall(function()
                    if InputAction ~= nil and InputAction.FM25_TOGGLE_OVERLAY ~= nil then
                        g_inputBinding:registerActionEvent(
                            InputAction.FM25_TOGGLE_OVERLAY, FarmManager25,
                            FarmManager25.onToggleOverlay,
                            false,   -- triggerUp
                            true,    -- triggerDown
                            false,   -- triggerAlways
                            true)    -- startActive
                    end
                end)
                if not okR then
                    print("FarmManager25: toggle registration failed -- the overlay mode key is off this pass; the panel stays in its current mode -- " .. tostring(errR))
                end
                -- Independent of the overlay pcall on purpose: a failure in one
                -- key's registration must not cost the other. Same Courseplay
                -- shape, same trigger flags (down-edge, startActive).
                local okC, errC = pcall(function()
                    if InputAction ~= nil and InputAction.FM25_TOGGLE_CURSOR ~= nil then
                        g_inputBinding:registerActionEvent(
                            InputAction.FM25_TOGGLE_CURSOR, FarmManager25,
                            FarmManager25.onToggleCursor,
                            false,   -- triggerUp
                            true,    -- triggerDown
                            false,   -- triggerAlways
                            true)    -- startActive
                    end
                end)
                if not okC then
                    print("FarmManager25: cursor registration failed -- the cursor key is off this pass; raise the cursor with AutoDrive/Courseplay instead -- " .. tostring(errC))
                end
                -- Independent again: the settings key registers on its own so a
                -- failure in either sibling never costs it. Same down-edge,
                -- startActive flags. Absence costs only the settings key: the
                -- panel + cursor keys keep working, the panel stays tunable via
                -- settings.xml exactly as before.
                local okS, errS = pcall(function()
                    if InputAction ~= nil and InputAction.FM25_TOGGLE_SETTINGS ~= nil then
                        g_inputBinding:registerActionEvent(
                            InputAction.FM25_TOGGLE_SETTINGS, FarmManager25,
                            FarmManager25.onToggleSettings,
                            false,   -- triggerUp
                            true,    -- triggerDown
                            false,   -- triggerAlways
                            true)    -- startActive
                    end
                end)
                if not okS then
                    print("FarmManager25: settings registration failed -- the settings key is off this pass; the panel stays tunable via settings.xml -- " .. tostring(errS))
                end
            end)
    end)
    if ok then
        self.hookInstalled = true
    else
        print("FarmManager25: could not hook player input registration -- the overlay mode key is off -- " .. tostring(err))
    end
end

--- The in-game clock, for card timestamps.
--
--  g_currentMission.environment.dayTime is MILLISECONDS at runtime. Verified,
--  not assumed: EasyDevControls converts hours with `hourToSet * 1000 * 60 * 60`
--  and compares the result directly against environment.dayTime
--  (EasyDevControls.lua:2105-2107).
--
--  TRAP: environment.xml's <dayTime> on disk is MINUTES-of-day (CLAUDE.md, F-002).
--  Same name, different units, different place. Do not carry one over to the other.
--
--  There is no environment.currentMinute -- it does not exist in any installed
--  mod (currentHour has 12 call sites, currentMinute zero), so minutes come from
--  dayTime and nowhere else.
--
--  Farm time, not system time: the player wants to know when this happened ON THE
--  FARM. Returns nil if the clock is unreadable -- the card then shows no
--  timestamp rather than a made-up one.
function FarmManager25.gameClock()
    if g_currentMission == nil or g_currentMission.environment == nil then
        return nil
    end
    local ms = g_currentMission.environment.dayTime
    if type(ms) ~= "number" then
        return nil
    end
    local totalMinutes = math.floor(ms / 60000)
    return string.format("%02d:%02d", math.floor(totalMinutes / 60) % 24, totalMinutes % 60)
end


--- The farm DAY a card was stamped on. Returns a positive integer, or nil when
--  the day cannot be read. Nil is a real answer here and must stay one: the
--  MESSAGES tab groups by day, and a fabricated day would file a card under the
--  wrong heading -- the exact class of lie DEC-001 exists to prevent. A nil day
--  groups under EARLIER, which is where the design already puts every card
--  written before this field existed.
--
--  ⛔ THE FIELD NAME IS NOT ENGINE-ATTESTED, AND THAT IS WHY THIS IS GUARDED.
--  Measured 2026-09-12, four instruments, stated so the next reader does not
--  redo it:
--    - gameSource.zip: `Environment.lua` IS ABSENT from the 951-file subset
--      (only `dataS/scripts/environment/weather/` ships). The three `currentDay`
--      hits in the subset are LOCAL VARIABLES off getDate() in
--      PlayerSystem.lua:185-203 -- real-world date, not farm time. No evidence.
--    - fs25-lookup: the `Environment` CLASS IS NOT IN THE CORPUS AT ALL -- a
--      TOC scan returns only EnvironmentalScoreEvent / RequestEnvironmentalScore
--      Event. Not a query miss; the page does not exist. No evidence.
--    - the game's OWN savegame (read-only): `environment.xml` carries
--      `<currentDay>`, `<currentMonotonicDay>` and `<daysPerPeriod>`. This is
--      the strongest signal we have, and it is still only a signal.
--    - installed mods: FS25_FieldsOfStories reads
--      `environment.currentDayInPeriod` (IAHelper.lua:1222); FS25_Distribution_
--      Redux probes `env.currentDay` DEFENSIVELY through tryCall
--      (SmartDistribution.lua:4336) -- i.e. its author was unsure too.
--
--  ⚠ AND A MATCHING NAME ON DISK DOES NOT PROVE A MATCHING RUNTIME FIELD. This
--  very file already documents the counterexample: `environment.xml`'s
--  `<dayTime>` is MINUTES-of-day on disk while runtime `dayTime` is
--  MILLISECONDS (:3688, F-002). The save above reads `<dayTime>879.458435</>`
--  -- 879 minutes, 14:39 -- which is that trap in the owner's own savegame.
--
--  ⭐ SO: currentMonotonicDay is preferred because grouping wants a counter that
--  never resets; currentDay is the fallback. Whichever resolves, an unreadable
--  day publishes nil. WHICH ONE ACTUALLY RESOLVES IS THE OWNER'S LIVE TEST --
--  no test in this repo asserts it and none can.
function FarmManager25.gameDay()
    if g_currentMission == nil or g_currentMission.environment == nil then
        return nil
    end
    local env = g_currentMission.environment
    local day = env.currentMonotonicDay
    if type(day) ~= "number" then
        day = env.currentDay
    end
    if type(day) ~= "number" then
        return nil
    end
    -- Guard the shape, not just the type: a negative or fractional day would
    -- sort and group wrongly and is not a day we can honestly report.
    day = math.floor(day)
    if day < 0 then
        return nil
    end
    return day
end


function FarmManager25:buildOverlays()
    local ok, err = pcall(function()
        local d = FarmManager25.DESIGN
        -- ⚠ RAW THEME ON PURPOSE, AND IT IS NOT AN OVERSIGHT. This block
        -- reads GEOMETRY only -- panel.insetPx, cardBorderPx and input's
        -- *Px sizes -- and doubles as the load assertion for
        -- FarmManagerTheme.lua. No colour is read here, so there is nothing
        -- to convert; routing it through engineTheme() would only make the
        -- load check depend on the converter it is meant to run before.
        local theme = FarmManager25.THEME
        if theme == nil then
            -- FarmManagerTheme.lua is listed before this file in modDesc;
            -- its absence means a broken package. Fail into the native tier
            -- with a message that names the actual problem.
            error("FarmManager25.THEME missing -- FarmManagerTheme.lua did not load")
        end

        -- px -> normalized, so the panel is the same physical size at any res.
        -- All static metrics are precomputed HERE, once -- draw only walks the
        -- stack's y cursor (card heights are content-driven, so per-card rects
        -- cannot be frame-independent).
        -- LT-7: fold the uniform scale into the pixel unit itself, so every
        -- geometry metric below (panel, padding, glyphs, gaps, banner, reply
        -- bar) scales by the one factor. Ratio uses of pxW/pxH (roundedRect's
        -- cap math) are unaffected -- both scale equally so the ratio is fixed.
        local s = clamp(d.uiScale or 1, 0.4, 1.5)
        self.pxW, self.pxH = getNormalizedScreenValues(1, 1)
        self.pxW           = self.pxW * s
        self.pxH           = self.pxH * s
        self.panelW        = d.panelWidthPx * self.pxW
        self.padX          = d.paddingXPx   * self.pxW
        self.padY          = d.paddingYPx   * self.pxH
        self.cardGlyphW    = d.cardGlyphPx  * self.pxW
        self.cardGlyphH    = d.cardGlyphPx  * self.pxH
        self.iconGlyphW    = d.iconGlyphPx  * self.pxW
        self.iconGlyphH    = d.iconGlyphPx  * self.pxH
        self.cardGap       = d.cardGapPx    * self.pxH
        self.pillGap       = d.pillGapPx    * self.pxH
        self.affordW       = d.affordWidthPx  * self.pxW
        self.affordH       = d.affordHeightPx * self.pxH
        self.affordGap     = d.affordGapPx    * self.pxW
        self.scrollBarW      = d.scrollBarWidthPx * self.pxW
        self.scrollThumbMinH = d.scrollThumbMinPx * self.pxH
        self.scrollGap       = d.scrollGapPx      * self.pxW
        self.scrollHitW      = d.scrollHitWidthPx * self.pxW
        -- Text sizes bypass pxW/pxH (they normalize px directly), so the scale
        -- is applied to the px argument. getNormalizedScreenValues is linear in
        -- px, so this is exactly titleSize*s etc. -- proportions preserved.
        _, self.titleSize  = getNormalizedScreenValues(0, d.titleSizePx * s)
        _, self.bodySize   = getNormalizedScreenValues(0, d.bodySizePx * s)
        _, self.timeSize   = getNormalizedScreenValues(0, d.timeSizePx * s)
        _, self.lineGap    = getNormalizedScreenValues(0, d.lineGapPx * s)
        _, self.titleGap   = getNormalizedScreenValues(0, d.titleGapPx * s)

        -- The backdrop panel and its inset content column.
        self.insetX  = theme.panel.insetPx * self.pxW
        self.insetY  = theme.panel.insetPx * self.pxH
        self.borderW = theme.cardBorderPx  * self.pxW
        self.borderH = theme.cardBorderPx  * self.pxH
        -- The scrollbar's lane (track + gap) is carved out of the content
        -- column permanently -- the stable-gutter rule (BP-070): cards, reply
        -- bar and overflow text share one right edge that never moves when
        -- the scrollbar appears. The banner keeps the full panel width; the
        -- lane exists only beside the scrolling content.
        self.cardW   = self.panelW - self.insetX * 2 - self.scrollBarW - self.scrollGap

        -- Banner height follows the panel width at the art's own aspect
        -- (UV_BANNER's w/h -- both packed slots share it), so the plate is
        -- never stretched.
        local uvB = FarmManager25.UV_BANNER
        self.bannerH = d.panelWidthPx * (uvB[4] / uvB[3]) * self.pxH

        -- The static reply bar.
        local inp = theme.input
        self.inputBarH    = inp.barHeightPx   * self.pxH
        self.inputFieldH  = inp.fieldHeightPx * self.pxH
        self.chatGlyphW   = inp.chatGlyphPx   * self.pxW
        self.chatGlyphH   = inp.chatGlyphPx   * self.pxH
        self.sendBoxW     = inp.sendBoxPx     * self.pxW
        self.sendBoxH     = inp.sendBoxPx     * self.pxH
        self.sendGlyphW   = inp.sendGlyphPx   * self.pxW
        self.sendGlyphH   = inp.sendGlyphPx   * self.pxH
        _, self.placeholderSize = getNormalizedScreenValues(0, inp.placeholderSizePx * s)

        self.panelLeft = d.anchorX - self.panelW
        self.panelTop  = d.anchorY

        -- ONE image overlay, rendered many times per frame at different
        -- positions, sizes, UVs and colours. This is the low-level API and it is
        -- the only one that can draw a STACK: position is an argument to
        -- renderOverlay, so nothing needs Overlay:setPosition (which has no call
        -- site on an Overlay in any shipped mod).
        --
        -- The pattern is Courseplay's, verbatim (CoursePlot.lua:36-37, 138, 194):
        --   id = createImageOverlay(Utils.getFilename('img/x.dds', BASE_DIRECTORY))
        --   setOverlayUVs(id, unpack(GuiUtils.getUVs({x,y,w,h}, {texW,texH})))
        --   setOverlayColor(id, r,g,b,a);  renderOverlay(id, x, y, w, h)
        -- ...and it renders the SAME id repeatedly in a loop, which is exactly
        -- what a stack of cards is.
        local path = Utils.getFilename(FarmManager25.ATLAS_FILE, FarmManager25.MOD_DIR)
        if not fileExists(path) then
            error("atlas missing at " .. tostring(path))
        end
        self.atlasId = createImageOverlay(path)
        if self.atlasId == nil or self.atlasId == 0 then
            error("createImageOverlay returned nothing for " .. tostring(path))
        end
    end)

    if not ok then
        print("FarmManager25: could not build the HUD, falling back to native notifications -- " .. tostring(err))
        self.overlaysOk    = false
        self.useNativeOnly = true
        return
    end
    self.overlaysOk = true
end


--- The savegame this session is playing, as a folder name ("savegame3").
--
--  ⛔ THE BASENAME OF missionInfo.savegameDirectory, not savegameIndex. The two
--  agree on every contiguous set we have observed (six times across three saves,
--  and the game's own log prints "(savegame3)" beside "My game save(3)") -- but a
--  player with savegame1 and savegame20 is untested, and a key that mapped two
--  saves onto one folder would recreate the exact bug this exists to fix. The
--  folder's own name removes the question, and the Python half derives its key
--  from the same fact (Path(config.paths.savegame_dir).name) so the two halves
--  cannot invent different values. Reading a path is not writing to it.
--
--  nil until the game has been saved once -- GIANTS says so in its own words
--  (AISystem.lua:1105: "Savegame directory does not exist yet, please save the
--  game first"), and a multiplayer client on a remote host has no local save at
--  all. Callers SKIP persistence on nil; they must never substitute the root.
--
--  Timing is safe: missionInfo is fully populated before a mod's loadMap is
--  dispatched (PlaceableSystem.lua:760, LoadTrigger.lua:132 both read it during
--  map/placeable loading).
function FarmManager25.savegameKey()
    local mi = g_currentMission ~= nil and g_currentMission.missionInfo or nil
    if mi == nil then
        return nil
    end
    local dir = mi.savegameDirectory
    if dir ~= nil and dir ~= "" then
        -- Trailing separators tolerated; the game writes none
        -- ("C:/Users/.../FarmingSimulator2025/savegame3").
        return dir:match("([^/\\]+)[/\\]*$")
    end
    if mi.savegameIndex ~= nil then
        return "savegame" .. tostring(mi.savegameIndex)
    end
    return nil
end

--- Dispose of the pre-scoping UNSCOPED replies.xml, exactly once.
--
--  <= v3.0.0.0 wrote every reply to modSettings/<MOD>/replies.xml regardless of
--  savegame, and the skill truncates only on ingest -- so acks earned on one farm
--  sat there waiting to be claimed by whichever farm ran the skill next. Now that
--  the skill reads the scoped path, that file is unreachable and would leak
--  forever.
--
--  ⛔ CONSUME AND DISCARD, never ingest. Those entries carry no savegame stamp;
--  handing them to whichever save loads first is the same attribution error that
--  makes migrating the orphaned cards unacceptable. The ids are printed to the
--  log first, so the evidence survives even though the answers do not.
--
--  Delete via getfenv(0) (the consumeBridge lesson: FS25's sandboxed global
--  environment has no deleteFile; the engine's real one does), with the same
--  write-an-empty-document fallback -- kept at the replies root tag so an
--  un-upgraded skill copy reads an empty ledger rather than a parse error.
function FarmManager25.discardLegacyReplies(rootFolder)
    local path = rootFolder .. FarmManager25.REPLIES_NAME
    if not fileExists(path) then
        return
    end
    local ids, hadEntries = {}, false
    pcall(function()
        local xml = XMLFile.load("FarmManager25LegacyReplies", path)
        if xml == nil then
            return
        end
        pcall(function()
            for i = 0, FarmManager25.MAX_REPLIES - 1 do
                local key = string.format("farmManager25Replies.reply(%d)", i)
                if not xml:hasProperty(key) then
                    break
                end
                hadEntries = true
                table.insert(ids, tostring(xml:getString(key .. "#id")))
            end
        end)
        xml:delete()
    end)
    if not hadEntries then
        return
    end
    print(string.format(
        "FarmManager25: discarding %d reply/replies from the pre-scoping (<= v3.0.0.0) unscoped "
        .. "replies.xml -- they cannot be attributed to a savegame, so they are "
        .. "dropped rather than credited to the wrong farm: %s",
        #ids, table.concat(ids, ", ")))
    local ok = pcall(function() getfenv(0).deleteFile(path) end)
    if ok and not fileExists(path) then
        return
    end
    pcall(function()
        local f = io.open(path, "w")
        if f ~= nil then
            f:write("<farmManager25Replies/>")
            f:close()
        end
    end)
end

-- registerSettingsGui was deleted here (Stage 1). It registered the S158 modal
-- dialog, whose files -- FarmManagerSettingsGui.lua, gui/FarmManagerSettingsGui.xml
-- and its modDesc <sourceFile> entry -- no longer exist: the settings now live on
-- the in-game menu page, registered by registerMenuPage() above. Loading a GUI
-- from a path that is not in the package is not a degrade, it is a lie in the log.

--- Register the in-game menu page (Stage 1 seam). The page itself --
--  InGameMenuFarmManager25 -- is the GUI lane's file, sourced at the bottom of
--  this one; this side only calls its register(). pcall'd, so a failure costs
--  the menu page and nothing else.
--
--  ⛔ THE TWO KINDS OF ABSENCE ARE NOT THE SAME THING, and treating them alike
--  is what let a missing source() line ship undetected:
--
--  * `InGameMenuFarmManager25 == nil` -- the file was NEVER LOADED. After the
--    source() call at the bottom of this file that can only mean the page file
--    is missing from the package. ⛔ A PACKAGING BUG, and it is PRINTED. This
--    branch was silent, and silence is exactly how the whole page shipped
--    inert while the log looked healthy.
--  * the table exists but `.register` is nil -- the file LOADED and took its
--    OWN headless guard (`if Class == nil or TabbedMenuFrameElement == nil then
--    return end`), leaving a bare table behind. That is the expected degrade on
--    a dedicated server or under the lupa harness, where there is no screen to
--    draw on. Stays SILENT -- printing here would spam every headless run.
--
--  The distinction is only available BECAUSE the page file guards itself that
--  way; without the source() call above, both cases collapse into "nil" and
--  neither can be told from the other.
function FarmManager25:registerMenuPage()
    if InGameMenuFarmManager25 == nil then
        print("FarmManager25: gui/InGameMenuFarmManager25.lua did not load -- "
            .. "the farm manager menu page is MISSING from this build. The HUD, "
            .. "cards and replies are unaffected; the menu tab will not appear.")
        return
    end
    if InGameMenuFarmManager25.register == nil then
        return   -- loaded, then took its own headless guard: no screen here
    end
    local ok, err = pcall(function()
        InGameMenuFarmManager25.register()
    end)
    if not ok then
        print("FarmManager25: in-game menu page registration failed -- the page is off this session -- " .. tostring(err))
    end
end

function FarmManager25:loadMap(name)
    -- A dedicated server has no screen, so there is nobody to notify. Bail out
    -- entirely: filePath stays nil, so update() returns immediately and we never
    -- poll, never render, never create a folder in a server's profile.
    --
    -- modDesc declares multiplayer supported="true". THIS GUARD is what makes
    -- that claim true rather than merely stated: the mod is client-side only,
    -- each client watches its own local bridge, and the server does nothing.
    -- The idiom is the one every shipped mod uses (AutoDrive: `if
    -- g_dedicatedServer == nil then`). Without it, the claim was unearned
    -- confidence of exactly the kind FRICTION-LOG keeps recording.
    if g_dedicatedServer ~= nil then
        print("FarmManager25: dedicated server detected -- notifier disabled (there is no screen to draw on)")
        return
    end

    -- ⛔ TWO createFolder calls, parent first -- createFolder is NOT mkdir -p.
    -- Courseplay calls it once per level for the same reason (FileSystem.lua:189)
    -- and the game's own log shows the two lines separately. One call to the deep
    -- path may silently no-op, and then every write below fails.
    local folder = getUserProfileAppPath() .. FarmManager25.RELATIVE_FOLDER
    createFolder(folder)

    self.timeSinceCheck = 0
    self.queue          = {}
    self.stack          = {}
    -- Cleared with the stack, and for the same reason: the transcript is THIS
    -- savegame's history and rides the same per-savegame cards.xml. Carrying it
    -- across a map load would show save A's exchanges in save B -- the exact
    -- bleed the per-savegame split was shipped to fix (BUG-027).
    self.retained       = {}
    self.useNativeOnly  = false

    self.interactiveOk      = true
    self.affordanceRects    = nil
    self.inputBarRect       = nil
    self.panelRect          = nil
    FarmManager25.scrollOffset = 0
    -- loadCards populates the stack directly (not via push), so it must not
    -- arm the dirty-flush -- we would re-save what we just read.
    self.stateDirty         = false

    -- The HUD block is machine-global and loads on EVERY savegame, including the
    -- ones with no directory to scope to.
    self.stateFolder = folder
    self:loadSettings(folder)     -- hand-edited seed first...
    self:loadState(folder)        -- ...then the live store wins (position + mode)

    local key = FarmManager25.savegameKey()
    if key == nil then
        -- ⛔ SKIP persistence. Do NOT fall back to `folder`: an unscoped store is
        -- the defect, and two simultaneously-unsaved new games would share it.
        -- Nothing real is lost -- a never-saved game has no careerSavegame.xml, so
        -- no manager can be bound to it in the first place. Say so out loud:
        -- absence must not look like data.
        self.saveFolder = nil
        self.filePath   = nil
        print("FarmManager25: this savegame has no directory yet (a new game not "
            .. "saved once, or a multiplayer client) -- cards and replies are NOT "
            .. "persisted this session, and no manager can be bound to it until "
            .. "you save. The panel still works; nothing is written.")
    else
        self.saveFolder = folder .. key .. "/"
        createFolder(self.saveFolder)      -- second call, child of the first
        self.filePath   = self.saveFolder .. FarmManager25.FILE_NAME
        self:loadCards(self.saveFolder)
        -- One-time: dispose of the pre-scoping shared replies.xml so its
        -- un-ingested acks can never be claimed as this farm's answers.
        FarmManager25.discardLegacyReplies(folder)
    end

    self:buildOverlays()
    self:installOverlayToggleHook()
    self:registerMenuPage()

    if self.filePath ~= nil then
        -- Start from a clean bridge: a message left over from a previous session
        -- is stale by definition and must not pop on load.
        if fileExists(self.filePath) then
            FarmManager25.consumeBridge(self.filePath)
        end
        print(string.format("FarmManager25: watching '%s' (protocol %d, custom HUD %s)",
            self.filePath, FarmManager25.PROTOCOL, self.overlaysOk and "on" or "OFF - native fallback"))
        -- One manager install serves ONE savegame (README: "one manager install
        -- per savegame, in its own directory"), so an EMPTY panel is the CORRECT
        -- state for a savegame nobody has set up a manager for. Unexplained, that
        -- reads as the cards having vanished -- i.e. as a new bug. Say it on the
        -- panel, through the card mechanism the mod already has.
        if #self.stack == 0
                and not fileExists(self.saveFolder .. FarmManager25.CARDS_NAME)
                and not fileExists(self.saveFolder .. FarmManager25.REPLIES_NAME) then
            local n = FarmManager25.buildNotification("info", "FARM MANAGER", nil, {
                "No manager is set up for " .. key .. ".",
                "Each savegame needs its own manager install,",
                "in its own directory -- see the skill README.",
            }, "briefing", nil, nil)
            if n ~= nil then
                -- Inserted the way loadCards does, NOT via push(): this notice is
                -- recomputed every load. `ephemeral` keeps saveCards from writing
                -- it, so it can never become a card that restores itself forever
                -- -- which is the shape of the very bug being fixed here.
                n.ephemeral = true
                table.insert(self.stack, n)
            end
        end
    end
end

function FarmManager25:deleteMap()
    -- Persist the window position and overlay mode (machine-global) plus this
    -- savegame's un-actioned cards on the way out. Both no-op on a nil folder:
    -- the dedicated-server path never got this far, and saveCards additionally
    -- skips a savegame that has no directory to scope to.
    self:saveState()
    self:saveCards()
    -- ...and this savegame's live contract rewards, on the way out. Same no-op
    -- on a nil folder as the two above.
    self:saveContracts()
    -- No manual input teardown here, on purpose: both keybinds
    -- (FM25_TOGGLE_OVERLAY, FM25_TOGGLE_CURSOR) are owned by the
    -- survives-rebuild hook (installOverlayToggleHook, the Courseplay shape)
    -- -- their lifecycle is the engine's global-action rebuild pass, which
    -- clears and re-registers on its own schedule, not loadMap/deleteMap. The
    -- BP-064 leak warning was about the OLD one-shot self-scoped
    -- registerActionEvent, which is gone. The cursor needs no release either:
    -- the mission-end input-context teardown resets it, and FM25_TOGGLE_CURSOR
    -- only flips the shared state the engine already owns.
    self.affordanceRects    = nil
    self.inputBarRect       = nil
    self.panelRect          = nil
    self.scrollbarRect      = nil
    self.scrollThumbRect    = nil
    self.scrollDrag         = nil
    self.stateFolder   = nil
    self.saveFolder    = nil
    self.filePath      = nil
    self.queue         = {}
    self.stack         = {}
    self.retained      = {}
    self.atlasId       = nil
    self.overlaysOk    = false
    self.headerRect    = nil
    self.dragOffset    = nil
end


-- ---------------------------------------------------------------------------
-- update: poll the bridge, advance the active notification
-- ---------------------------------------------------------------------------

function FarmManager25:pollBridge()
    if not fileExists(self.filePath) then
        return
    end

    -- Read via the engine XML API. io.open(path, "r") is NOT an option: FS25
    -- sandboxes io to write-only, returns a table with no read method, and opens
    -- the file for WRITING anyway -- which then blocks our own next open with a
    -- sharing violation. See the header.
    local xml = XMLFile.load("FarmManager25Notify", self.filePath)

    if xml == nil then
        print("FarmManager25: could not parse " .. tostring(self.filePath) .. " as XML -- discarding")
        FarmManager25.consumeBridge(self.filePath)
        return
    end

    local root = "farmManager25.notification"
    local hasNote = xml:hasProperty(root)

    if not hasNote then
        -- A SPENT bridge: <farmManager25/> with nothing in it. Left behind when
        -- deleteFile was refused and we fell back to truncating. Ignore it and
        -- do NOT try to consume it again -- retrying a refused delete every
        -- 200ms is what put 450 engine errors in the log. The sender simply
        -- overwrites this file on its next send.
        xml:delete()
        return
    end

    local notification
    local ok, err = pcall(function()
        local lines = {}
        for i = 0, FarmManager25.MAX_BODY_LINES - 1 do
            local key = string.format("%s.line(%d)", root, i)
            -- hasProperty, not "getString ~= nil". An EMPTY <line/> is a blank
            -- line in the message, and its getString is nil -- so breaking on nil
            -- would silently truncate the body at the first blank line and show a
            -- half message as if it were the whole one. "No such element" and
            -- "element with no text" are two different claims; keep them distinct.
            if not xml:hasProperty(key) then
                break
            end
            table.insert(lines, xml:getString(key) or "")
        end

        -- Protocol 4 <actions>, in its OWN pcall. This outer pcall deliberately
        -- loses the whole card on a throw (exactly one consume attempt, see
        -- below) -- a malformed <actions> block must not ride that path. If
        -- reading actions throws, the card still shows; only the affordances
        -- are dropped.
        local actions = nil
        local okActions, parsedOrErr = pcall(FarmManager25.parseActions, xml, root)
        if okActions then
            actions = parsedOrErr
        else
            print("FarmManager25: malformed <actions> block ignored -- " .. tostring(parsedOrErr))
        end

        notification = FarmManager25.buildNotification(
            xml:getString(root .. "#severity"),
            xml:getString(root .. "#title"),
            xml:getString(root .. "#ttl"),
            lines,
            xml:getString(root .. "#icon"),
            xml:getString(root .. "#id"),
            actions)
    end)

    -- Release the engine's handle BEFORE touching the file on disk.
    xml:delete()

    -- Exactly ONE consume attempt per message, whatever happened above. If the
    -- read threw, the message is lost -- but a wedged bridge would lose every
    -- future one too, and make the sender wait forever for a receipt.
    if not FarmManager25.consumeBridge(self.filePath) then
        print("FarmManager25: WARNING -- could not clear " .. tostring(self.filePath) ..
              "; the sender will not see a delivery receipt")
    end

    if not ok then
        print("FarmManager25: error reading notification -- " .. tostring(err))
        return
    end
    if notification == nil then
        return
    end

    if #self.queue >= FarmManager25.MAX_QUEUE then
        -- Drop the OLDEST, keep the newest: on a farm the latest state is the
        -- one worth reading. Say so rather than dropping silently.
        table.remove(self.queue, 1)
        print("FarmManager25: notification queue full, dropped the oldest message")
    end
    table.insert(self.queue, notification)
end


--- Move a parsed notification onto the visible stack.
-- Retained-card statuses. ⛔ L10N KEYS, NOT TEXT. Every user-visible string in
-- this mod belongs to the translation files (en is authoritative -- the game
-- falls back to it), and getMessageLog is specified as ZERO engine calls, so it
-- cannot resolve these itself: the consuming page must. A prose literal here
-- would be a defect, not a shortcut.
FarmManager25.STATUS_LIVE      = "fm25_status_live"
FarmManager25.STATUS_ANSWERED  = "fm25_status_answered"
FarmManager25.STATUS_DISMISSED = "fm25_status_dismissed"
FarmManager25.STATUS_EXPIRED   = "fm25_status_expired"
FarmManager25.STATUS_EVICTED   = "fm25_status_evicted"
FarmManager25.STATUS_NATIVE    = "fm25_status_native"

--- Move a card OUT of the live stack and INTO the transcript (TECH-DEBT-060).
--  The single place a card may leave `stack` and still exist.
--
--  ⛔ THIS DOES NOT REMOVE FROM THE STACK -- every caller pairs it with its own
--  table.remove. That is deliberate: the four removal sites remove by four
--  different rules (index 1 on overflow, a reverse-walk index on expiry, table
--  IDENTITY on answer, and a whole-stack wipe in the draw latch), so a helper
--  that also removed would have to re-implement all four and would silently pick
--  the wrong card the day a fifth site appears.
--
--  `ephemeral` cards (loadMap's "no manager is set up" notice) are NOT retained:
--  they are recomputed every load and saveCards already refuses to write them, so
--  retaining one would reintroduce the self-restoring-card bug inside the
--  transcript -- the exact shape of the bug the per-savegame split exists to fix.
--
--  A cap of 0 means the player switched retention OFF. Honour it exactly and
--  silently: keeping "just one" would ignore the setting, and printing per card
--  would spam a log the player deliberately turned off.
function FarmManager25:retain(n, status)
    if n == nil or n.ephemeral then
        return
    end
    if FarmManager25.retentionCap <= 0 then
        return
    end
    -- ⛔ `status` is the ONLY thing stored. `answered` is DERIVED from it in
    -- getMessageLog and nowhere else. It used to be stored here too and
    -- recomputed in loadCards -- two fields bearing one answer, of which the
    -- mutation pass could only ever check one: pinning this copy to false left
    -- the entire suite green, because a card that had been through a reload got
    -- its value from the other copy. One source, one thing to get wrong.
    n.status = status
    table.insert(self.retained, n)
    -- Bounded like the live stack, and printed for the same reason: a card that
    -- vanishes with no log trail reads as a sender bug and cost a live yes/no
    -- card once. The transcript exists so that exchange can be reconstructed
    -- afterwards -- dropping from it silently would rebuild the hole it fills.
    while #self.retained > FarmManager25.retentionCap do
        table.remove(self.retained, 1)
        print("FarmManager25: message log full, dropped the oldest retained card")
    end
    -- The transcript rides cards.xml, so a change to it is a change to persist.
    self.stateDirty = true
end

function FarmManager25:push(n)
    if self.useNativeOnly or not self.overlaysOk then
        FarmManager25.showNative(n)   -- the game owns its lifetime, not us
        return
    end

    -- A new card tops up the ones already showing, so the stack reads as a
    -- coherent group instead of older cards blinking out from under a new one
    -- mid-read. Only ever extends -- never cuts a card short.
    for _, old in ipairs(self.stack) do
        local remaining = old.ttl - old.age
        if remaining < FarmManager25.LINGER_MS then
            old.ttl = old.age + FarmManager25.LINGER_MS
        end
    end

    table.insert(self.stack, n)
    -- The STORE bound, not the screen: what fits on screen is renderStack's
    -- fit-window decision. Eviction is printed -- a card that vanishes with
    -- no log trail reads as a sender bug and cost a live yes/no card once.
    while #self.stack > FarmManager25.MAX_STORE do
        local evicted = table.remove(self.stack, 1)   -- oldest off the SCREEN store; the newest is the one that matters
        -- TECH-DEBT-060: off the stack, not out of existence. The wording moved
        -- with the behaviour -- "dropped" was true and is not any more, and a
        -- log line that misdescribes what happened is the failure this print was
        -- added to prevent, not an instance of preventing it.
        self:retain(evicted, FarmManager25.STATUS_EVICTED)
        print("FarmManager25: card store full, oldest card moved to the message log")
    end
    -- LT-8: the stack changed -> the persisted store is stale. Flushed once at
    -- the end of update() so a burst of arrivals coalesces to a single write.
    self.stateDirty = true
    -- S157: a new arrival snaps the scroll window back to the newest. The
    -- newest card is the one that matters -- it must not land hidden behind a
    -- scroll the player left parked on older history.
    FarmManager25.scrollOffset = 0
end

function FarmManager25:update(dt)
    if self.filePath == nil then
        return
    end

    self.timeSinceCheck = self.timeSinceCheck + dt
    if self.timeSinceCheck >= FarmManager25.CHECK_INTERVAL_MS then
        self.timeSinceCheck = 0
        self:pollBridge()
    end

    -- Age the stack. Expiry is OFF-mode-only (overlay ON = the persistent
    -- panel, cards stay until actioned or evicted), and even in OFF mode an
    -- expired ACTION card only stops rendering (alphaOf hits 0) -- it stays
    -- in the store, because an unanswered question must survive the fade and
    -- reappear when the panel is toggled back ON. Plain cards are transient
    -- info and leave for real. (Iterate backwards: removing while walking
    -- forwards skips the next element.)
    for i = #self.stack, 1, -1 do
        local n = self.stack[i]
        n.age = n.age + dt
        if not FarmManager25.overlayOn and n.age >= n.ttl and n.actions == nil then
            table.remove(self.stack, i)
            -- TECH-DEBT-060: an expired transient card is still something the
            -- farm manager said. It leaves the screen; it does not leave history.
            self:retain(n, FarmManager25.STATUS_EXPIRED)
            -- LT-8: state.xml mirrors the live stack -- an OFF-mode expired
            -- transient card must not resurrect on restart.
            self.stateDirty = true
        end
    end

    while #self.queue > 0 do
        self:push(table.remove(self.queue, 1))
    end

    -- LT-8: coalesced persist. Any stack mutation this tick (arrival, eviction,
    -- expiry, and dismiss/answer set from mouseEvent) writes cards.xml exactly
    -- ONCE here, not per-card -- human message cadence, negligible cost, and
    -- never a per-frame write on an idle stack. A stack change does not touch
    -- the HUD block, so this flushes the cards only.
    if self.stateDirty then
        self.stateDirty = false
        self:saveCards()
    end
end


-- ---------------------------------------------------------------------------
-- draw: the panel
-- ---------------------------------------------------------------------------

--- Draw one atlas region. renderOverlay takes x,y as the BOTTOM-LEFT corner.
function FarmManager25:blit(uv, x, y, w, h, c, alpha)
    setOverlayUVs(self.atlasId, unpack(GuiUtils.getUVs(uv, {FarmManager25.ATLAS_W, FarmManager25.ATLAS_H})))
    -- ⛔ THE CONVERSION HAPPENS AT THE SINK, AND THAT IS DELIBERATE. This is
    -- the ONLY setOverlayColor call in the mod, so converting here makes it
    -- impossible for any of the ten blit() call sites to hand the engine a
    -- display-space colour -- the guarantee stops depending on every caller
    -- remembering. Safe because engineColor() is IDEMPOTENT: a caller that
    -- already converted (every THEME path does, via engineTheme()) passes
    -- through untouched, so nothing is double-encoded.
    c = FarmManager25.engineColor(c)
    setOverlayColor(self.atlasId, c[1], c[2], c[3], (c[4] or 1) * alpha)
    renderOverlay(self.atlasId, x, y, w, h)
end

--- A rounded rect of any width, 3-sliced so the corners never smear.
--  The caps are drawn at the graphic's own aspect (CARD_CAP of CARD_PX, scaled to
--  the rect's height); only the middle stretches, and its rows are uniform so the
--  stretch is invisible.
function FarmManager25:roundedRect(uvL, uvM, uvR, x, y, w, h, c, alpha)
    local capW = h * (FarmManager25.CARD_CAP / FarmManager25.CARD_PX) * (self.pxW / self.pxH)
    if capW * 2 > w then
        capW = w * 0.5
    end
    self:blit(uvL, x,            y, capW,          h, c, alpha)
    self:blit(uvM, x + capW,     y, w - capW * 2,  h, c, alpha)
    self:blit(uvR, x + w - capW, y, capW,          h, c, alpha)
end

--- Card height. affordH is the affordance row's height for cards that draw
--  one, absent/0 otherwise -- a protocol-3 card's height is exactly what it
--  was before the interactive layer existed.
function FarmManager25:cardHeight(lines, affordH)
    local h = self.padY * 2 + self.titleSize + self.titleGap
         + #lines * self.bodySize + math.max(0, #lines - 1) * self.lineGap
    -- The glyph sits straight on the card (no icon box); a one-line card must
    -- still be tall enough to hold it.
    h = math.max(h, self.cardGlyphH + self.padY * 2)
    if affordH ~= nil and affordH > 0 then
        h = h + affordH + self.padY
    end
    return h
end

--- The affordance buttons a card earns, or nil only when the interactive
--  layer is latched off (cards then render one-way). Drawn right-to-left, so
--  close/dismiss -- always last here -- lands rightmost. LT-6: every card gets
--  a close X; an action card also gets its answer glyphs, and its X still
--  writes a dismiss reply (O2: the skill learns it was seen-and-cleared),
--  while a passive info card's X is a local clear (no id, no reply). Bounded
--  and deduped: a sender repeating "yesno" six times gets one pair.
function FarmManager25:affordanceButtons(n)
    -- LT-6: EVERY card earns a close/dismiss X, info cards included -- in
    -- persistent (ON) mode a card with no X can never be cleared. Only a
    -- latched-off interactive layer suppresses the row (cards then render
    -- one-way, interactive -> one-way -> native). A passive info card (no
    -- <actions>) yields exactly [close]; its X clears it locally with no reply
    -- (it has no id to correlate one -- see handleAffordanceClick).
    if not self.interactiveOk then
        return nil
    end
    local buttons = {}
    local seen = {}
    -- MAX_ACTIONS - 1: the unconditional close append below takes the last
    -- slot, so the TOTAL row (actions + close) never exceeds MAX_ACTIONS.
    local function add(icon, reply)
        if not seen[reply] and #buttons < FarmManager25.MAX_ACTIONS - 1 then
            seen[reply] = true
            table.insert(buttons, { icon = icon, reply = reply })
        end
    end
    for _, action in ipairs(n.actions or {}) do
        if action.type == "ack" then
            add("check", "ack")
        elseif action.type == "yesno" then
            add("thumb_up", "yes")
            add("thumb_down", "no")
        end
    end
    table.insert(buttons, { icon = "close", reply = "dismiss" })
    return buttons
end

--- Draw a card's affordance row along its bottom edge and record each
--  button's rect for mouseEvent -- the headerRect pattern, per button. Called
--  under its own pcall in drawCard: a throw here costs the interactive layer,
--  never the card.
function FarmManager25:drawAffordances(n, buttons, cardX, cardBottom, alpha)
    local d = FarmManager25.DESIGN
    -- ⛔ engineTheme(), NOT FarmManager25.THEME. The table holds DISPLAY
    -- (sRGB) values and the engine paints in LINEAR; handing it the raw table
    -- renders every colour too bright (+43.9% at placeholder, measured on the
    -- owner's 2026-09-17 screenshots). ONE shared conversion lives in
    -- FarmManagerTheme.lua and the menu calls the same one -- see the seam
    -- note there for why the table itself is never converted in place.
    local theme = FarmManager25.engineTheme()
    local fam = theme.cards[n.severity] or theme.cards[FarmManager25.DEFAULT_SEVERITY]
    local y = cardBottom + self.padY
    local x = cardX + self.cardW - self.padX
    for i = #buttons, 1, -1 do
        local b = buttons[i]
        x = x - self.affordW
        -- No button pill behind the glyph: the mockup's buttons are the bare
        -- circled glyphs (the circles are baked into the owner art). The hit
        -- rect is unchanged -- affordW x affordH, recorded below exactly as
        -- before -- so mouseEvent routing is untouched.
        local glyph = FarmManager25.ICONS[b.icon]
        if glyph == nil then
            error("affordance glyph missing from atlas: " .. tostring(b.icon))
        end
        -- Thumbs are FIXED green/red whatever the card colour; dismiss stays
        -- muted; everything else takes the family accent.
        local tint = fam.accent
        if b.icon == "thumb_up" then
            tint = theme.thumbs.up
        elseif b.icon == "thumb_down" then
            tint = theme.thumbs.down
        elseif b.reply == "dismiss" then
            tint = d.timeColor
        end
        self:blit(glyph,
                  x + (self.affordW - self.iconGlyphW) * 0.5,
                  y + (self.affordH - self.iconGlyphH) * 0.5,
                  self.iconGlyphW, self.iconGlyphH,
                  tint, alpha)
        table.insert(self.affordanceRects, {
            x = x, y = y, w = self.affordW, h = self.affordH,
            id = n.id, reply = b.reply,
            card = n,   -- identity of the drawn card, for exact removal
        })
        x = x - self.affordGap
    end
end

--- Wrap + cache a card's body lines. Wrapping calls getTextWidth, which is only
--  meaningful once the font size is set, so it is done in draw and cached per
--  notification rather than at parse time.
function FarmManager25:linesFor(n)
    if n.lines == nil then
        setTextBold(false)
        local textW = self.cardW - self.cardGlyphW - self.padX * 3
        n.lines = self:wrapText(n.body, self.bodySize, textW)
    end
    return n.lines
end

function FarmManager25:drawCard(n, top, alpha)
    local d = FarmManager25.DESIGN
    -- ⛔ engineTheme(), NOT FarmManager25.THEME. The table holds DISPLAY
    -- (sRGB) values and the engine paints in LINEAR; handing it the raw table
    -- renders every colour too bright (+43.9% at placeholder, measured on the
    -- owner's 2026-09-17 screenshots). ONE shared conversion lives in
    -- FarmManagerTheme.lua and the menu calls the same one -- see the seam
    -- note there for why the table itself is never converted in place.
    local theme = FarmManager25.engineTheme()
    local sev = FarmManager25.SEVERITIES[n.severity] or FarmManager25.SEVERITIES[FarmManager25.DEFAULT_SEVERITY]
    local fam = theme.cards[n.severity] or theme.cards[FarmManager25.DEFAULT_SEVERITY]
    local lines = self:linesFor(n)
    local buttons = self:affordanceButtons(n)
    local h = self:cardHeight(lines, buttons ~= nil and self.affordH or 0)
    local x = self.panelLeft + self.insetX

    -- card body: bright border ring, then the family bg inset by the border
    self:roundedRect(FarmManager25.UV_CARD_L, FarmManager25.UV_CARD_M, FarmManager25.UV_CARD_R,
                     x, top - h, self.cardW, h, fam.border, alpha * d.cardAlpha)
    self:roundedRect(FarmManager25.UV_CARD_L, FarmManager25.UV_CARD_M, FarmManager25.UV_CARD_R,
                     x + self.borderW, top - h + self.borderH,
                     self.cardW - self.borderW * 2, h - self.borderH * 2,
                     fam.bg, alpha * d.cardAlpha)

    -- the glyph sits straight on the card bg (no icon box), accent-tinted
    local gX = x + self.padX
    local gY = top - self.padY - self.cardGlyphH
    local glyph = FarmManager25.ICONS[n.icon] or FarmManager25.ICONS[sev.icon] or FarmManager25.ICONS.leaf
    self:blit(glyph, gX, gY, self.cardGlyphW, self.cardGlyphH, fam.accent, alpha)

    local textX = gX + self.cardGlyphW + self.padX
    local y = top - self.padY - self.titleSize

    -- title: white + bold (the mockup's look; the colour lives in the border,
    -- bg, glyph and timestamp)
    setTextAlignment(RenderText.ALIGN_LEFT)
    setTextBold(true)
    setTextColor(theme.text.title[1], theme.text.title[2], theme.text.title[3], alpha)
    -- The title is a single-line header (cardHeight budgets exactly one
    -- titleSize -- see there), so it is truncated, not wrapped: an unclamped
    -- title ran straight through the fixed-position timestamp and off the
    -- card's right edge. Budget = the body's text column (cardW - 3*padX -
    -- cardGlyphW, the linesFor textW) minus room for the right-aligned stamp
    -- when present -- its rendered width plus a padX gutter -- so title and
    -- stamp can never collide; no stamp -> the full column. (The stamp is
    -- measured under the title's bold state, which over-reserves a hair versus
    -- its non-bold render -- the safe direction: the title truncates a touch
    -- sooner, never overlaps.) ellipsize reuses wrapText's measure-and-trim.
    local titleW = self.cardW - self.cardGlyphW - self.padX * 3
    if n.stamp ~= nil then
        titleW = titleW - getTextWidth(self.timeSize, n.stamp) - self.padX
    end
    renderText(textX, y, self.titleSize, FarmManager25.ellipsize(n.title, self.titleSize, titleW))

    -- timestamp, right-aligned, in the family accent. Absent if the clock was
    -- unreadable -- better a card with no time than a card with an invented one.
    if n.stamp ~= nil then
        setTextBold(false)
        setTextAlignment(RenderText.ALIGN_RIGHT)
        setTextColor(fam.accent[1], fam.accent[2], fam.accent[3], alpha * 0.9)
        renderText(x + self.cardW - self.padX, y, self.timeSize, n.stamp)
        setTextAlignment(RenderText.ALIGN_LEFT)
    end

    -- body, in the theme's sampled body white
    setTextBold(false)
    setTextColor(theme.text.body[1], theme.text.body[2], theme.text.body[3], alpha)
    y = y - self.titleGap
    for _, line in ipairs(lines) do
        y = y - self.bodySize
        renderText(textX, y, self.bodySize, line)
        y = y - self.lineGap
    end

    -- Affordance row, in its OWN pcall (the parseActions discipline, extended
    -- to draw): a throw here latches the interactive layer off and the card
    -- keeps rendering one-way -- interactive -> one-way -> native.
    if buttons ~= nil then
        local okA, errA = pcall(function()
            self:drawAffordances(n, buttons, x, top - h, alpha)
        end)
        if not okA then
            self.interactiveOk = false
            print("FarmManager25: affordance draw failed -- interactive layer disabled, cards stay one-way -- " .. tostring(errA))
        end
    end

    return h
end

function FarmManager25:drawBanner(top, alpha)
    -- ⛔ engineTheme(), NOT FarmManager25.THEME. The table holds DISPLAY
    -- (sRGB) values and the engine paints in LINEAR; handing it the raw table
    -- renders every colour too bright (+43.9% at placeholder, measured on the
    -- owner's 2026-09-17 screenshots). ONE shared conversion lives in
    -- FarmManagerTheme.lua and the menu calls the same one -- see the seam
    -- note there for why the table itself is never converted in place.
    local theme = FarmManager25.engineTheme()
    local x = self.panelLeft
    -- The banner is the drag handle (the drawPill contract, bigger art). Its
    -- rect is recorded every drawn frame in the same normalized space
    -- mouseEvent receives, and nil'd on every path that does NOT draw it --
    -- an invisible header must not be grabbable.
    self.headerRect = { x = x, y = top - self.bannerH, w = self.panelW, h = self.bannerH }
    -- Owner art: plate, leaf badge and title are baked into the texture, so
    -- this is a single blit -- no renderText, nothing to compose.
    -- Two packed sizes (task103-item14, BP-070 R4): with no mipmaps, detailed
    -- colour art aliases past ~2x minification, so the atlas carries a
    -- pre-downsampled small slot next to the full one. Pick the smallest slot
    -- that still covers this frame's actual pixel width (panelW is normalized
    -- against screen width) -- never upscaling, never over-minifying. Both
    -- slots share the plate's aspect, so bannerH holds for either.
    local uvB = FarmManager25.UV_BANNER
    if self.panelW * (g_screenWidth or 1920) <= FarmManager25.UV_BANNER_SM[3] then
        uvB = FarmManager25.UV_BANNER_SM
    end
    self:blit(uvB, x, top - self.bannerH, self.panelW, self.bannerH,
              theme.header.tint, alpha)
    return self.bannerH
end

--- The reply bar: chat glyph, a darker placeholder field, a green send
--  button. Its rect is recorded each drawn frame (the headerRect
--  discipline) -- a cursor-gated click on it opens the free-text reply
--  dialog (LT-4). Draws at the stack's bottom and fades with the same peak
--  alpha.
function FarmManager25:drawInputBar(top, alpha)
    -- ⛔ engineTheme(), NOT FarmManager25.THEME. The table holds DISPLAY
    -- (sRGB) values and the engine paints in LINEAR; handing it the raw table
    -- renders every colour too bright (+43.9% at placeholder, measured on the
    -- owner's 2026-09-17 screenshots). ONE shared conversion lives in
    -- FarmManagerTheme.lua and the menu calls the same one -- see the seam
    -- note there for why the table itself is never converted in place.
    local theme = FarmManager25.engineTheme()
    local inp = theme.input
    local x = self.panelLeft + self.insetX
    local barTop = top
    local barBottom = barTop - self.inputBarH
    self.inputBarRect = { x = x, y = barBottom, w = self.cardW, h = self.inputBarH }

    -- bar
    self:roundedRect(FarmManager25.UV_CARD_L, FarmManager25.UV_CARD_M, FarmManager25.UV_CARD_R,
                     x, barBottom, self.cardW, self.inputBarH, inp.bg, alpha)

    -- chat glyph, left, vertically centred
    local cy = barBottom + (self.inputBarH - self.chatGlyphH) * 0.5
    self:blit(FarmManager25.ICONS.chat, x + self.padX, cy,
              self.chatGlyphW, self.chatGlyphH, inp.chatTint, alpha)

    -- send button, right: green rounded box + arrow glyph
    local sbX = x + self.cardW - self.padX - self.sendBoxW
    local sbY = barBottom + (self.inputBarH - self.sendBoxH) * 0.5
    self:roundedRect(FarmManager25.UV_CARD_L, FarmManager25.UV_CARD_M, FarmManager25.UV_CARD_R,
                     sbX, sbY, self.sendBoxW, self.sendBoxH, inp.sendBorder, alpha)
    self:roundedRect(FarmManager25.UV_CARD_L, FarmManager25.UV_CARD_M, FarmManager25.UV_CARD_R,
                     sbX + self.borderW, sbY + self.borderH,
                     self.sendBoxW - self.borderW * 2, self.sendBoxH - self.borderH * 2,
                     inp.sendBg, alpha)
    self:blit(FarmManager25.ICONS.send,
              sbX + (self.sendBoxW - self.sendGlyphW) * 0.5,
              sbY + (self.sendBoxH - self.sendGlyphH) * 0.5,
              self.sendGlyphW, self.sendGlyphH, inp.sendTint, alpha)

    -- placeholder field between the two, with its own subtle border
    local fX = x + self.padX * 2 + self.chatGlyphW
    local fW = sbX - self.padX - fX
    local fY = barBottom + (self.inputBarH - self.inputFieldH) * 0.5
    self:roundedRect(FarmManager25.UV_PILL_L, FarmManager25.UV_PILL_M, FarmManager25.UV_PILL_R,
                     fX, fY, fW, self.inputFieldH, inp.fieldBorder, alpha)
    self:roundedRect(FarmManager25.UV_PILL_L, FarmManager25.UV_PILL_M, FarmManager25.UV_PILL_R,
                     fX + self.borderW * 0.5, fY + self.borderH * 0.5,
                     fW - self.borderW, self.inputFieldH - self.borderH,
                     inp.fieldBg, alpha)
    setTextAlignment(RenderText.ALIGN_LEFT)
    setTextBold(false)
    setTextColor(theme.text.placeholder[1], theme.text.placeholder[2],
                 theme.text.placeholder[3], alpha)
    renderText(fX + self.padX,
               fY + (self.inputFieldH - self.placeholderSize) * 0.5 + self.placeholderSize * 0.12,
               self.placeholderSize, inp.placeholderText)

    return self.inputBarH
end

function FarmManager25:renderStack()
    local top = self.panelTop

    -- OFF mode: the header is as visible as the most-visible card, so it
    -- fades WITH the stack instead of hanging around over nothing. ON mode:
    -- the panel is a persistent fixture -- full alpha, cards or not.
    local peak = 0
    for _, n in ipairs(self.stack) do
        peak = math.max(peak, FarmManager25.alphaOf(n))
    end
    if FarmManager25.overlayOn then
        peak = 1
    elseif peak <= 0 then
        self.headerRect = nil
        self.affordanceRects = nil
        self.inputBarRect = nil
        self.panelRect = nil
        self.scrollbarRect = nil
        self.scrollThumbRect = nil
        return
    end

    -- The window is bounded by TWO budgets, and the smaller wins.
    --
    -- screenBudget is the LT-5 guard, unchanged in intent: never draw a card
    -- (or the reply bar) below the screen edge. Both overflow lines ("+N more"
    -- older, "N newer" when scrolled) have their height reserved here so
    -- showing one never causes the overflow it reports.
    --
    -- capBudget (S157) is the owner ask: cap the window at a FIXED ~4 cards'
    -- worth of height, NOT "whatever is left down to the screen bottom". The
    -- old code used screenBudget alone, so 8 modest cards legitimately filled
    -- ~80% of the screen before the old single "+N more" ever engaged. The cap
    -- is measured, not a hard count: a representative card is a 2-line body
    -- plus the universal dismiss affordance row every card carries since LT-6
    -- (a row-less baseline would over-estimate a real card and let ~5 show),
    -- sized through the SAME cardHeight helper the real cards use so the two
    -- can never drift.
    local moreH = self.timeSize + self.cardGap
    local screenBudget = top - (self.bannerH + self.pillGap + self.inputBarH
                                + self.insetY + moreH * 2 + 0.01)
    local sampleLines = { "", "" }
    local avgCardH = self:cardHeight(sampleLines, self.interactiveOk and self.affordH or 0)
    local capBudget = FarmManager25.DESIGN.maxVisibleCards * (avgCardH + self.cardGap)
    local budget = math.min(screenBudget, capBudget)

    -- Clamp the scroll offset to a FULL last page (total - the ACTUAL last-page
    -- fit): scrolling only exists when more cards live than the window fits, and
    -- the furthest scroll still fills the window from the oldest card. Written
    -- back so a burst of wheel ticks past the end cannot accumulate forever.
    local totalVisible = 0
    for _, n in ipairs(self.stack) do
        if FarmManager25.alphaOf(n) > 0 then
            totalVisible = totalVisible + 1
        end
    end
    -- The last page is measured, not counted: card heights vary and the window
    -- is a height budget, not a fixed count, so fill `budget` from the OLDEST
    -- card with the SAME rule the window loop below uses and take that count.
    -- (Using maxVisibleCards here was the item-14 regression -- when the screen,
    -- or a tall card, fits fewer than the cap, total - cap fell to 0, so the
    -- offset clamped dead and the scrollbar never drew even though the fit-
    -- derived "+N more" reported real overflow.) First-card-always-counts on
    -- both sides, so the oldest-anchored fit and the newest-anchored window
    -- agree for any height mix.
    local lastPageFit = 0
    local lastPageH = 0
    for i = 1, #self.stack do
        local n = self.stack[i]
        if FarmManager25.alphaOf(n) > 0 then
            local lines = self:linesFor(n)
            local buttons = self:affordanceButtons(n)
            local h = self:cardHeight(lines, buttons ~= nil and self.affordH or 0)
            if lastPageFit > 0 and lastPageH + h + self.cardGap > budget then
                break
            end
            lastPageFit = lastPageFit + 1
            lastPageH = lastPageH + h + self.cardGap
        end
    end
    local scrollMax = math.max(0, totalVisible - lastPageFit)
    FarmManager25.scrollOffset = clamp(FarmManager25.scrollOffset, 0, scrollMax)
    local offset = FarmManager25.scrollOffset

    -- Walk NEWEST-first. Skip `offset` newest cards (scrolled past -> counted
    -- as hiddenNewer), fill the budget from there toward older, and count
    -- everything older than the window as hiddenOlder. The window is thus a
    -- contiguous slice anchored `offset` cards back from the newest.
    local newestFirst = {}
    local cardsH = 0
    local hiddenNewer = 0
    local hiddenOlder = 0
    local seen = 0
    for i = #self.stack, 1, -1 do
        local n = self.stack[i]
        local a = FarmManager25.alphaOf(n)
        if a > 0 then
            seen = seen + 1
            if seen <= offset then
                hiddenNewer = hiddenNewer + 1
            elseif hiddenOlder > 0 then
                hiddenOlder = hiddenOlder + 1   -- window already closed below
            else
                local lines = self:linesFor(n)
                local buttons = self:affordanceButtons(n)
                local h = self:cardHeight(lines, buttons ~= nil and self.affordH or 0)
                if #newestFirst > 0 and cardsH + h + self.cardGap > budget then
                    hiddenOlder = 1
                else
                    table.insert(newestFirst, { n = n, a = a })
                    cardsH = cardsH + h + self.cardGap
                end
            end
        end
    end
    local visible = {}
    for i = #newestFirst, 1, -1 do
        table.insert(visible, newestFirst[i])   -- back to oldest-first for drawing
    end

    -- No shared backdrop panel (S157): it reused the CARD 3-slice atlas
    -- graphic -- baked for a card's ~56px height -- stretched to the panel's
    -- whole (card-count-dependent) height, so its corner radius distorted at
    -- heights far from the design. Every card, the banner and the reply bar
    -- draw their own correctly-proportioned backgrounds, so nothing here
    -- depended on it for grouping.

    -- Rebuilt from scratch every drawn frame -- a rect from a frame that no
    -- longer exists must not take a click.
    self.affordanceRects = {}

    top = top - self:drawBanner(top, peak) - self.pillGap

    -- The scroll viewport's top edge (just under the banner). The scrollbar
    -- track spans from here down to the reply-bar top (viewBottom, below).
    local viewTop = top

    -- The older-overflow line sits where the hidden (oldest) cards would begin
    -- -- at the top, above the visible slice.
    if hiddenOlder > 0 then
        setTextAlignment(RenderText.ALIGN_RIGHT)
        setTextBold(false)
        local c = FarmManager25.engineColor(FarmManager25.DESIGN.timeColor)   -- DEC-216
        setTextColor(c[1], c[2], c[3], peak)
        renderText(self.panelLeft + self.insetX + self.cardW - self.padX,
                   top - self.timeSize, self.timeSize,
                   string.format("+%d more", hiddenOlder))
        setTextAlignment(RenderText.ALIGN_LEFT)
        top = top - moreH
    end

    -- Oldest first, top-down: the newest card lands nearest the player's eye and
    -- the times read downward, like a transcript.
    for _, v in ipairs(visible) do
        top = top - self:drawCard(v.n, top, v.a) - self.cardGap
    end

    -- The newer-overflow hint sits just above the reply bar (the newest cards
    -- live at the bottom): a scroll-up has hidden newer cards below, and the
    -- player can wheel back down to them.
    if hiddenNewer > 0 then
        setTextAlignment(RenderText.ALIGN_RIGHT)
        setTextBold(false)
        local c = FarmManager25.engineColor(FarmManager25.DESIGN.timeColor)   -- DEC-216
        setTextColor(c[1], c[2], c[3], peak)
        renderText(self.panelLeft + self.insetX + self.cardW - self.padX,
                   top - self.timeSize, self.timeSize,
                   string.format("%d newer", hiddenNewer))
        setTextAlignment(RenderText.ALIGN_LEFT)
        top = top - moreH
    end

    -- The scroll viewport's bottom edge (the reply-bar top), captured before
    -- the reply bar consumes `top`.
    local viewBottom = top

    -- The reply bar closes the panel, fading with the stack in OFF mode.
    self:drawInputBar(top, peak)

    -- The whole-panel bounds for the wheel-scroll hit-test (the headerRect
    -- discipline): from the top anchor down to the reply bar's bottom, nil on
    -- every path that does not draw. inputBarRect was just recorded by
    -- drawInputBar, so its bottom is this frame's true panel floor.
    self.panelRect = {
        x = self.panelLeft,
        y = self.inputBarRect.y,
        w = self.panelW,
        h = self.panelTop - self.inputBarRect.y,
    }

    -- Scrollbar (item 18): a click/drag affordance for the card window, drawn
    -- only when there is something to scroll (scrollMax > 0). The track spans
    -- the card viewport (banner bottom -> reply-bar top) at the panel's right
    -- inset; the thumb's height is the visible fraction (on-screen cards /
    -- total) and its Y maps the offset -- offset 0 (newest) parks the thumb at
    -- the BOTTOM, by the reply bar, matching the newest-at-bottom card order.
    -- Rides the button path in mouseEvent, so it scrolls with zero camera
    -- movement (unlike the wheel). Same nil-on-every-undrawn-path discipline as
    -- panelRect. scrollTravel/scrollRange hand the drag its render-time geometry.
    if scrollMax > 0 and self.scrollBarW ~= nil and viewTop - viewBottom > 0 then
        local d = FarmManager25.DESIGN
        local trackH = viewTop - viewBottom
        local trackX = self.panelLeft + self.panelW - self.insetX - self.scrollBarW
        local frac = #visible / totalVisible
        if frac > 1 then frac = 1 end
        local thumbH = math.max(self.scrollThumbMinH, trackH * frac)
        if thumbH > trackH then thumbH = trackH end
        local travel = trackH - thumbH
        local thumbY = viewBottom + (offset / scrollMax) * travel
        self:blit(FarmManager25.UV_CARD_M, trackX, viewBottom, self.scrollBarW, trackH,
                  d.scrollTrackColor, peak)
        self:blit(FarmManager25.UV_CARD_M, trackX, thumbY, self.scrollBarW, thumbH,
                  d.scrollThumbColor, peak)
        -- Hit rects are WIDER than the 4px visual track (BP-070: 12-16 ref-px
        -- minimum click target), centred on it. The extra width lands in the
        -- reserved gap and the panel inset -- never over card content. The
        -- drag math reads only y/h, so widening x/w is safe.
        local hitPad = (self.scrollHitW - self.scrollBarW) * 0.5
        self.scrollbarRect   = { x = trackX - hitPad, y = viewBottom, w = self.scrollHitW, h = trackH }
        self.scrollThumbRect = { x = trackX - hitPad, y = thumbY, w = self.scrollHitW, h = thumbH }
        self.scrollTravel    = travel
        self.scrollRange     = scrollMax
    else
        self.scrollbarRect   = nil
        self.scrollThumbRect = nil
    end

    -- Leave global text state as we found it: FS renders text globally and a
    -- leaked colour/bold/alignment would tint every HUD drawn after us this frame.
    setTextBold(false)
    setTextColor(1, 1, 1, 1)
    setTextAlignment(RenderText.ALIGN_LEFT)
end

function FarmManager25.alphaOf(n)
    -- Settings row 9, the minimum severity shown. Gated HERE because renderStack
    -- already routes EVERY visibility decision it makes through alphaOf > 0 --
    -- the peak/header fade, the scroll clamp, the fit window and both overflow
    -- counters. One gate keeps them all consistent; a filter bolted onto the
    -- draw loop alone would have left the counters reporting cards nobody can
    -- see. Rank 0 = a severity we do not know, and an unrankable card is SHOWN,
    -- never hidden (see severityRank).
    local rank = FarmManager25.severityRank(n.severity)
    if rank > 0 and rank < FarmManager25.severityRank(FarmManager25.minSeverity) then
        return 0
    end
    if n.age < FarmManager25.FADE_IN_MS then
        return n.age / FarmManager25.FADE_IN_MS
    end
    -- ttl only means anything in OFF mode: the persistent panel neither
    -- fades nor expires its cards (an action card whose age has sailed past
    -- its ttl in OFF mode comes back at full alpha when toggled ON).
    if not FarmManager25.overlayOn and n.age > n.ttl - FarmManager25.FADE_OUT_MS then
        return math.max(0, (n.ttl - n.age) / FarmManager25.FADE_OUT_MS)
    end
    return 1
end

function FarmManager25:draw()
    -- The persistent panel (overlay ON) draws even with an empty stack --
    -- header and reply bar are the fixture the owner asked for; only OFF
    -- mode disappears between cards.
    if self.useNativeOnly or not self.overlaysOk
            or (#self.stack == 0 and not FarmManager25.overlayOn) then
        self.headerRect = nil
        self.affordanceRects = nil
        self.inputBarRect = nil
        self.panelRect = nil
        self.scrollbarRect = nil
        self.scrollThumbRect = nil
        return
    end

    local ok, err = pcall(function() self:renderStack() end)
    if not ok then
        -- Latch to native for the session and re-show what is live there. Never
        -- let a draw failure eat a notification: the operator would keep sending
        -- into a void believing they had landed.
        print("FarmManager25: HUD draw failed, latching to native notifications -- " .. tostring(err))
        self.useNativeOnly = true
        self.headerRect    = nil
        self.affordanceRects = nil
        self.inputBarRect  = nil
        self.panelRect     = nil
        self.scrollbarRect = nil
        self.scrollThumbRect = nil
        setTextBold(false)
        setTextColor(1, 1, 1, 1)
        setTextAlignment(RenderText.ALIGN_LEFT)
        if g_currentMission ~= nil then
            for _, n in ipairs(self.stack) do
                FarmManager25.showNative(n)
            end
        end
        -- ⚠ THE FOURTH REMOVAL SITE, and the one that loses most: the WHOLE
        -- stack is wiped here. The cards are re-shown natively once and the game
        -- owns their lifetime from then on, so without this the mod -- again,
        -- the only component that ever held their text -- discards every live
        -- card on the single path where something has already gone wrong.
        -- Retained OUTSIDE the g_currentMission guard above: whether the native
        -- tier could re-show them has no bearing on whether they happened.
        for _, n in ipairs(self.stack) do
            self:retain(n, FarmManager25.STATUS_NATIVE)
        end
        self.stack = {}
    end
end


-- ---------------------------------------------------------------------------
-- input: affordance clicks + drag the window by its header
-- ---------------------------------------------------------------------------

--- Engine-delivered mouse events (the addModEventListener contract; posX/posY
--  are normalized 0..1 -- the same space the panel geometry lives in). Two
--  jobs: affordance clicks and header drag, both gated on the ENGINE's shared
--  cursor state (cursorIsShown) -- without a cursor on screen the coordinates
--  aren't player-aimed and nothing may route.
--
--  The whole body is pcall-wrapped: an input handler that throws must never
--  take the frame down (the buildOverlays/draw discipline, extended to input).
--  On a throw the drag is abandoned and nothing latches -- losing a drag is
--  nothing, losing the notifier is everything.
--- A left-release over an affordance button (AABB, the AutoDrive hit()
--  bounds math). Routed on RELEASE to avoid double-fires, only while the
--  engine cursor is shown, never mid-drag. On a recorded reply the card
--  leaves the stack; on a failed
--  write it STAYS -- the action did not take, and the player can re-click.
--  Returns true when the click hit a button (so the drag path never sees it).
function FarmManager25:handleAffordanceClick(posX, posY)
    if self.affordanceRects == nil then
        return false
    end
    for _, r in ipairs(self.affordanceRects) do
        if posX >= r.x and posX <= r.x + r.w
                and posY >= r.y and posY <= r.y + r.h then
            -- LT-6: a passive info card's X carries no id -- it has no
            -- correlation key, so a reply would reference nothing. Clear it
            -- LOCALLY (remove + persist), never write replies.xml. Action
            -- cards (always id'd) are unchanged: their X/answer writes a reply
            -- and the card leaves only on a recorded write.
            local removed
            if r.id == nil then
                removed = true
            else
                removed = self:writeReply(r.id, r.reply)
            end
            if removed then
                -- Remove the CLICKED card only, by table identity -- ids come
                -- from untrusted notify.xml, and two live cards sharing one
                -- id must not both vanish under a single click. (writeReply's
                -- (id,action) idempotency contract still collapses their
                -- same-action answers to one recorded reply; each instance is
                -- dismissed by its own click -- see writeReply.)
                for i = #self.stack, 1, -1 do
                    if self.stack[i] == r.card then
                        local gone = table.remove(self.stack, i)
                        -- ⭐ TECH-DEBT-060: THIS is the card the transcript
                        -- exists for. writeReply records id/action/gameTime/
                        -- realTime only, so before this the correlation id
                        -- survived while the question text it referred to was
                        -- destroyed -- 49 live exchanges, none reconstructable.
                        -- An id'd card was ANSWERED; an id-less one (LT-6, the
                        -- passive info X) was DISMISSED. Same click, two
                        -- different things to have recorded.
                        self:retain(gone, r.id ~= nil
                            and FarmManager25.STATUS_ANSWERED
                            or FarmManager25.STATUS_DISMISSED)
                        break
                    end
                end
                -- LT-8: write-on-removal. A dismissed/answered card must not
                -- resurrect on an unclean restart -- this path removed from the
                -- stack but never persisted (the pre-existing gap). Marking
                -- dirty lets update()'s flush mirror the removal into state.xml.
                self.stateDirty = true
            end
            return true
        end
    end
    return false
end

--- A left-release over the reply bar (LT-4): open the base game's
--  TextInputDialog for a free-text message to the farm manager. The dialog
--  API shape is Courseplay's, verbatim (4 live call sites, e.g.
--  CustomFieldManager.lua:126-130 and the callback at :206):
--      TextInputDialog.show(callback, target, defaultText, dialogText,
--                           title, maxCharacters, confirmText, args)
--  Returns true when the click hit the bar -- the click is consumed whether
--  or not the dialog could open, so it never falls through to the drag path.
--  A dialog failure costs one attempt and is printed; nothing latches.
function FarmManager25:openReplyBar(posX, posY)
    local r = self.inputBarRect
    if r == nil or posX < r.x or posX > r.x + r.w
            or posY < r.y or posY > r.y + r.h then
        return false
    end
    local ok, err = pcall(function()
        if TextInputDialog == nil or TextInputDialog.show == nil then
            error("TextInputDialog unavailable")
        end
        local confirm = (g_i18n ~= nil and g_i18n.getText ~= nil)
            and g_i18n:getText("button_ok") or "OK"
        TextInputDialog.show(
            FarmManager25.onReplyText, FarmManager25, "",
            "Type your message...", "AI FARM MANAGER", 120,
            confirm, nil)
    end)
    if not ok then
        print("FarmManager25: could not open the reply dialog -- " .. tostring(err))
    end
    return true
end

--- The TextInputDialog callback: write the typed text as a reply. Every
--  free-text reply carries a UNIQUE id ("text-<stamp>-<seq>") -- the
--  (id, action) idempotency key that protects affordance clicks from
--  double-counting would otherwise collapse every message after the first
--  into "already recorded". The date is probed, never trusted (the
--  writeReply discipline); the session sequence number alone still
--  uniquifies within a session if the clock is unreadable.
function FarmManager25:onReplyText(text, clickOk)
    local ok, err = pcall(function()
        if not clickOk then
            return
        end
        text = tostring(text or ""):gsub("^%s*(.-)%s*$", "%1")
        if text == "" then
            return
        end
        FarmManager25.textReplySeq = FarmManager25.textReplySeq + 1
        local stamp = ""
        local okDate, d = pcall(function() return getDate("%Y%m%d%H%M%S") end)
        if okDate and type(d) == "string" then
            stamp = d .. "-"
        end
        local id = "text-" .. stamp .. tostring(FarmManager25.textReplySeq)
        -- Persist the advanced counter the moment a reply is recorded (not
        -- only at map exit): the counter's whole job is surviving into the
        -- next session, and a session that ends without deleteMap would
        -- otherwise rewind it.
        if self:writeReply(id, "text", { text }) then
            self:saveState()
        end
    end)
    if not ok then
        print("FarmManager25: could not record the text reply -- " .. tostring(err))
    end
end

function FarmManager25:mouseEvent(posX, posY, isDown, isUp, button)
    local ok, err = pcall(function()
        -- Mouse-wheel scroll of the card window (S157 owner ask): reveal older
        -- cards when more exist than the capped window shows. GIANTS delivers
        -- the wheel to mouseEvent as a button tick -- Input.MOUSE_BUTTON_WHEEL_
        -- UP/_DOWN, isDown on the tick. Gated exactly like a click: only while
        -- the ENGINE cursor is up and only over the panel. On foot the wheel
        -- ALSO zooms the camera now -- item 11's suppression lock was removed so
        -- the wheel reaches us again (BP-067; the owner accepts that movement,
        -- and the click/drag scrollbar is the zero-movement alternative).
        -- Nil-tolerant on Input and panelRect: with either absent the
        -- wheel falls straight through to the game, untouched. Wheel up scrolls
        -- toward OLDER history (offset up); the frame clamps the offset.
        if isDown and Input ~= nil and self.panelRect ~= nil
                and self:cursorIsShown()
                and not (g_gui ~= nil and g_gui:getIsGuiVisible()) then
            local r = self.panelRect
            if posX >= r.x and posX <= r.x + r.w
                    and posY >= r.y and posY <= r.y + r.h then
                if button == Input.MOUSE_BUTTON_WHEEL_UP then
                    FarmManager25.scrollOffset = FarmManager25.scrollOffset + 1
                    return
                elseif button == Input.MOUSE_BUTTON_WHEEL_DOWN then
                    FarmManager25.scrollOffset = math.max(0, FarmManager25.scrollOffset - 1)
                    return
                end
            end
        end
        -- Scrollbar drag (item 18): a click/drag on the thumb scrolls the card
        -- window with ZERO camera movement -- button events are not contested by
        -- the on-foot camera (unlike the wheel), so this path works whether or
        -- not the cursor is also swinging the view. A drag in flight owns every
        -- event until release: map the thumb's Y back to a scroll offset
        -- (renderStack re-clamps to a full last page and redraws the thumb from
        -- it next frame). Same gate as a click on the way IN (cursor up, no menu
        -- owning the screen, a thumb drawn this frame).
        if self.scrollDrag ~= nil then
            if isUp and button == 1 then
                self.scrollDrag = nil
            elseif self.scrollbarRect ~= nil and self.scrollTravel > 0 then
                local sb = self.scrollbarRect
                local newY = clamp(posY - self.scrollDrag.grab, sb.y, sb.y + self.scrollTravel)
                local frac = (newY - sb.y) / self.scrollTravel
                FarmManager25.scrollOffset = clamp(math.floor(frac * self.scrollRange + 0.5),
                                                   0, self.scrollRange)
            end
            return
        end
        if isDown and button == 1 and self:cursorIsShown()
                and not (g_gui ~= nil and g_gui:getIsGuiVisible())
                and self.scrollThumbRect ~= nil then
            local t = self.scrollThumbRect
            if posX >= t.x and posX <= t.x + t.w
                    and posY >= t.y and posY <= t.y + t.h then
                self.scrollDrag = { grab = posY - t.y }
                return
            end
        end
        -- THE DESIGN (S153 live-test rework): click-gating READS the shared
        -- engine cursor -- raised by AutoDrive's MMB, Courseplay's RMB, this
        -- mod's own Ctrl+Comma toggle, or any cursor mod -- because the
        -- ecosystem contract is "any cursor up => every mod's HUD is
        -- clickable" (AutoDrive.lua:596-601; AD watches foreign cursor changes
        -- at Specialization.lua:405). The click path never writes that state
        -- (only FM25_TOGGLE_CURSOR does); nothing here arms or latches. The GUI
        -- guard stays: a menu that owns the screen must not let a stray
        -- click under it answer a card. The reply bar (LT-4) shares the
        -- exact gate chain -- affordances win when both could hit.
        if isUp and button == 1 and self:cursorIsShown()
                and self.dragOffset == nil
                and not (g_gui ~= nil and g_gui:getIsGuiVisible())
                and (self:handleAffordanceClick(posX, posY)
                     or self:openReplyBar(posX, posY)) then
            return
        end
        -- Drag-start shares the cursor gate, nil-TOLERANT (g_inputBinding
        -- absent => allow): a click that writes a reply must fail closed,
        -- but a cosmetic drag may fail open where no input surface exists.
        if isDown and button == 1 and self.dragOffset == nil
                and (g_inputBinding == nil or g_inputBinding:getShowMouseCursor()) then
            local r = self.headerRect
            if r ~= nil and posX >= r.x and posX <= r.x + r.w
                        and posY >= r.y and posY <= r.y + r.h then
                local d = FarmManager25.DESIGN
                self.dragOffset = { x = posX - d.anchorX, y = posY - d.anchorY }
            end
        elseif self.dragOffset ~= nil then
            -- Any event while dragging repositions; release ends the drag.
            -- anchorX is the panel's RIGHT edge and anchorY its TOP, so these
            -- clamps keep the whole panel on-screen horizontally and the
            -- header reachable vertically -- a window dragged off-screen could
            -- never be dragged back.
            local d = FarmManager25.DESIGN
            d.anchorX = clamp(posX - self.dragOffset.x, self.panelW or 0, 1)
            d.anchorY = clamp(posY - self.dragOffset.y, 0.05, 0.999)
            self.panelLeft = d.anchorX - (self.panelW or 0)
            self.panelTop  = d.anchorY
            if isUp and button == 1 then
                self.dragOffset = nil
                self:saveState()
            end
        end
    end)
    if not ok then
        self.dragOffset = nil
        print("FarmManager25: mouseEvent failed -- " .. tostring(err))
    end
end

-- ⛔ THE IN-GAME MENU PAGE IS LOADED HERE, AND NOWHERE ELSE.
--
-- modDesc's <extraSourceFiles> lists ONLY FarmManagerTheme.lua and this file.
-- ⛔ extraSourceFiles does NOT auto-load anything under gui/ -- so without this
-- line gui/InGameMenuFarmManager25.lua ships inside the zip and NEVER EXECUTES:
-- InGameMenuFarmManager25 stays nil, registerMenuPage() and onToggleSettings()
-- both hit their nil checks and return, and the entire page -- both tabs, the
-- ten settings rows, the message log -- is silently absent while the mod logs
-- as healthy. That was the shipped state until this line was added; every test
-- passed throughout, because the core suite tests core in isolation.
--
-- The idiom is the reference mod's, verbatim in shape:
--   FS25_FarmOperationsDashboard/FarmOperationsDashboard.lua:5
--     source(dir .. "gui/InGameMenuFarmOperationsDashboard.lua")
-- whose modDesc likewise declares only its top-level scripts.
--
-- ⚠ MODULE SCOPE, NOT loadMap. MOD_DIR is captured at the top of this file
-- while g_currentModDirectory is still set; by loadMap it is nil and the path
-- would resolve to a bare "gui/..." that finds nothing.
--
-- ⚠ Unguarded ON PURPOSE. source() is a GIANTS global that always exists in the
-- game, and wrapping this in `if source ~= nil` would put a test-harness
-- accommodation into shipped code -- the same class of silent degrade that hid
-- the missing call in the first place. The harness defines source() faithfully
-- instead (it really loads the file), which is also what makes the core<->GUI
-- seam testable at all.
source(FarmManager25.MOD_DIR .. "gui/InGameMenuFarmManager25.lua")

addModEventListener(FarmManager25)
