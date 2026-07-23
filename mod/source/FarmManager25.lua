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
-- The reverse channel: an append log the skill reads + truncates on its next
-- run. Many replies accrue between skill runs, so it is a log, not the
-- single-slot bridge notify.xml is.
FarmManager25.REPLIES_NAME    = "replies.xml"
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

FarmManager25.filePath      = nil
FarmManager25.timeSinceCheck = 0
FarmManager25.queue         = {}
FarmManager25.stack         = {}      -- live cards, OLDEST FIRST (top of screen)
FarmManager25.overlaysOk    = false
FarmManager25.useNativeOnly = false   -- set true and latched if drawing ever throws
FarmManager25.atlasId       = nil
FarmManager25.stateFolder   = nil     -- where state.xml lives; nil until loadMap
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
FarmManager25.textReplySeq      = 0      -- uniquifies free-text reply ids within a session
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
-- S158: the g_gui settings dialog. The controller instance is built once and
-- the XML registered in loadMap; settingsGuiLoaded latches true only when
-- g_gui:loadGui succeeded, so the settings keybind is a clean no-op when the
-- GUI framework is absent (a dedicated server, a headless test, or a failed
-- load) -- exactly the degrade discipline the rest of the mod uses.
FarmManager25.settingsGui       = nil
FarmManager25.settingsGuiLoaded = false


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
        delete(xml)
    end)
    if not ok then
        print("FarmManager25: settings.xml unreadable, using defaults -- " .. tostring(err))
    end
end

--- Load the mod-written client store. Runs AFTER loadSettings so the live
--  store (a position the player dragged to) wins over the hand-edited seed.
--  Same engine XML API and the same discipline as loadSettings: wrapped, and a
--  corrupt file costs the stored position/mode/cards, never the notifier.
--
--  S155 (LT-1/LT-8): the store also carries the overlay mode and EVERY
--  un-dismissed card (info AND action) -- an unanswered question, and now any
--  card the player has not cleared, must survive a relog. Counts are written
--  explicitly (#lineCount etc.) so an empty <line/> cannot silently truncate
--  the read (the pollBridge blank-line lesson, applied to our own file).
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
        local count = getXMLFloat(xml, "farmManager25State.cards#count") or 0
        for i = 0, math.min(count, FarmManager25.MAX_STORE) - 1 do
            local key = string.format("farmManager25State.cards.card(%d)", i)
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
                table.insert(self.stack, n)
            end
        end
        delete(xml)
    end)
    if not ok then
        print("FarmManager25: state.xml unreadable, using defaults -- " .. tostring(err))
    end
end

--- Write the client store. Called on drag-end, on mode toggle, on map exit,
--  and (LT-8) on any stack change via update()'s coalesced dirty-flush.
--  ContractBoost's modSettings write pattern: createXMLFile + setters +
--  saveXMLFile + delete (setXMLString on indexed paths: AutoDrive
--  RoutesManager.lua:220). Wrapped: a failed save costs persistence, nothing
--  else. EVERY card in the live stack is written (LT-8, supersedes O5's
--  action-only rule) -- state.xml mirrors the stack, so a dismissed/answered
--  card is gone and an un-dismissed info card survives a restart. Info cards
--  carry no id/actions: their minimal shape is severity/title/icon/stamp/lines.
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
        local i = 0
        for _, n in ipairs(self.stack) do
            local key = string.format("farmManager25State.cards.card(%d)", i)
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
        setXMLFloat(xml, "farmManager25State.cards#count", i)
        saveXMLFile(xml)
        delete(xml)
    end)
    if not ok then
        print("FarmManager25: could not save state.xml -- " .. tostring(err))
    end
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
    if self.stateFolder == nil then
        return false
    end
    local path = self.stateFolder .. FarmManager25.REPLIES_NAME
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
-- settings page (S158): the g_gui dialog's apply logic lives here as plain
-- methods on FarmManager25 so it is lupa-testable; the DialogElement
-- controller (FarmManagerSettingsGui.lua) is a thin shell that calls these.
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

--- Open the settings dialog (FM25_TOGGLE_SETTINGS, default Ctrl+Alt+Period).
--  Works on foot or in a vehicle -- no camera concern, it's a modal GUI. Same
--  guards as the other keys: nil-tolerant on g_gui, skipped while a menu
--  already owns the screen, and a clean no-op when the dialog never
--  registered (headless / load failure) so the key can never throw.
function FarmManager25:onToggleSettings()
    local ok, err = pcall(function()
        if g_gui == nil then
            return
        end
        if g_gui:getIsGuiVisible() then
            return
        end
        if not FarmManager25.settingsGuiLoaded then
            return
        end
        g_gui:showDialog("FarmManagerSettings")
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


function FarmManager25:buildOverlays()
    local ok, err = pcall(function()
        local d = FarmManager25.DESIGN
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
        local path = Utils.getFilename("textures/fm25_atlas.dds", FarmManager25.MOD_DIR)
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


--- Register the settings dialog with g_gui (S158). Guarded end to end: with
--  g_gui absent (dedicated server / headless test), the source class not
--  loaded, or any load failure, settingsGuiLoaded stays false and the settings
--  key is a clean no-op. loadProfiles + loadGui is AutoDrive's exact shape
--  (Gui.lua:3,60); the controller is instantiated ONCE (.new() BEFORE loadGui
--  -- the "nil controller" trap, BP-064 §1) and reused across map reloads.
--  Loaded is latched on a throw-free pass, not on loadGui's return value
--  (its success convention varies); showDialog is itself guarded in
--  onToggleSettings, so a mis-registered name degrades to a printed no-op.
function FarmManager25:registerSettingsGui()
    FarmManager25.settingsGuiLoaded = false
    if g_gui == nil or FarmManagerSettingsGui == nil or FarmManagerSettingsGui.new == nil then
        return
    end
    local ok, err = pcall(function()
        g_gui:loadProfiles(FarmManager25.MOD_DIR .. "gui/guiProfiles.xml")
        if FarmManager25.settingsGui == nil then
            FarmManager25.settingsGui = FarmManagerSettingsGui.new()
        end
        g_gui:loadGui(FarmManager25.MOD_DIR .. "gui/FarmManagerSettingsGui.xml",
            "FarmManagerSettings", FarmManager25.settingsGui)
        FarmManager25.settingsGuiLoaded = true
    end)
    if not ok then
        print("FarmManager25: settings GUI registration failed -- the settings key is off this session -- " .. tostring(err))
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

    local folder = getUserProfileAppPath() .. FarmManager25.RELATIVE_FOLDER
    createFolder(folder)

    self.filePath       = folder .. FarmManager25.FILE_NAME
    self.timeSinceCheck = 0
    self.queue          = {}
    self.stack          = {}
    self.useNativeOnly  = false

    self.interactiveOk      = true
    self.affordanceRects    = nil
    self.inputBarRect       = nil
    self.panelRect          = nil
    FarmManager25.scrollOffset = 0
    -- loadState populates the stack directly (not via push), so it must not
    -- arm the dirty-flush -- we would re-save what we just read.
    self.stateDirty         = false

    self.stateFolder = folder
    self:loadSettings(folder)     -- hand-edited seed first...
    self:loadState(folder)        -- ...then the live store wins (mode + cards too)
    self:buildOverlays()
    self:installOverlayToggleHook()
    self:registerSettingsGui()

    -- Start from a clean bridge: a message left over from a previous session
    -- is stale by definition and must not pop on load.
    if fileExists(self.filePath) then
        FarmManager25.consumeBridge(self.filePath)
    end

    print(string.format("FarmManager25: watching '%s' (protocol %d, custom HUD %s)",
        self.filePath, FarmManager25.PROTOCOL, self.overlaysOk and "on" or "OFF - native fallback"))
end

function FarmManager25:deleteMap()
    -- Persist the window position, overlay mode and un-actioned action cards
    -- on the way out (saveState no-ops when stateFolder is nil, i.e. the
    -- dedicated-server path never got this far).
    self:saveState()
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
    self.filePath      = nil
    self.queue         = {}
    self.stack         = {}
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
        table.remove(self.stack, 1)   -- drop the oldest; the newest is the one that matters
        print("FarmManager25: card store full, dropped the oldest card")
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
            -- LT-8: state.xml mirrors the live stack -- an OFF-mode expired
            -- transient card must not resurrect on restart.
            self.stateDirty = true
        end
    end

    while #self.queue > 0 do
        self:push(table.remove(self.queue, 1))
    end

    -- LT-8: coalesced persist. Any stack mutation this tick (arrival, eviction,
    -- expiry, and dismiss/answer set from mouseEvent) writes state.xml exactly
    -- ONCE here, not per-card -- human message cadence, negligible cost, and
    -- never a per-frame write on an idle stack.
    if self.stateDirty then
        self.stateDirty = false
        self:saveState()
    end
end


-- ---------------------------------------------------------------------------
-- draw: the panel
-- ---------------------------------------------------------------------------

--- Draw one atlas region. renderOverlay takes x,y as the BOTTOM-LEFT corner.
function FarmManager25:blit(uv, x, y, w, h, c, alpha)
    setOverlayUVs(self.atlasId, unpack(GuiUtils.getUVs(uv, {FarmManager25.ATLAS_W, FarmManager25.ATLAS_H})))
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
    local theme = FarmManager25.THEME
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
    local theme = FarmManager25.THEME
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
    local theme = FarmManager25.THEME
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
    local theme = FarmManager25.THEME
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
        local c = FarmManager25.DESIGN.timeColor
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
        local c = FarmManager25.DESIGN.timeColor
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
                        table.remove(self.stack, i)
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

addModEventListener(FarmManager25)
