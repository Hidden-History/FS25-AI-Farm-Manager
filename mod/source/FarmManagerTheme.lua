--[[
    FarmManagerTheme.lua
    --------------------
    ALL of the panel's visual design values, and nothing else: colours,
    measurements, and the per-severity card families, locked to the target
    mockup (assets/in_game_overlay_FarmManager25.png) by pixel sampling --
    every colour below is a median-of-region sample, not a guess. The
    renderer (FarmManager25.lua) reads THEME; it never defines colours.

    Listed FIRST in modDesc's <extraSourceFiles>: files execute in order into
    one shared per-mod global environment (BP-065 -- the ContractBoost /
    Courseplay ordered-list idiom), so this file creates the FarmManager25
    table and the renderer extends it. No engine calls, so load order is its
    only dependency. (It was "pure data, no functions" until 2026-09-17; it now
    also carries the colour-space conversion - pure Lua arithmetic, no engine
    calls - so the property that sentence protected still holds. See the seam
    note at the end of the file.)

    Scale basis: mockup panel content 897px == DESIGN.panelWidthPx 330, x0.368.
]]

FarmManager25 = FarmManager25 or {}

FarmManager25.THEME = {
    -- The content column geometry. S157 removed the shared backdrop rect (it
    -- reused the CARD 3-slice atlas graphic stretched to the panel's whole,
    -- card-count-dependent height, so its baked corner radius distorted); the
    -- header, cards and reply bar each draw their own correctly-proportioned
    -- background, so only the inset survives here.
    panel = {
        insetPx  = 8,                        -- content inset from the panel edge
    },

    -- The header banner (owner art: textured plate, leaf badge and title are
    -- baked into the texture). Height derives from the panel width and the
    -- atlas region's 512/99 aspect so the art is never stretched.
    header = {
        tint = {1, 1, 1, 1},                 -- colour art: tint is a no-op
    },

    -- Per-severity card families, sampled from the mockup's three cards.
    -- critical has no mockup card; its values are DERIVED with the same
    -- bg/border/accent ratios as the three sampled families.
    cards = {
        ok       = { bg = {0.06, 0.14, 0.03, 1}, border = {0.40, 0.62, 0.20, 1}, accent = {0.70, 0.89, 0.31, 1} },  -- green
        warn     = { bg = {0.16, 0.11, 0.00, 1}, border = {0.72, 0.56, 0.03, 1}, accent = {0.91, 0.76, 0.09, 1} },  -- gold
        info     = { bg = {0.02, 0.09, 0.11, 1}, border = {0.28, 0.60, 0.70, 1}, accent = {0.32, 0.73, 0.90, 1} },  -- blue
        critical = { bg = {0.20, 0.05, 0.04, 1}, border = {0.85, 0.30, 0.25, 1}, accent = {0.98, 0.45, 0.38, 1} },  -- red (derived)
    },
    cardBorderPx = 2,                        -- bright border ring width

    -- ⛔ V-22. THE PROPORTIONAL BAR (SPEC D3). Added because § 6.4 rule 6 said
    -- "colour comes from FarmManagerTheme.lua ... do not re-source a palette"
    -- while THIS TABLE HAD NO BAR, TRACK OR FILL ENTRY AT ALL -- so the rule
    -- pointed at nothing and read as forbidding the lane from adding one.
    -- The menu already tints a row from THEME.cards[...].accent
    -- (InGameMenuFarmManager25.lua), so a bar fill is tinted the same way.
    --
    -- ⚠ ONE FILL COLOUR, NOT A SEVERITY RAMP, AND THAT IS DELIBERATE. A
    -- red/amber/green ramp needs runway CUT-OFFS ("under how many hours is a
    -- chain in trouble?"), and nobody has priced that question -- inventing two
    -- thresholds here would put a confident judgement in front of the player
    -- that no measurement supports. The bar already carries the severity in its
    -- LENGTH: it is normalised to a FIXED horizon
    -- (FarmManager25.RUNWAY_HORIZON_H), so a nearly-empty bar means nearly
    -- starved on every point, and the comparison holds across rows. Adding the
    -- ramp later is one table and one predicate; it is an OWNER decision, not
    -- an implementer's.
    -- `fill` is cards.ok.accent's value, written out rather than referenced
    -- because this file is pure data with no expressions in it.
    bar = {
        track = {0.13, 0.14, 0.14, 1},       -- the empty channel, dark and quiet
        fill  = {0.70, 0.89, 0.31, 1},       -- = cards.ok.accent (green)
    },

    text = {
        title       = {0.95, 0.96, 0.94, 1}, -- mockup titles are white + bold
        body        = {0.93, 0.93, 0.93, 1},
        placeholder = {0.52, 0.51, 0.51, 1},
        -- Text ON an accent fill: chosen.html `.tag.out{background:#b2e34f;
        -- color:#111}` (the OUT tag). #111 = 17/255 = 0.067. Added 2026-09-17;
        -- no existing key held it, and borrowing input.fieldBg (#0a0a0a) would
        -- have been a near colour presented as the design's.
        onAccent    = {0.067, 0.067, 0.067, 1},
        -- timestamps render in the card family's accent colour
    },

    -- Reply thumbs are FIXED green/red -- yes is always green and no always
    -- red, whatever colour the card is.
    thumbs = {
        up   = {0.30, 0.80, 0.30, 1},
        down = {0.88, 0.30, 0.25, 1},
    },

    -- The static reply bar (visual only this phase -- NO hitboxes; the
    -- functional free-text input is a later phase).
    input = {
        barHeightPx       = 54,
        bg                = {0.06, 0.07, 0.07, 0.95},
        fieldHeightPx     = 34,
        fieldBg           = {0.04, 0.04, 0.04, 1},
        fieldBorder       = {0.42, 0.44, 0.33, 0.6},
        chatGlyphPx       = 22,
        chatTint          = {0.55, 0.78, 0.29, 1},
        sendBoxPx         = 34,
        sendBg            = {0.12, 0.24, 0.07, 1},
        sendBorder        = {0.40, 0.62, 0.20, 1},
        sendGlyphPx       = 20,
        sendTint          = {0.65, 0.86, 0.35, 1},
        placeholderText   = "Type your message...",
        placeholderSizePx = 12,
    },
}

-- ---------------------------------------------------------------------------
-- ⛔⛔ THE COLOUR-SPACE SEAM. ONE CONVERSION PER CONSUMER, AND ONLY ONE.
--
-- Every colour above is a DISPLAY (sRGB) value: the header says each one is "a
-- median-of-region sample" from the mockup PNG, i.e. a screen pixel over 255.
-- text.placeholder {0.52,0.51,0.51} IS #858282, exactly as chosen.html's theme
-- table calls it. The ENGINE treats a colour tuple as LINEAR and sRGB-encodes
-- it on the way to the screen, so handing it a display value encodes an
-- already-encoded number and everything renders too bright -- measured +43.9%
-- at placeholder and +4.1% at body on the owner's 2026-09-17 screenshots.
--
-- ⛔ THE TABLES ABOVE ARE NOT CONVERTED AND MUST NEVER BE. They are the DESIGN
-- values, they match chosen.html key-for-key, and they have THREE consumers:
--   - the in-game menu  (InGameMenuFarmManager25.lua), through engineTheme()
--   - the on-screen overlay (FarmManager25.lua), through engineTheme() and the
--     converting blit() sink
--   - ⚠ guiProfiles.xml's hand-linearised colour literals. A GUI profile
--     cannot call Lua, so these are the converted values typed out. NOTHING
--     regenerates them: change a value here and the XML does not follow.
--     tests/test_chosen_html_conformance.py pins every literal to the THEME key
--     it came from, so a change here that the XML misses FAILS - update both.
-- Linearising the table in place would make whichever consumer already
-- converts convert a SECOND time. A double conversion is not subtle -- it puts
-- placeholder at 58 instead of 133 -- but it would ship green, because every
-- test compares against whatever the accessor returns. So the conversion lives
-- HERE, in one implementation, and each consumer calls it exactly once.
--
-- ⚠ THE TWO TABLES NEED DIFFERENT HANDLING, and this is measured, not assumed:
--   THEME  is never assigned to after load (0 write sites), so a converted
--          copy can be memoised safely.
--   DESIGN IS mutated at runtime -- the SETTINGS tab writes uiScale,
--          panelWidthPx, bodySizePx and cardAlpha -- so it is never copied.
--          Its three colours are converted AT THE POINT OF USE (DEC-216).
--
-- ⚠ NO ENGINE CALLS HERE. This file's header promises no engine calls, so
-- load order stays its only dependency (it held "pure data, no functions"
-- until 2026-09-17, when these functions arrived). They are pure Lua
-- arithmetic over numbers and add no load-order dependency, which is the
-- property that promise actually protects.
-- ---------------------------------------------------------------------------

--- sRGB -> linear for ONE channel. The standard piecewise transfer; the linear
--  toe below 0.04045 matters for the near-black card backgrounds (0.02, 0.03).
function FarmManager25.toLinearChannel(c)
    if type(c) ~= "number" then
        return c
    end
    if c <= 0.04045 then
        return c / 12.92
    end
    return ((c + 0.055) / 1.055) ^ 2.4
end

-- Memo keyed on the COLOUR TABLE'S IDENTITY, not on its values.
-- ⛔ THIS IS A DRAW-PATH ALLOCATION GUARD, NOT A MICRO-OPTIMISATION. blit() is
-- called ten times per panel per FRAME; converting on each call would allocate
-- a fresh table every time and churn the collector during rendering. Colour
-- tables here are constants, so identity is a sound key and each distinct
-- colour converts exactly once per session.
-- ⚠ WEAK KEYS so a colour table that goes out of scope can still be collected.
local engineColorCache = setmetatable({}, { __mode = "k" })

-- ⛔⛔ THE IDEMPOTENCE GUARD, AND IT IS THE WHOLE "EXACTLY ONCE" GUARANTEE.
-- Without it engineColor() is a pure transform that happily runs TWICE: hand
-- it a colour it already converted and it converts again, putting
-- text.placeholder at 58 instead of 133. Nothing would catch that -- every
-- test compares against whatever the accessor returned -- and it is one
-- careless call away at any future site, in either consumer.
-- Recording what came OUT makes a second call a NO-OP, so "one conversion per
-- consumer" is true BY CONSTRUCTION rather than by everyone remembering.
-- ⚠ Weak keys, like the cache above, so a converted colour can still be
-- collected.
local alreadyLinear = setmetatable({}, { __mode = "k" })

--- ⭐ THE ONE CONVERSION. Give it a DISPLAY colour, get the LINEAR colour the
--  engine must be handed. Safe to call repeatedly on the same table.
--  ⛔ ALPHA IS NOT CONVERTED. Alpha is a coverage fraction, not a light
--  intensity; running it through the transfer would make every translucent
--  element wrong in a second, independent way.
function FarmManager25.engineColor(c)
    if type(c) ~= "table" then
        return c
    end
    -- Already OUR output: converting again would double-encode it.
    if alreadyLinear[c] then
        return c
    end
    local hit = engineColorCache[c]
    if hit ~= nil then
        return hit
    end
    if type(c[1]) ~= "number" or type(c[2]) ~= "number" or type(c[3]) ~= "number" then
        return c
    end
    local out = {
        FarmManager25.toLinearChannel(c[1]),
        FarmManager25.toLinearChannel(c[2]),
        FarmManager25.toLinearChannel(c[3]),
        c[4],
    }
    engineColorCache[c] = out
    alreadyLinear[out] = true
    return out
end

--- Deep-copy a THEME subtree, converting every colour tuple.
--  A table is a COLOUR when its first three entries are numbers -- what every
--  colour in THEME looks like and what no other entry does.
local function linearizeThemeValue(v)
    if type(v) ~= "table" then
        return v
    end
    if type(v[1]) == "number" and type(v[2]) == "number" and type(v[3]) == "number" then
        return FarmManager25.engineColor(v)
    end
    local out = {}
    for k, sub in pairs(v) do
        out[k] = linearizeThemeValue(sub)
    end
    return out
end

local engineThemeCache = nil

--- ⭐ THE ONLY WAY EITHER CONSUMER MAY READ A THEME COLOUR.
--  Returns THEME with every colour in the space the engine paints in.
--  Memoised: pure over an immutable table, so it runs once per session.
function FarmManager25.engineTheme()
    if engineThemeCache ~= nil then
        return engineThemeCache
    end
    if FarmManager25.THEME == nil then
        return nil
    end
    engineThemeCache = linearizeThemeValue(FarmManager25.THEME)
    return engineThemeCache
end
