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
    table and the renderer extends it. Pure data -- no engine calls, no
    functions -- so load order is its only dependency.

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

    text = {
        title       = {0.95, 0.96, 0.94, 1}, -- mockup titles are white + bold
        body        = {0.93, 0.93, 0.93, 1},
        placeholder = {0.52, 0.51, 0.51, 1},
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
