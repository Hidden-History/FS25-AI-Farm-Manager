--[[
    InGameMenuFarmManager25.lua
    ---------------------------
    Stage 1 in-game menu page: two sub-tabs, MESSAGES and SETTINGS, spliced
    into the native pause-menu TabbedMenu. Retires the old FarmManagerSettingsGui
    modal dialog.

    ADAPTED FROM (read-only reference, verified shipping):
    dev-mods/gameplay-mods/FS25_FarmOperationsDashboard/gui/InGameMenuFarmOperationsDashboard.lua
      - Class(x, TabbedMenuFrameElement) shape, setMenuButtonInfo, onFrameOpen/
        onFrameClose/onGuiSetupFinished/initialize lifecycle -- copied nearly
        verbatim (:1-108).
      - The sub-tab strip built by cloning `selectorPrefab` (:70-98) -- copied,
        NUM_TABS dropped from 9 (FOD) to 2 (MESSAGES/SETTINGS) and the
        `+140 * g_pixelSizeScaledX` paging-width pad (tuned for 9 tabs) reduced
        to `+40 * g_pixelSizeScaledX`. ⚠ PIXEL VALUE IS UNVERIFIED -- FOD's own
        constant was tuned by eye for its own tab count; ours is a proportional
        guess, not a measurement. Live-test question, not a test question.
      - getNumberOfSections/getNumberOfItemsInSection/populateCellForItemInSection
        (:171-206) -- the SmoothList data-source/delegate shape, copied; the
        colour-by-severity treatment at :195-202 is adapted to read
        FarmManager25.THEME.cards[row.severity].accent instead of a hardcoded
        priority->colour table (this mod already owns that palette --
        FarmManagerTheme.lua -- so the page reads it rather than inventing a
        second one).

    NOT copied from FOD: the fixInGameMenu splice. TabbedMenu:addPage was tried
    first but is REMOVED as of 2026-09-02 (CRITICAL: it registers the frame and
    the page-root element in two different registries, which froze the load at
    57% -- see InGameMenuFarmManager25.fixInGameMenu below). FOD's manual
    splice, already verified shipping, is now the only path.

    THE INTERFACE CONTRACT (dev-fm-core publishes these on FarmManager25; this
    file only READS them, never writes FarmManager25.lua):
      1. FarmManager25:getMessageLog() -> newest-first array of
         { whenText, fromText, messageText, statusText, severity, answered }.
         getMessageLog() is zero engine calls by design, so core cannot call
         g_i18n:getText itself -- CONFIRMED by team-lead 2026-09-01:
           - whenText (the card's stamp), fromText (n.title), messageText
             (n.body) are RAW pass-through, never resolved as l10n. whenText
             is "" when the clock was dead -- render the blank, no fallback
             string; a fabricated timestamp in a transcript is worse than an
             empty one.
           - statusText IS AN L10N KEY, resolved here via self.i18n:getText().
             The six confirmed keys -- fm25_status_live, fm25_status_answered,
             fm25_status_dismissed, fm25_status_expired, fm25_status_evicted,
             fm25_status_native -- live in every translation_*.xml alongside
             our own static keys. fm25_status_native marks a card shown
             through the game's native-notification fallback during a render
             failure and then retained: the transcript's record that
             something went wrong and what the player saw anyway.
           - severity is a SEVERITIES key, drives row colour (read from
             FarmManager25.THEME.cards, not translated). answered is boolean.
      2. FarmManager25.SETTINGS_ROWS -> ordered array of
         { key, kind = "stepper"|"action", l10nName, texts, getIndex, setIndex,
         invoke }. Rendered generically; no row list, no hardcoded label lives
         here. `l10nName` and every `texts` entry are ALWAYS l10n keys,
         unconditionally, resolved via self.i18n:getText() -- CONFIRMED by
         team-lead 2026-09-01 (SUPERSEDING an earlier "fm25_ prefix vs. bare
         numeral" rule floated the same day: core removed that escape hatch,
         "a rule with an exception is a rule someone gets wrong"). The 36
         stepper VALUE keys this implies (fm25_scale_50, fm25_width_330, ...;
         see translation_en.xml's own comment for the full derivation) carry
         their unit IN THE VALUE ("330 px"), not in the row name -- so
         l10nName text is unit-free ("Panel width", not "Panel width (px)").
      3. This file publishes InGameMenuFarmManager25.PAGE_NAME and
         InGameMenuFarmManager25.register(). Core calls .register() from
         loadMap, and must `source()` this file first (FOD's own main script
         does this for its gui/*.lua at FarmOperationsDashboard.lua:5 --
         extraSourceFiles does NOT auto-load files under gui/).

    Headless guard, same reasoning and shape as FarmManagerSettingsGui.lua: the
    g_gui framework (Class / TabbedMenuFrameElement) is absent under the lupa
    test harness. Without it this file must not define a screen class --
    calling Class(x, nil) would raise at load time, in every test that sources
    this file. Leave InGameMenuFarmManager25 a bare table (.new/.register stay
    nil) and return; core's register() call then degrades to whatever guard
    core puts around it (mirroring registerSettingsGui's own nil-checks).
]]

InGameMenuFarmManager25 = InGameMenuFarmManager25 or {}

if Class == nil or TabbedMenuFrameElement == nil then
    return
end

InGameMenuFarmManager25.PAGE_NAME = "pageFarmManager25"

-- ---------------------------------------------------------------------------
-- ⛔ C3 (PLAN-UI-FIXES item 15): THE THEME IS AUTHORED IN DISPLAY (sRGB)
-- SPACE AND THE ENGINE WANTS LINEAR. This is a COLOUR-SPACE conversion, NOT a
-- brightness tweak, and the difference matters: darkening one constant until
-- it looks right fixes one cell and leaves every other colour wrong.
--
-- WHY THE THEME IS A DISPLAY VALUE. FarmManagerTheme.lua's header says every
-- colour is "a median-of-region sample" taken from the mockup PNG, i.e. a
-- screen pixel divided by 255. So text.placeholder {0.52,0.51,0.51} IS
-- #858282 -- exactly what chosen.html's "Theme values used" table calls it.
-- The engine treats a colour tuple as LINEAR and encodes it to sRGB on the
-- way to the screen, so handing it a display value paints the sRGB encode of
-- an already-encoded number, and everything renders too bright.
--
-- ⭐ MEASURED, not inferred, off the owner's 2026-09-17 live-test screenshots
-- (Pillow, brightest-pixel core of each glyph run):
--
--      theme value            intended px   ON SCREEN   error
--      placeholder 0.52,0.51      133,130     191,189   +43.9%
--      body        0.93            237         247       +4.1%
--
-- Both land on the sRGB encode of the authored value TO THE INTEGER. That
-- non-linearity is the entire shape of the bug report: the transfer barely
-- moves a near-white and lifts a mid-grey enormously, which is why the dim
-- class reads "~45% too bright" while the bright class looks fine.
-- ⛔ THE BRIGHT CLASS IS WRONG TOO -- by 10 levels, which nobody can see.
--
-- ⚠ THE CONSTANTS IN FarmManagerTheme.lua ARE CORRECT AND ARE NOT TOUCHED.
-- They are the design values and match chosen.html key-for-key. The
-- conversion happens on the way OUT, in ONE shared implementation in
-- FarmManagerTheme.lua that both this page and the overlay call - see
-- engineTheme() below and the seam note in that file. (This block used to say
-- the page was "the only consumer that gets linear values"; the overlay has
-- converted through the same function since the scope extension.)
-- ---------------------------------------------------------------------------

--- ⭐ THE PAGE'S HANDLE ON THE ONE SHARED CONVERSION.
--  ⛔ THIS IS A DELEGATION, NOT A SECOND IMPLEMENTATION, AND THAT IS THE
--  WHOLE POINT. The converter used to live here, privately. Then the overlay
--  (FarmManager25.lua) needed the same fix, and two copies of a colour-space
--  transform in one mod is how the two surfaces drift a shade apart with
--  every test green on both sides. There is now exactly ONE implementation,
--  in FarmManagerTheme.lua beside the data it converts, and both consumers
--  call it. See the seam note there for why the THEME table itself is never
--  converted in place.
function InGameMenuFarmManager25.engineTheme()
    return FarmManager25 ~= nil and FarmManager25.engineTheme ~= nil
        and FarmManager25.engineTheme() or nil
end

--- Nil-safe read of ONE colour out of engineTheme(), by path.
--  Exists so a colour read is one call instead of a four-line nil-guard
--  chain: the chains were what made it easy to add a new read that quietly
--  went to the RAW theme. `themeColor("text","placeholder")` cannot.
function InGameMenuFarmManager25.themeColor(...)
    local t = InGameMenuFarmManager25.engineTheme()
    local n = select("#", ...)
    for i = 1, n do
        if type(t) ~= "table" then
            return nil
        end
        t = t[select(i, ...)]
    end
    return t
end

-- ⭐ FARM-FIRST ORDER (chosen.html STRIP-4, "NEW ORDER: FARM, FIELDS,
-- PRODUCTIONS, MESSAGES, SETTINGS"). These constants are INDICES, and the
-- index IS the on-screen position.
--
-- ⛔ REORDERING IS SAFE HERE FOR ONE REASON, AND IT IS WORTH STATING BECAUSE
-- IT IS NOT OBVIOUS: switchTab maps each tabContainer<N> to a TAB_* CONSTANT
-- BY NAME, never by position, so tabContainer1 stays the MESSAGES panel
-- whatever number MESSAGES holds. Only the numbers and TAB_NAMES move; not one
-- XML id changes. Had switchTab indexed containers positionally, this edit
-- would silently have shown the wrong panel under every tab.
InGameMenuFarmManager25.TAB_MESSAGES = 4
InGameMenuFarmManager25.TAB_SETTINGS = 5
-- ⛔ SUPERSEDED 2026-09-03 by a later ruling from the same owner. This comment
-- read: "FARM and FIELDS are EMPTY SHELLS (owner's option (a)): the tab, its
-- strip entry and its container exist and switch correctly; the container has
-- no content yet and is deliberately not given a placeholder. Clicking one
-- moves the strip highlight and shows an empty page -- that is the intended
-- state, not an unfinished render."
-- It was true when written and is kept here as the record, not deleted.
-- What retired it: FARM was given real content (plan item 11), and on
-- 2026-09-03 the owner asked for an empty-state line on FIELDS and MESSAGES
-- ("field and messages"). Neither tab is a bare shell now.
-- ⭐ The original reasoning still binds where it still applies: a placeholder
-- that ships is a placeholder that gets believed. So what ships is ONE honest
-- line per empty tab and no invented content, and the FIELDS line names OUR
-- missing feature rather than describing the player's farm.
InGameMenuFarmManager25.TAB_FARM = 1
InGameMenuFarmManager25.TAB_FIELDS = 2
-- ⭐ D4, the FIFTH tab. Adding one is exactly three edits, and this is the
--  first: raise NUM_TABS, extend TAB_NAMES, add a switchTab visibility branch
--  and a tabContainer5. The strip itself is unchanged -- initialize() already
--  walks 1..NUM_TABS cloning selectorPrefab, so nothing about the mechanism
--  needed touching.
--  ⚠ AND A FIFTH TAB RE-OPENS ONE UNVERIFIED NUMBER: the
--  `+140 * g_pixelSizeScaledX` paging pad below. It is FOD's own constant and
--  the reasoning beside it argues it is tab-count independent, but whether the
--  arrows actually clear five labels is the OWNER'S EYE. No test here asserts
--  it and none can.
InGameMenuFarmManager25.TAB_PRODUCTIONS = 3
-- Index order here IS the on-screen order and MUST match NUM_TABS and the
-- tabContainer<N> ids in InGameMenuFarmManager25.xml. initialize() walks
-- 1..NUM_TABS and indexes TAB_NAMES by the same i, so a name missing here
-- would resolve to nil and setText would fail at strip-build time.
--- C1 / chosen.html STRIP-4: "Tab glyphs FarmManager25.ICONS: FARM finances,
--  FIELDS field, PRODUCTIONS building, MESSAGES briefing, SETTINGS gear".
--  ⛔ INDEXED BY THE TAB CONSTANT, not by position, so this map and
--  TAB_NAMES cannot drift if the strip is ever reordered again - the FARM-first
--  reorder is exactly the change that would have silently mismatched a
--  positional list.
InGameMenuFarmManager25.TAB_GLYPHS = {
    [InGameMenuFarmManager25.TAB_FARM]        = "finances",
    [InGameMenuFarmManager25.TAB_FIELDS]      = "field",
    [InGameMenuFarmManager25.TAB_PRODUCTIONS] = "building",
    [InGameMenuFarmManager25.TAB_MESSAGES]    = "briefing",
    [InGameMenuFarmManager25.TAB_SETTINGS]    = "gear",
}

InGameMenuFarmManager25.TAB_NAMES = {
    "fm25_tab_farm",
    "fm25_tab_fields",
    "fm25_tab_productions",
    "fm25_tab_messages",
    "fm25_tab_settings",
}
InGameMenuFarmManager25.NUM_TABS = 5

InGameMenuFarmManager25._mt = Class(InGameMenuFarmManager25, TabbedMenuFrameElement)

function InGameMenuFarmManager25.new(i18n)
    local self = InGameMenuFarmManager25:superClass().new(nil, InGameMenuFarmManager25._mt)

    self.name = "InGameMenuFarmManager25"
    self.i18n = i18n
    self.rows = {}
    -- Empty, never nil: the engine can ask for a section count before
    -- updateMessages() has ever run, and #nil is an error inside a GUI callback.
    self.messageGroups = {}
    -- Same rule for the two lists added with the master-detail rebuild.
    self.farmMaster = {}
    self.settingsGroups = {}
    -- No group selected yet. farmDetailRows() yields an EMPTY detail panel for
    -- this, never group 1's rows -- see the comment there.
    self.selectedFarmGroup = nil
    -- MESSAGES starts on ALL. ⛔ Named by constant, never the literal "all":
    -- a filter that matches no button leaves the strip with nothing
    -- highlighted, which reads as a broken page rather than a default.
    self.messageFilter = InGameMenuFarmManager25.FILTER_ALL
    -- Opens on the first tab, which is now FARM (chosen.html STRIP-4's
    -- farm-first order). Named by constant, not by the literal 1, so it
    -- follows any future reorder instead of quietly pointing elsewhere.
    self.currentTab = InGameMenuFarmManager25.TAB_FARM
    self.subCategoryTabs = {}
    self.settingsRowElements = {}
    -- PRODUCTIONS: four row sources, one per list. Empty until
    -- refreshProductionData() runs, and `prodMeta.status` -- not the emptiness
    -- of prodPoints -- is what says whether an empty page means "you own no
    -- productions" or "we could not ask".
    self.fieldRows = {}
    self.fieldMeta = { status = "unavailable" }
    self.selectedFieldIndex = 1
    self.prodPoints = {}
    self.prodLines = {}
    -- The merged IN/OUT rows. Empty, never nil: the engine can ask for a
    -- section count before any point has been selected.
    self.prodFillRows = {}
    self.prodMeta = { status = "unavailable" }
    self.prodIndex = 1
    self.backButtonInfo = {
        inputAction = InputAction.MENU_BACK
    }

    self:setMenuButtonInfo({
        self.backButtonInfo
    })

    return self
end

function InGameMenuFarmManager25:delete()
    InGameMenuFarmManager25:superClass().delete(self)
end

function InGameMenuFarmManager25:copyAttributes(src)
    InGameMenuFarmManager25:superClass().copyAttributes(self, src)
    self.i18n = src.i18n
end

function InGameMenuFarmManager25:onGuiSetupFinished()
    InGameMenuFarmManager25:superClass().onGuiSetupFinished(self)

    -- EMPTY-3 glyphs. Set ONCE here rather than on every show: the card is
    -- toggled often and the glyph never changes, so re-applying it per toggle
    -- would be work for no answer.
    -- The MESSAGES legend swatches, tinted from the SAME THEME.cards entries
    -- the row bars use. ⛔ One source, so the legend cannot teach a colour the
    -- rows do not draw -- a legend that disagrees with the thing it explains
    -- is worse than none.
    local legendBox = self.msgLegendBox
    if legendBox ~= nil and legendBox.getDescendantByName ~= nil
            and InGameMenuFarmManager25.themeColor("cards") ~= nil then
        for _, sev in ipairs({ "ok", "info", "warn", "critical" }) do
            local swatch = legendBox:getDescendantByName(
                "lg" .. sev:sub(1, 1):upper() .. sev:sub(2))
            local family = InGameMenuFarmManager25.themeColor("cards", sev)
            local c = family ~= nil and family.accent or nil
            if swatch ~= nil and c ~= nil and swatch.setImageColor ~= nil then
                swatch:setImageColor(nil, c[1], c[2], c[3], c[4])
            end
        end
    end

    for _, id in ipairs({ "messagesEmptyCard", "fieldsNoneCard", "fieldsEmptyCard",
                          "prodNoneCard", "prodUnavailableCard" }) do
        local card = self[id]
        if card ~= nil and card.getDescendantByName ~= nil then
            InGameMenuFarmManager25.setGlyph(
                card:getDescendantByName("emptyGlyph"), "report",
                InGameMenuFarmManager25.themeColor("cards", "info", "accent"))
        end
    end
    self.messageTable:setDataSource(self)
    self.messageTable:setDelegate(self)

    -- ⛔ FOUR MORE LISTS ON ONE DELEGATE, TOLD APART BY IDENTITY. Adapted from
    -- FS25_Distribution_Redux DistributionProductionsPage.lua:223-228, which
    -- dispatches `if list == self.assetList then ... end` rather than giving
    -- each list its own delegate object. That is the mechanism this page does
    -- not own and must not invent a second version of.
    -- ⚠ EACH ONE IS NIL-CHECKED SEPARATELY, not walked with ipairs over a
    -- table literal: a nil in position 1 makes ipairs yield NOTHING, so a
    -- single missing id would silently unbind all four.
    for _, list in pairs({ p1 = self.prodPointList, p2 = self.prodFillList,
                           p3 = self.prodLineList,
                           p5 = self.fieldList, p6 = self.farmMasterList,
                           p7 = self.settingsList }) do
        if list ~= nil then
            list:setDataSource(self)
            list:setDelegate(self)
        end
    end
end

--- Build the sub-tab strip (FOD :70-98, NUM_TABS 9 -> 2) and render the
--  SETTINGS rows from FarmManager25.SETTINGS_ROWS. Runs ONCE, right after
--  register() loads this page's GUI XML.
function InGameMenuFarmManager25:initialize()
    if self.selectorPrefab == nil or self.subCategoryBox == nil or self.subCategoryPaging == nil then
        return
    end

    self.selectorPrefab:unlinkElement()
    FocusManager:removeElement(self.selectorPrefab)

    for i = 1, InGameMenuFarmManager25.NUM_TABS do
        self.subCategoryPaging:addText(tostring(i))
        self.subCategoryTabs[i] = self.selectorPrefab:clone(self.subCategoryBox)
        FocusManager:loadElementFromCustomValues(self.subCategoryTabs[i])
        self.subCategoryTabs[i]:setText(self.i18n:getText(InGameMenuFarmManager25.TAB_NAMES[i]))

        -- C1 / H2: room for the glyph BESIDE the label, then the ring fill,
        -- then the glyph itself. Order matters: children paint in clone order
        -- and the Button's own label paints after all of them.
        InGameMenuFarmManager25.makeRoomForTabGlyph(self.subCategoryTabs[i])
        self:addTabChrome(self.subCategoryTabs[i], i)

        local background = self.subCategoryTabs[i]:getDescendantByName("background")
        if background ~= nil then
            background:setSize(self.subCategoryTabs[i].size[1], self.subCategoryTabs[i].size[2])
        end

        local tabIndex = i
        self.subCategoryTabs[i].onClickCallback = function()
            self:switchTab(tabIndex)
        end
    end

    self.subCategoryBox:invalidateLayout()
    -- 140 is FOD's own constant, restored 2026-09-02. It had been reduced to 40
    -- on the belief that the pad scales with tab count -- it does NOT, and this
    -- is the ONE value in this function that still differed from the reference
    -- without a reason recorded beside it (NUM_TABS, the other, is commented
    -- above).
    --
    -- WHY IT IS TAB-COUNT INDEPENDENT, from the engine's own implementation:
    -- BoxLayoutElement:updateLayoutCells accumulates
    --   elementFlowSize = element.absSize + margin.LOWER + margin.UPPER
    --   currentFlowSize = currentFlowSize + elementFlowSize + elementSpacing
    --   self.maxFlowSize = math.max(self.maxFlowSize, currentFlowSize)
    -- (docs/script/GUI/BoxLayoutElement.md, fs25-lookup corpus commit
    -- 24afb18e7cfb788b7686b9ec791671e0dcba32b9). So EVERY tab's width, margins
    -- and spacing are already inside maxFlowSize. What this constant adds is the
    -- arrow gutter -- the width the MultiTextOption needs beyond the label strip
    -- to seat its left/right arrows -- which is a function of the arrow art, not
    -- of how many tabs precede it. FOD runs 140 live at 9 tabs; the same gutter
    -- is what 4 tabs need.
    -- ⚠ Whether the arrows actually clear the labels is the OWNER'S EYE. No test
    -- in this repo asserts it and none can: the g_gui boundary is not stubbed.
    self.subCategoryPaging:setSize(self.subCategoryBox.maxFlowSize + 140 * g_pixelSizeScaledX)

    -- C1 / chosen.html STRIP-4: "arrows tinted THEME.input.sendBg". The paging
    -- control is stock and keeps all its behaviour; only its tint moves.
    -- ⛔ pcall'd like tintBar: a stock element that does not expose
    -- setImageColor must not take the page down at load.
    local arrow = InGameMenuFarmManager25.themeColor("input", "sendBg")
    if arrow ~= nil and self.subCategoryPaging.setImageColor ~= nil then
        pcall(function()
            self.subCategoryPaging:setImageColor(nil, arrow[1], arrow[2], arrow[3], arrow[4])
        end)
    end

    self:unlinkSettingsTemplates()
    self:buildSettingsRows()
    self:unlinkFarmTemplates()

    -- No buildFarmRows() call here: switchTab() below ends in refreshFarmData(),
    -- which does the one read and renders both consumers. Calling it here too
    -- would read getFarmRows() twice on every page load.
    self:switchTab(self.currentTab)
end

--- Detach the two row templates from the tree before cloning from them --
--  same unlink-then-clone order as selectorPrefab above.
function InGameMenuFarmManager25:unlinkSettingsTemplates()
    if self.stepperRowTemplate ~= nil then
        self.stepperRowTemplate:unlinkElement()
        FocusManager:removeElement(self.stepperRowTemplate)
    end
    if self.actionRowTemplate ~= nil then
        self.actionRowTemplate:unlinkElement()
        FocusManager:removeElement(self.actionRowTemplate)
    end
    -- The allowed-value chip. Not focusable (it is a legend, not a control),
    -- so it is unlinked but never handed to FocusManager.
    if self.allowedChipTemplate ~= nil then
        self.allowedChipTemplate:unlinkElement()
    end
end

--- Render FarmManager25.SETTINGS_ROWS generically: no row list of our own,
--  no user-visible string of our own. Core owns every key, kind, label key
--  and value; this only knows the SHAPE (kind = "stepper" | "action").
--  If SETTINGS_ROWS does not exist yet (core has not wired it), this renders
--  an empty SETTINGS tab -- not a crash, not a placeholder row.
--- ⛔ MASTER-DETAIL NOW (chosen.html SETTINGS). The ten rows used to be
--  cloned into one tall box, every stepper live at once. They are now a
--  sectioned master list of NAME + CURRENT VALUE, and only the SELECTED row's
--  stepper is built, into the 740px detail pane.
--
--  ⭐ WHAT DID NOT CHANGE: wireSettingsRow. The stepper is cloned from the
--  same template, focus-loaded the same way and wired to the same
--  getIndex/setIndex on the same row table. Only how MANY exist at a time, and
--  where they live, is different -- so the control's behaviour is the part
--  most likely to be right, and the LAYOUT is the part that needs the owner's
--  eyes.
--
--  ⚠ KEYBOARD AND CONTROLLER FOCUS MOVING BETWEEN THE LIST AND THE STEPPER IS
--  THE OWNER'S LIVE TEST. chosen.html names it as a requirement and no test
--  here can gate it: focus is engine behaviour, and stubbing FocusManager
--  would prove only that the stub was called.
function InGameMenuFarmManager25:buildSettingsRows()
    self.settingsGroups = InGameMenuFarmManager25.buildSettingsGroups(
        (FarmManager25 ~= nil and FarmManager25.SETTINGS_ROWS) or {})

    if self.settingsList ~= nil then
        local sg = InGameMenuFarmManager25.SECTION_GLYPHS.settingsList
        InGameMenuFarmManager25.applySectionGlyph(self.settingsList, sg.header, sg.icon)
        self.settingsList:reloadData()
    end

    -- Select the first real row so the detail pane is never blank on open.
    if self.selectedSetting == nil then
        local first = (self.settingsGroups[1] or {}).items
        self.selectedSetting = first ~= nil and first[1] or nil
    end
    self:buildSettingsDetail()
end

--- Clone the SELECTED row's control into the detail pane.
--- C1 / chosen.html SETTINGS: "Allowed values -> row.texts (every preset)".
--  ⛔ EVERY CHIP IS A KEY RESOLVED THROUGH i18n, exactly as the stepper's own
--  value is (settingValueText). row.texts holds l10n KEYS for some settings
--  and already-rendered strings for others, and getText returns its argument
--  unchanged when there is no entry -- which is what makes one call correct
--  for both and is why the raw value is never printed.
--  ⛔ THE LABEL HIDES WITH THE STRIP. An "ALLOWED VALUES" heading over an
--  empty row reads as a list that failed to load; the action row (the reset
--  button) legitimately has no presets, and that is not a gap to announce.
function InGameMenuFarmManager25:buildAllowedValueChips(row)
    local box = self.settingsAllowedBox
    if box == nil then
        return
    end
    while #box.elements > 0 do
        box.elements[1]:delete()
    end

    local texts = row ~= nil and row.texts or nil
    local has = texts ~= nil and #texts > 0
    if self.settingsAllowedLabel ~= nil then
        self.settingsAllowedLabel:setVisible(has)
    end
    if not has or self.allowedChipTemplate == nil then
        box:invalidateLayout()
        return
    end

    -- ⛔ M4 `.pv` / `.pv.on`: the chip for the value the setting HOLDS is
    -- --tabOn with --tabOnT text; every other chip is --rowB with --cell. Round
    -- 2 drew every chip alike (and on the status chip's profile), so the strip
    -- listed the range but never said where the setting sat in it.
    local current = nil
    if row.getIndex ~= nil and FarmManager25 ~= nil then
        local ok, idx = pcall(row.getIndex, FarmManager25)
        if ok then current = idx end
    end
    for i, key in ipairs(texts) do
        local chip = self.allowedChipTemplate:clone(box)
        if chip ~= nil then
            chip:setVisible(true)
            local on = (i == current)
            local label = chip:getDescendantByName("chipText")
            if label ~= nil then
                label:setText(self.i18n:getText(key))
                local ink = on and InGameMenuFarmManager25.themeColor("cards", "ok", "accent")
                    or InGameMenuFarmManager25.themeColor("text", "body")
                if ink ~= nil then label.textColor = ink end
            end
            local bg = chip:getDescendantByName("chipBg")
            local fill = on and InGameMenuFarmManager25.themeColor("cards", "ok", "bg")
                or InGameMenuFarmManager25.themeColor("bar", "track")
            if bg ~= nil and bg.setImageColor ~= nil and fill ~= nil then
                bg:setImageColor(nil, fill[1], fill[2], fill[3], fill[4])
            end
        end
    end
    box:invalidateLayout()
end

function InGameMenuFarmManager25:buildSettingsDetail()
    self.settingsRowElements = {}

    local box = self.settingsBox
    if box == nil or self.stepperRowTemplate == nil or self.actionRowTemplate == nil then
        return
    end

    while #box.elements > 0 do
        box.elements[1]:delete()
    end

    local row = self.selectedSetting
    self:buildAllowedValueChips(row)
    if self.settingsDetailTitle ~= nil then
        self.settingsDetailTitle:setText(row ~= nil
            and self.i18n:getText(row.l10nName or "") or "")
    end
    if self.settingsHelpText ~= nil then
        -- ⛔ THE HELP LINE IS BLANK WHEN WE HAVE NO HELP, NEVER A REPEAT OF THE
        -- TITLE. A restated title reads as an explanation and teaches nothing;
        -- an empty line is honest about a gap. (All ten help strings now exist
        -- as fm25_help_* in every translation file and are wired through
        -- row.helpKey; this used to say they were owed.)
        local helpKey = row ~= nil and row.helpKey or nil
        self.settingsHelpText:setText(helpKey ~= nil
            and self.i18n:getText(helpKey) or "")
    end
    if row == nil then
        box:invalidateLayout()
        return
    end

    local element = nil
    if row.kind == "stepper" then
        element = self.stepperRowTemplate:clone(box)
    elseif row.kind == "action" then
        element = self.actionRowTemplate:clone(box)
    end

    if element ~= nil then
        FocusManager:loadElementFromCustomValues(element)
        if element.setVisible ~= nil then
            element:setVisible(true)
        end
        self:wireSettingsRow(element, row)
        table.insert(self.settingsRowElements, element)
    end

    box:invalidateLayout()
end

--- One master row: the setting's name and the value it is currently on.
function InGameMenuFarmManager25:populateSettingsCell(list, section, index, cell)
    local rows = self:sectionRows(list, section)
    local row = rows ~= nil and rows[index] or nil
    if row == nil then
        return
    end

    local name = cell:getAttribute("stName")
    if name ~= nil then
        name:setText(self.i18n:getText(row.l10nName or ""))
    end
    -- ⛔ D2: AN ACTION HAS NO VALUE, EVER, SO IT HAS NOTHING TO BE UNKNOWN
    --  ABOUT. `resetPosition` is the only kind="action" row; the other nine
    --  are steppers. Routing it through the unknown-aware setter printed the
    --  dim WORD next to a button, which claims "we could not read this
    --  setting's value" about a thing that HAS no value. That is DEC-001
    --  inverted: the rule exists so an absent answer cannot be mistaken for
    --  data, not so a non-existent question gets reported as an absent
    --  answer. The two failures share the word `unknown` and nothing else --
    --  D1 is a real figure called absent, this is a non-question answered.
    --
    --  ⚠ THE COLOUR MUST BE SET EXPLICITLY, AND applyUnknownColor CANNOT DO
    --  IT HERE. List cells are recycled, so a cell that last rendered a dim
    --  unknown stepper still carries that colour; blanking the text alone
    --  leaves the action row wearing another row's dim, which reads as "we
    --  could not tell" on an empty cell.
    --  ⛔ applyUnknownColor(value, false) LOOKS like the right call and is a
    --  NO-OP here. It lazily captures `fm25BaseTextColor = element.textColor`
    --  on first use (applyUnknownColor: `element.fm25BaseTextColor =
    --  element.textColor or theme.text.body`), and on a recycled cell that value IS the
    --  dim -- so it pins the dim as the "baseline" and then restores it.
    --  Caught by mutation: deleting the call changed nothing, which is what a
    --  surviving mutant means. setUnknownAwareText never populates
    --  fm25BaseTextColor either, so the two helpers cannot be mixed on one
    --  element. Assign the body colour the same way setUnknownAwareText does
    --  for a known value (setUnknownAwareText: `known and theme.text.body`).
    local value = cell:getAttribute("stValue")
    if row.kind == "action" then
        if value ~= nil then
            value:setText("")
            local theme = InGameMenuFarmManager25.engineTheme()
            if theme ~= nil and theme.text ~= nil and theme.text.body ~= nil then
                value.textColor = theme.text.body
            end
        end
    else
        -- A stepper whose index cannot be read shows the dim WORD rather than
        -- a blank, which would read as "off".
        self:setUnknownAwareText(value, self:settingValueText(row))
    end
end

--- The l10n KEY of the value a stepper is currently on, or nil when it cannot
--  be read. ⛔ Returns the key, not English -- resolved by the caller, same
--  contract as every other label on this page.
function InGameMenuFarmManager25:settingValueText(row)
    if row == nil or row.texts == nil or row.getIndex == nil then
        return nil
    end
    local ok, index = pcall(row.getIndex, FarmManager25)
    if not ok or type(index) ~= "number" then
        return nil
    end
    local key = row.texts[index]
    if key == nil then
        return nil
    end
    return self.i18n:getText(key)
end


function InGameMenuFarmManager25:wireSettingsRow(element, row)
    if row.kind == "stepper" then
        local option = element:getDescendantByName("stepperOption")
        local title = element:getDescendantByName("stepperTitle")

        if title ~= nil and row.l10nName ~= nil then
            title:setText(self.i18n:getText(row.l10nName))
        end

        if option ~= nil then
            -- Every texts entry is an l10n key, unconditionally (core's
            -- superseding ruling, 2026-09-01: the earlier "fm25_ prefix vs.
            -- bare numeral" escape hatch is gone -- "a rule with an
            -- exception is a rule someone gets wrong". The 36 derived
            -- stepper value keys, e.g. fm25_width_330 = "330 px", carry
            -- their own unit now, so this resolves the same way l10nName
            -- always has.
            local labels = {}
            for j = 1, #(row.texts or {}) do
                labels[j] = self.i18n:getText(row.texts[j])
            end
            if option.setTexts ~= nil then
                option:setTexts(labels)
            end
            if option.setState ~= nil and row.getIndex ~= nil then
                option:setState(row.getIndex(FarmManager25))
            end

            local setIndex = row.setIndex
            --  ⛔ CORRECTED 2026-09-01 (CRITICAL): this closure took ONE
            --  parameter and treated it as the new index. The engine never
            --  calls it that way. GuiElement:raiseCallback PREPENDS the
            --  element's target -- `return self[name](self.target, ...)`
            --  (gameSource.zip dataS/scripts/gui/elements/GuiElement.lua:1637)
            --  -- and a cloned template element inherits a non-nil target
            --  (:524, `self.target = src.target`). So `state` bound to the
            --  TARGET TABLE, and wrapIndex (FarmManager25.lua:1422) did
            --  `((i - 1) % n) + 1` on a table -> a Lua error raised inside the
            --  engine's input path, outside every pcall we own. 9 of the 10
            --  settings rows are steppers, so 9 of 10 were dead on click; only
            --  the `action` row survived, because its closure takes no
            --  arguments. A REGRESSION -- the retired modal had the signature
            --  right.
            --  ⚠ WHAT IS NOT KNOWN, and why this takes NO parameters:
            --  whether the index is the argument immediately after the target.
            --  MultiTextOptionElement raises this via raiseClickCallback
            --  (:348/:707/:758) and that method's BODY is in neither the
            --  fs25-lookup corpus nor gameSource.zip (positive-controlled: a
            --  search for `raiseCallback` in the same zip DOES find its
            --  definition, so the zero is real, not a broken search). A
            --  positional guess would be unfalsifiable here.
            --  ⭐ So ignore the arguments entirely and read the index off the
            --  element, which is correct under ANY argument layout:
            --  MultiTextOptionElement:getState() returns self.state
            --  (MultiTextOptionElement.lua:356-357), and the engine assigns
            --  self.state BEFORE it raises (:675-685 then :707), so by the time
            --  we run, getState() is already the NEW index.
            --  ⚠ Our own option:setState(i) calls below cannot re-enter this:
            --  setState only raises when its second `forceEvent` arg is true
            --  (:342-349) and we never pass one.
            option.onClickCallback = function()
                if setIndex ~= nil and option.getState ~= nil then
                    setIndex(FarmManager25, option:getState())
                end
            end
        end
    elseif row.kind == "action" then
        if row.l10nName ~= nil and element.setText ~= nil then
            element:setText(self.i18n:getText(row.l10nName))
        end

        local invoke = row.invoke
        element.onClickCallback = function()
            if invoke ~= nil then
                invoke(FarmManager25)
            end
        end
    end
end

--- Re-sync stepper indices on every open (values can change outside this
--  page); labels/texts are static and set once in buildSettingsRows, matching
--  the retired modal's applyOption-once / syncOption-per-change idiom.
--- ⛔ REFRESHES THE SELECTED ROW AND THE LIST TOGETHER. Only one stepper
--  exists now, but its value is ALSO printed in the master list, and the two
--  must never disagree -- a list saying 85% beside a stepper on 100% is the
--  two-read-moments defect this page was already fixed for once.
function InGameMenuFarmManager25:refreshSettingsRows()
    local row = self.selectedSetting
    local element = self.settingsRowElements ~= nil
        and self.settingsRowElements[1] or nil
    if row ~= nil and row.kind == "stepper" and row.getIndex ~= nil
            and element ~= nil then
        local option = element:getDescendantByName("stepperOption")
        if option ~= nil and option.setState ~= nil then
            option:setState(row.getIndex(FarmManager25))
        end
    end
    if self.settingsList ~= nil then
        local sg = InGameMenuFarmManager25.SECTION_GLYPHS.settingsList
        InGameMenuFarmManager25.applySectionGlyph(self.settingsList, sg.header, sg.icon)
        self.settingsList:reloadData()
    end
end

--- Which groups sit in which column. 20 lines (18 before D-3) plus 5 headings is 25 rows, and
--  that many x 42px does not fit the panel; two columns split them. DATA, so
--  rebalancing the columns is an edit here and nothing else.
--  ⭐ CONTRACTS FIRST, top-left, and that is a ruling not a layout preference:
--  D is the only group with real bodies in the archive for enumeration, reward,
--  completion AND time-remaining, so it is the group most likely to be RIGHT on
--  the owner's first look. Core still PUBLISHES in research-citation order
--  (a1..e4) so a row traces to its citation; only the render order differs.
InGameMenuFarmManager25.FARM_COLUMNS = {
    { "d_contracts", "a_money" },
    { "b_land", "c_productions", "e_fleet" },
}

InGameMenuFarmManager25.FARM_GROUP_KEYS = {
    a_money       = "fm25_farm_group_money",
    b_land        = "fm25_farm_group_land",
    c_productions = "fm25_farm_group_productions",
    d_contracts   = "fm25_farm_group_contracts",
    e_fleet       = "fm25_farm_group_fleet",
}

--- Detach the FARM templates before cloning from them -- same unlink-then-clone
--  order as selectorPrefab and the settings templates.
function InGameMenuFarmManager25:unlinkFarmTemplates()
    if self.farmRowTemplate ~= nil then
        self.farmRowTemplate:unlinkElement()
        FocusManager:removeElement(self.farmRowTemplate)
    end
    if self.farmHeaderTemplate ~= nil then
        self.farmHeaderTemplate:unlinkElement()
        FocusManager:removeElement(self.farmHeaderTemplate)
    end
    -- The FIELDS detail row template: same unlink-then-clone order, and the same
    -- reason -- an element cloned while still linked keeps its old parent's
    -- geometry.
    if self.fieldDetailRowTemplate ~= nil then
        self.fieldDetailRowTemplate:unlinkElement()
        FocusManager:removeElement(self.fieldDetailRowTemplate)
    end
end

--- ⭐ THE ONE READ. Everything on this page that comes from getFarmRows() is
--  rendered from a SINGLE call here: the FARM table and the header balance chip.
--
--  ⛔ WHY THIS FUNCTION EXISTS (F-1, adversarial review, 2026-09-03). The chip
--  and FARM row a1 used to be fetched by two different call paths on two
--  different cadences: updateBalance() ran only from onFrameOpen(), while
--  buildFarmRows() ran from initialize() and from every switchTab() into FARM.
--  Open the menu, switch tabs, come back to FARM and the rows re-read while the
--  chip did not -- and the chip is header chrome visible on ALL FOUR tabs, with
--  no freshness label of its own to give the staleness away. Sharing an accessor
--  was never enough; what makes two figures agree is sharing a READ MOMENT.
--
--  The table is rebuilt only when FARM is the open tab -- it is 23 cloned
--  elements and nothing sees them otherwise -- but the chip is refreshed on
--  every switch, because it is always on screen.
function InGameMenuFarmManager25:refreshFarmData()
    local rows = {}
    if FarmManager25 ~= nil and FarmManager25.getFarmRows ~= nil then
        rows = FarmManager25:getFarmRows() or {}
    end

    self:updateBalance(rows)

    if self.currentTab == InGameMenuFarmManager25.TAB_FARM then
        self:buildFarmRows(rows)
    end
end


--- [[DEC-222]] D-8: the text of ONE freshness mark. LIVE, or "as of" WITH its
--  time. An as-of mark with no time to print still says "as of" -- a figure
--  that is not live must never read as live.
function InGameMenuFarmManager25.freshMarkText(isLive, liveText, asOfLabel, asOfText)
    if isLive then
        return liveText
    end
    if asOfText ~= nil and asOfText ~= "" then
        return asOfLabel .. " " .. asOfText
    end
    return asOfLabel
end

--- Render the rows refreshFarmData() fetched into the two static columns.
--  Takes the rows rather than fetching them: the header balance chip renders
--  from the SAME result, and a function that fetched its own would reintroduce
--  the second read moment this page was fixed to remove (see refreshFarmData).
--
--  ⛔ ZERO ENGINE READS. This renders what ONE core function handed back
--  (DEC-128 ②). It knows the SHAPE of a row -- labelKey, valueText,
--  unknown, freshness -- and not one figure, label or unit of its own.
--
--  ⛔ labelKey is an l10n KEY, resolved here, never by core. Same contract as
--  statusText in the message log: getFarmRows() makes no g_i18n call, so the
--  resolution has to happen on this side.
--
--  GUARD 8 is rendered here: an unknown value prints the WORD, from l10n --
--  never blank, never an em dash. GUARD 7: every row prints LIVE or AS-OF.
--  ⛔ [[DEC-222]] D-8 (owner ruling 2026-09-23): an AS-OF mark carries its
--  TIME on every row and tile ("as of 18:31"), as chosen.html shows (DEC-144,
--  DEC-209). The header stamp states it too; it no longer stands in for the
--  marks. The earlier "stamp printed once in the header" rule predates both.
--- ⛔ MASTER-DETAIL NOW, NOT TWO STATIC COLUMNS. chosen.html FARM replaces
--  farmBoxLeft / farmBoxRight with a five-row master list and a 930px detail
--  pane. The row RENDERING below is unchanged from the two-column version --
--  same template, same guards 7 and 8, same money formatter -- only where the
--  rows are put has changed. That split is deliberate: the layout was the
--  thing the owner re-specified, the truthfulness rules were not.
function InGameMenuFarmManager25:buildFarmRows(rows)
    self.farmRowElements = {}
    rows = rows or {}

    -- The page's as-of stamp (guard 7), independent of the split below so it
    -- still renders on a build where the list has not loaded. Each as-of row
    -- and tile ALSO carries its time (D-8, DEC-222); this is not instead.
    local asOfText = nil
    for i = 1, #rows do
        asOfText = asOfText or rows[i].asOfText
    end
    if self.farmAsOfText ~= nil then
        -- Blank when nothing has been published yet: an absent stamp must not
        -- read as "as of just now".
        self.farmAsOfText:setText(asOfText ~= nil
            and (self.i18n:getText("fm25_farm_asof") .. " " .. asOfText)
            or "")
    end

    -- ⛔ THE TILES READ THE SAME `rows` THE MASTER DOES -- one read moment,
    -- one answer. chosen.html: "values from the rows already read, no second
    -- getFarmRows() call".
    local tiles = InGameMenuFarmManager25.buildFarmTiles(rows)
    for i = 1, 4 do
        self:renderTile(self["farmTile" .. i], tiles[i])
    end

    self.farmMaster = InGameMenuFarmManager25.buildFarmMaster(rows)

    -- ⛔ THE SELECTION IS CLAMPED, NOT PRESERVED BLINDLY. The master is rebuilt
    -- on every refresh; a stored index that now points past the end would give
    -- farmDetailRows() an empty list under a heading that still reads FLEET.
    if self.selectedFarmGroup == nil
            or self.selectedFarmGroup > #self.farmMaster then
        self.selectedFarmGroup = #self.farmMaster > 0 and 1 or nil
    end

    if self.farmMasterList ~= nil then
        self.farmMasterList:reloadData()
    end
    self:buildFarmDetail()
end

--- Render the selected group's rows into the detail pane.
--  ⛔ ZERO ENGINE READS, exactly as before: this renders what ONE core call
--  handed back and knows the SHAPE of a row -- labelKey, valueText, unknown,
--  freshness -- and not one figure, label or unit of its own.
function InGameMenuFarmManager25:buildFarmDetail()
    local box = self.farmDetailBox
    if box == nil or self.farmRowTemplate == nil then
        return
    end

    while #box.elements > 0 do
        box.elements[1]:delete()
    end

    local entry = (self.farmMaster or {})[self.selectedFarmGroup or 0]
    -- M4 SECTIONS-3: the heading's glyph is the SELECTED GROUP's own
    -- (chosen.html's MONEY heading draws the finances mask, byte-identical to
    -- the FARM tab's), hidden when nothing is selected rather than stale.
    if self.farmDetailGlyph ~= nil then
        local g = entry ~= nil and entry.glyph or nil
        self.farmDetailGlyph:setVisible(g ~= nil)
        if g ~= nil then
            InGameMenuFarmManager25.setGlyph(self.farmDetailGlyph, g,
                InGameMenuFarmManager25.themeColor("cards", "ok", "accent"))
        end
    end
    if self.farmDetailTitle ~= nil then
        -- ⛔ THE HEADING AND THE ROWS COME FROM THE SAME ENTRY. Reading the
        -- title from one place and the rows from another is how a panel headed
        -- FIELD 6 ends up beside a selected Field 35 (the defect this page
        -- already shipped once).
        self.farmDetailTitle:setText(entry ~= nil
            and self.i18n:getText(entry.titleKey or "") or "")
    end
    if entry == nil then
        box:invalidateLayout()
        return
    end

    local unknownText = self.i18n:getText("fm25_farm_unknown")
    local liveText    = self.i18n:getText("fm25_farm_live")
    local asOfLabel   = self.i18n:getText("fm25_farm_asof")

    for _, row in ipairs(entry.items or {}) do
        local element = self.farmRowTemplate:clone(box)
        element:setVisible(true)

        local label = element:getDescendantByName("labelText")
        local value = element:getDescendantByName("valueText")
        local fresh = element:getDescendantByName("freshText")

        if label ~= nil then
            label:setText(self.i18n:getText(row.labelKey))
        end
        if value ~= nil then
            -- GUARD 8. `unknown` is the FLAG core publishes; the word itself
            -- is ours to localise. Core publishes money as a raw NUMBER and
            -- everything else pre-formatted, so money goes through the same
            -- formatter the header chip uses and nothing else does.
            local text
            if row.unknown then
                -- F7 ([[DEC-211]]): a REFUSED figure prints its refusal tag INSTEAD of the
                -- word (`unknown · capacity refused` does not fit the value cell), still
                -- dim below. Every other unknown keeps the word.
                local tagKey = row.refusalKind ~= nil
                    and InGameMenuFarmManager25.REFUSAL_TAG_KEYS[row.refusalKind] or nil
                text = tagKey ~= nil and self.i18n:getText(tagKey) or unknownText
            elseif row.valueNumber ~= nil then
                text = self:formatMoney(row.valueNumber)
            else
                text = row.valueText
            end
            value:setText(text)
            -- ⛔ [[DEC-199]]: the FARM rows print the unknown WORD (GUARD 8)
            -- and, until now, printed it in the same class as a real figure.
            InGameMenuFarmManager25.applyUnknownColor(value, row.unknown == true)
        end
        if fresh ~= nil then
            fresh:setText(InGameMenuFarmManager25.freshMarkText(
                row.freshness == FarmManager25.FARM_FRESH_LIVE,
                liveText, asOfLabel, row.asOfText))
        end

        table.insert(self.farmRowElements, element)
    end

    box:invalidateLayout()
end

--- One master row: glyph, group name, headline figure.
function InGameMenuFarmManager25:populateFarmMasterCell(index, cell)
    local entry = (self.farmMaster or {})[index]
    if entry == nil then
        return
    end
    InGameMenuFarmManager25.setGlyph(cell:getAttribute("fmGlyph"), entry.glyph,
        InGameMenuFarmManager25.themeColor("cards", "ok", "accent"))

    local group = cell:getAttribute("fmGroup")
    if group ~= nil then
        group:setText(self.i18n:getText(entry.titleKey or ""))
    end
    -- ⛔ THE HEADLINE GOES THROUGH THE UNKNOWN-AWARE SETTER. An absent headline
    -- renders the dim WORD, never a blank cell -- the same rule, and the same
    -- one call, the MESSAGES "When" column was fixed to use (DEC-001,
    -- DEC-199).
    -- ⛔ D1: money arrives as a NUMBER and is formatted here, never in the
    -- pure builder. Same order as the tile renderer
    -- (`self:formatMoney(tile.valueNumber)`) and the detail row
    -- (`self:formatMoney(row.valueNumber)`): number first, then the
    -- pre-formatted text.
    local headline = nil
    if not entry.headlineUnknown then
        if entry.headlineNumber ~= nil then
            headline = self:formatMoney(entry.headlineNumber)
        else
            headline = entry.headlineText
        end
    end
    self:setUnknownAwareText(cell:getAttribute("fmHeadline"), headline)
end


-- ---------------------------------------------------------------------------
-- PRODUCTIONS (SPEC Block D, D2 + D3). Master-detail over five lists.
--
-- ⛔ ZERO ENGINE READS FOR THE FIGURES. This renders what ONE core function
-- handed back -- FarmManager25:getProductionRows() -- and knows the SHAPE of a
-- row, not one figure, label or unit of its own. Every number was formatted in
-- core, where it is assertable headlessly; every WORD is resolved here, where
-- the i18n object lives.
--
-- ⛔ EVERY FIGURE IS FILE / AS-OF. There is no live half, so freshness is a
-- PER-TAB property and one header serves the page -- carrying TWO stamps.
-- ---------------------------------------------------------------------------

--- The bar track's inner width in the page's own pixel units, matching the
--  `size="156px 14px"` the cell template declares. ⛔ DECLARED ONCE HERE AND
--  READ BACK FROM THE ELEMENT AT RENDER TIME: the element's own resolved size
--  is the authority, and this is only the fallback for a cell whose track did
--  not load. A width guessed twice is a width that disagrees with itself.
--
--  ⚠ IT DID DISAGREE. Merging the separate IN and OUT lists into one
--  narrowed the track from 246px to 156px in the XML; this constant and the
--  line above it stayed at 246, so the fallback overstated every ratio by
--  ~58% and overflowed its own track. Only reachable when the element's size
--  is nil, which is why nothing showed it. test_draw_bar.py now reads the
--  width out of the shipped XML and fails if the two drift again -- the
--  "declared once" claim above is now enforced rather than asserted.
InGameMenuFarmManager25.BAR_TRACK_PX = 156

--- Tint one bar element from FarmManager25.THEME.bar (V-22). ⛔ THE PALETTE IS
--  NOT RE-SOURCED HERE. THEME already owns every colour this mod draws, and the
--  page reads it the same way populateCellForItemInSection reads
--  THEME.cards[severity].accent for a message row.
local function tintBar(element, key)
    if element == nil or element.setImageColor == nil then
        return
    end
    local theme = InGameMenuFarmManager25.engineTheme()
    local bar = theme ~= nil and theme.bar or nil
    local c = bar ~= nil and bar[key] or nil
    if c == nil then
        return
    end
    pcall(function() element:setImageColor(nil, c[1], c[2], c[3], c[4]) end)
end

--- ⛔⛔ THE BAR'S THREE STATES, AND TWO OF THEM LOOK IDENTICAL IF YOU GET THIS
--  WRONG (D3 rules 4 and 5, DEC-001 in pixels).
--
--    ratio == nil : UNKNOWN. Hide the TRACK ENTIRELY. The adjacent numeric cell
--                   already reads the word `unknown`; a zero-width fill inside a
--                   visible track would render "we could not ask" and "this tank
--                   is empty" the same way.
--    ratio == 0   : A REAL, MEASURED ZERO -- starved right now, the most
--                   important state on this tab. Show the TRACK, hide the FILL.
--                   The visible empty channel is exactly what distinguishes it
--                   from the case above.
--    ratio > 0    : fill width = round(trackWidth x clamp(ratio, 0, 1)).
--
--  ⚠ THE RATIO IS AGAINST A FIXED HORIZON, NOT AGAINST THE LARGEST VALUE ON
--  SCREEN -- core does that normalisation (FarmManager25.RUNWAY_HORIZON_H), and
--  it is why a half-full bar means the same thing on every point. A bar
--  normalised to the row maximum makes the healthiest chain look full and the
--  whole farm look fine.
local function drawBar(cell, ratio)
    local track = cell:getAttribute("barTrack")
    if track == nil then
        return
    end
    local fill = track:getDescendantByName("barFill")

    if ratio == nil then
        pcall(function() track:setVisible(false) end)
        if fill ~= nil then pcall(function() fill:setVisible(false) end) end
        return
    end

    pcall(function() track:setVisible(true) end)
    tintBar(track, "track")
    if fill == nil then
        return
    end
    tintBar(fill, "fill")

    if ratio <= 0 then
        pcall(function() fill:setVisible(false) end)
        return
    end
    pcall(function() fill:setVisible(true) end)
    -- ModMixer's recipe (SwitchboardFrame.lua:212-225): the fill is nested in
    -- the track, so it grows from the track's left edge, and only its WIDTH is
    -- set -- GuiElement:setSize(x, nil) keeps the current height.
    local width = (track.size ~= nil and track.size[1])
        or InGameMenuFarmManager25.BAR_TRACK_PX
    local margin = (fill.margin ~= nil and fill.margin[1]) or 0
    local usable = width - margin * 2
    if usable > 0 then
        pcall(function() fill:setSize(usable * ratio, nil) end)
    end
end

--- Render one PRODUCTIONS cell, for four lists at once. A value core flagged
--  `unknown` prints l10n text, dim. ⛔ Never blank, never an em dash, never a
--  zero, and never the producer's English reason prose.
--  ⛔ [[DEC-211]] AMENDS GUARD 8 ON THIS TAB. A REFUSED figure prints its
--  refusal tag (`rate refused`, `capacity refused`, `stock unreadable`) INSTEAD
--  of the word `unknown`; every other unknown still prints the word. This is
--  the owner's ruling, not a lapse: `unknown · capacity refused` does not fit a
--  140px cell and the engine truncates it (TextElement TRUNCATE). Do not
--  "restore" the word on a tagged cell.
function InGameMenuFarmManager25:populateProductionCell(list, index, cell)
    local unknownText = self.i18n:getText("fm25_farm_unknown")
    local function setc(name, text)
        local c = cell:getAttribute(name)
        if c ~= nil and c.setText ~= nil then c:setText(text or "") end
    end
    -- One place where "the flag decides, not the text" is enforced, so no cell
    -- on this tab can render a blank by forgetting to check.
    -- ⛔ [[DEC-199]]: the flagged cell is DIM. setc() only ever set text, so
    -- until now an `unknown` here read in the same class as a measured value
    -- -- the whole point of the ruling is that those must not look alike.
    -- One funnel for seven cells (pointRunway, ftHeld/ftRate/ftTrail,
    -- lnEnabled/lnOutput/lnLimiting), so none can be forgotten.
    -- `tagKey` (D3, [[DEC-211]]) is refusalTag()'s answer: when the cell is
    -- unknown and a refusal explains it, the tag replaces the word. Still dim.
    local function setv(name, text, unknown, tagKey)
        local shown = text
        if unknown then
            shown = tagKey ~= nil and self.i18n:getText(tagKey) or unknownText
        end
        setc(name, shown)
        InGameMenuFarmManager25.applyUnknownColor(cell:getAttribute(name),
            unknown == true)
    end
    local tag = InGameMenuFarmManager25.refusalTag

    if list == self.prodPointList then
        local p = self.prodPoints[index]
        if p == nil then return end
        setc("pointName", p.name)
        setv("pointRunway", p.runwayText, p.runwayUnknown)
        return
    end

    if list == self.prodFillList then
        local r = self.prodFillRows[index]
        if r == nil then return end
        -- ⛔ ONE POPULATOR FOR BOTH KINDS, and that is the point: a merged row
        -- has the same shape whichever half it came from, so there is no
        -- per-kind branch here that could put an output's capacity into an
        -- input's burn-rate column.
        setc("ftLabel", r.label)
        setc("ftTag", self.i18n:getText(r.tagKey or ""))
        -- M4 `.tag` / `.tag.out`: an IN tag is a quiet --rowB pill with --brt
        -- text; an OUT tag is an ACCENT pill with dark text, so the two halves
        -- of one merged list read apart at a glance.
        do
            local out = (r.kind == "out")
            local pill = cell:getAttribute("ftTagBg")
            local fill = out and InGameMenuFarmManager25.themeColor("cards", "ok", "accent")
                or InGameMenuFarmManager25.themeColor("bar", "track")
            if pill ~= nil and pill.setImageColor ~= nil and fill ~= nil then
                pill:setImageColor(nil, fill[1], fill[2], fill[3], fill[4])
            end
            local tag = cell:getAttribute("ftTag")
            local ink = out and InGameMenuFarmManager25.themeColor("text", "onAccent")
                or InGameMenuFarmManager25.themeColor("text", "title")
            if tag ~= nil and ink ~= nil then
                tag.textColor = ink
            end
        end
        -- ⛔ [[DEC-197]] REACHES THE SCREEN HERE AND NOWHERE ELSE. STOCK_RENDER,
        -- stockState() and stockRender() were built, unit-tested and joined to
        -- NOTHING: this populator never read `r.state`, so a line the player
        -- never started and a line that has genuinely run dry rendered
        -- IDENTICALLY -- the exact distinction [[DEC-202]]/[[DEC-197]] exist to
        -- make. A component tested in isolation plus a caller that never calls
        -- it is a green suite and a dead feature.
        --
        -- ⚠ INPUTS ONLY, AND THIS IS LOAD-BEARING. buildFillTypeRows gives
        -- OUT rows no `state` on purpose (the ruling is about an absent INPUT),
        -- and stockRender(nil) falls back to `unknown`, whose rule sets
        -- word=true. Applying this to outputs would print the unknown WORD over
        -- every output's real litres. The kind decides; never the nil-ness.
        if r.kind == InGameMenuFarmManager25.FILL_KIND_IN then
            local render = InGameMenuFarmManager25.stockRender(r.state)
            -- stockState() already folds heldUnknown/absent into STOCK_UNKNOWN,
            -- so `word` is the whole unknown test for an input.
            setv("ftHeld", r.heldText, render.word == true, tag("ftHeld", r))
            InGameMenuFarmManager25.applyStockColor(
                cell:getAttribute("ftHeld"), render)
        else
            setv("ftHeld", r.heldText, r.heldUnknown, tag("ftHeld", r))
        end
        setv("ftRate",  r.rateText,  r.rateUnknown,  tag("ftRate", r))
        setv("ftTrail", r.trailText, r.trailUnknown, tag("ftTrail", r))
        -- ⛔ NO BAR when the ratio is unknown, and an EMPTY bar in a visible
        -- track when it is a measured zero. drawBar already separates them.
        drawBar(cell, r.ratio)

        -- [[DEC-195]]: the product's OWN game icon, resolved by TOKEN, with
        -- our atlas glyph DIMMED as the fallback. ⛔ The fallback is REQUIRED,
        -- not optional -- the reference mod's version HIDES the icon, and a
        -- 28px hole reads as a broken cell. Never blank, and never another
        -- product's picture.
        local glyph = cell:getAttribute("ftGlyph")
        if glyph ~= nil then
            if not InGameMenuFarmManager25.setFillTypeIcon(glyph, r.ft) then
                InGameMenuFarmManager25.setGlyph(glyph, "supply",
                    InGameMenuFarmManager25.themeColor("text", "placeholder"))
            end
        end
        return
    end

    if list == self.prodLineList then
        local r = self.prodLines[index]
        if r == nil then return end
        setc("lnName", r.name)
        -- ⛔ On / Off, NEVER Running / Idle. See the core seam and the page XML:
        -- `enabled` is "is this line switched on", read from placeables.xml.
        -- "Is it producing right now" is a different fact and is killed.
        local enabledText = nil
        if not r.enabledUnknown then
            enabledText = self.i18n:getText(r.enabled and "fm25_prod_on" or "fm25_prod_off")
        end
        setv("lnEnabled", enabledText, r.enabledUnknown)
        setv("lnOutput", r.outText, r.outUnknown, tag("lnOutput", r))
        setv("lnLimiting", r.limitingText, r.limitingUnknown)
        return
    end

    -- ⛔ NO FALL-THROUGH ANY MORE. This used to end by assuming anything that
    -- reached here was prodOutputList and populating it from self.prodOutputs:
    -- the same "borrow another list's rows" shape the section registry was
    -- built to kill, surviving one method along in the populator. An
    -- unrecognised list now draws NOTHING.
end

--- Render one FIELDS master-list cell. GUARD 8 lives here: a value core flagged
--  `unknown` prints the WORD, from l10n. ⛔ Never blank, never an em dash.
--  ⚠ EXCEPT the contract cell, where BLANK IS THE ANSWER: "this field is under
--  no contract" is a real, complete answer and must not read `unknown`. The two
--  are told apart by `contractKnown`, never by the emptiness of `contract`.
function InGameMenuFarmManager25:populateFieldCell(index, cell)
    local row = self.fieldRows[index]
    if row == nil then
        return
    end
    local unknownText = self.i18n:getText("fm25_farm_unknown")
    local function setc(name, text)
        local c = cell:getAttribute(name)
        if c ~= nil and c.setText ~= nil then c:setText(text or "") end
    end

    -- ⛔ THE `(n)` MARKER MEANS "this row sums n savegame parcels", from #subIds
    -- and never from merge state -- so an unmarked row is a true statement.
    local name = row.name or ""
    if row.merged then
        name = name .. string.format(" (%d)", row.subCount)
    end
    setc("fName", name)
    -- [[DEC-195]] ICONS-2: the crop's OWN picture, resolved by TOKEN, with our
    -- atlas glyph DIMMED as the fallback. cropToken is absent for a field with
    -- no crop, an unknown crop, or a merged field whose parts disagree -- all
    -- three take the fallback, which is exactly what the ruling asks for.
    local fGlyph = cell:getAttribute("fGlyph")
    if fGlyph ~= nil then
        if not InGameMenuFarmManager25.setFillTypeIcon(fGlyph, row.cropToken) then
            InGameMenuFarmManager25.setGlyph(fGlyph, "crop",
                InGameMenuFarmManager25.themeColor("text", "placeholder"))
        end
    end

    -- ⛔ [[DEC-199]] IS A COLOUR RULE AND setc() NEVER TOUCHED COLOUR, so
    -- every `unknown` in this master list rendered in the row's normal class
    -- while the detail pane beside it dimmed the same fact. setu() is setc
    -- plus the one colour decision.
    local function setu(name, text, unknown)
        setc(name, text)
        InGameMenuFarmManager25.applyUnknownColor(cell:getAttribute(name), unknown)
    end

    setu("fArea", row.areaUnknown and unknownText or row.areaText,
        row.areaUnknown == true)
    if row.ownedUnknown then
        setu("fOwned", unknownText, true)
    else
        setu("fOwned", self.i18n:getText(row.owned and "fm25_field_yes" or "fm25_field_no"), false)
    end
    -- ⚠ THREE CASES, AND ONLY THE FIRST IS DIM. "" here means "under NO
    -- contract" -- a real answer that must stay in the normal class.
    if not row.contractKnown then
        setu("fContract", unknownText, true)
    elseif row.hasContract then
        setu("fContract", row.contract or unknownText, row.contract == nil)
    else
        setu("fContract", "", false)
    end
end


--- ⭐ THE ONE READ for this tab. Called from switchTab() into PRODUCTIONS and
--  from nowhere else, ever -- the cadence the seam declares. Rebuilt per call.
function InGameMenuFarmManager25:refreshProductionData()
    local rows, meta = {}, nil
    if FarmManager25 ~= nil and FarmManager25.getProductionRows ~= nil then
        rows, meta = FarmManager25:getProductionRows()
    end
    self.prodPoints = rows or {}
    self.prodMeta = meta or { status = "unavailable" }

    -- ⛔ TWO STAMPS, RENDERED, NOT ONE. `generatedAt` covers every
    -- savegame-derived figure and `defsAsOf` every definition-derived one, and
    -- they can differ by WEEKS -- the definitions cache is regenerated only
    -- when the owner runs a 900-second install-tree walk. A missing stamp reads
    -- `unknown`; it must NEVER read as "as of just now".
    if self.prodAsOfText ~= nil then
        local text = ""
        if self.prodMeta.status == "ok" then
            local unknownText = self.i18n:getText("fm25_farm_unknown")
            text = self.i18n:getText("fm25_farm_asof") .. " "
                .. (self.prodMeta.asOfText or unknownText)
                .. "   " .. self.i18n:getText("fm25_prod_defsasof") .. " "
                .. (self.prodMeta.defsAsOfText or unknownText)
        end
        self.prodAsOfText:setText(text)
    end

    -- ⛔ TWO EMPTY STATES, AND THEY ARE DIFFERENT FACTS. `status ~= "ok"` means
    -- WE could not ask -- nothing published, unreadable, or another savegame's
    -- document -- and names our gap. An empty list under `status == "ok"` is a
    -- real answer about the player's farm. Rendering the first as the second is
    -- the failure fm25_fields_empty was written to prevent.
    local unavailable = (self.prodMeta.status ~= "ok")
    -- EMPTY-3: the CARD is what shows and hides; the Text inside it stays
    -- visible and is hidden by its parent, which is what lets the Text keep
    -- its id and its static $l10n_ reference under the parity gate.
    if self.prodUnavailableCard ~= nil then
        self.prodUnavailableCard:setVisible(unavailable)
    end
    -- EMPTY-3: the CARD is what shows and hides; the Text inside it stays
    -- visible and is hidden by its parent, which is what lets the Text keep
    -- its id and its static $l10n_ reference under the parity gate.
    if self.prodNoneCard ~= nil then
        self.prodNoneCard:setVisible(not unavailable and #self.prodPoints == 0)
    end


    -- FOOTER-2 + [[DEC-198]]. The wording names BOTH counts, and the
    -- unmeasurable tail is dropped only when there is genuinely nothing
    -- unmeasurable -- "0 unmeasurable" is noise, but hiding a real 14 is the
    -- misreading the ruling exists to stop.
    -- ⛔ SORT BEFORE THE LIST IS READ. See refreshFieldData for the full
    -- reasoning: reloadData() and selectProductionPoint(1) both read this
    -- array, so both must run AFTER the sort or the tiles and detail pane
    -- describe a different point from the highlighted row.
    local col, desc = self:currentSort("productions")
    if col ~= nil then
        self.prodPoints = InGameMenuFarmManager25.sortRows(
            self.prodPoints, "productions", col, desc)
    end

    if self.prodPointList ~= nil then
        self.prodPointList:reloadData()
    end
    self:selectProductionPoint(1)

    -- ⛔ GATED ON status == "ok", EXACTLY AS THE AS-OF STAMP ABOVE IS. See
    -- refreshFieldData's footer for the full reasoning: an empty prodPoints
    -- under `unavailable` means WE COULD NOT ASK, and "TOTAL · 0 points · 0 of
    -- 0 under 24 h" states a measurement we never made ([[DEC-001]]).
    if unavailable then
        self:setFooter(self.prodFooterText, {}, self.prodFooterLabel)
        return
    end

    local f = InGameMenuFarmManager25.buildProductionFooter(self.prodPoints)
    local cutoff = FarmManager25 ~= nil and FarmManager25.RUNWAY_CUTOFF_H or 24
    local runway
    if f.unmeasurable > 0 then
        runway = self:fmt("fm25_footer_runway_unmeasurable",
            f.urgent, f.measurable, cutoff, f.unmeasurable)
    else
        runway = self:fmt("fm25_footer_runway", f.urgent, f.measurable, cutoff)
    end
    self:setFooter(self.prodFooterText, {
        self.i18n:getText("fm25_footer_total"),
        self:fmt("fm25_footer_points", f.total),
        runway,
    }, self.prodFooterLabel)
end

--- Master-list selection -> detail refresh. Adapted from
--  DistributionProductionsPage.lua:279-289 -> :180-199 (selectAsset), including
--  its `setSelectedIndex(1)` open state inside a pcall.
--  ⛔ THE THREE DETAIL LISTS ARE ALWAYS REBUILT, INCLUDING TO EMPTY. A point
--  with no configured line has no line rows and no output rows, and leaving the
--  previous point's rows on screen would attribute one building's production to
--  another. Four such points exist on this farm.
--- ⛔ P-8: name the selected point above its own figures.
function InGameMenuFarmManager25:setProductionDetailTitle(point)
    if self.prodDetailTitle == nil then
        return
    end
    -- Blank, never the previous point's name, when nothing is selected.
    self.prodDetailTitle:setText(point ~= nil and (point.name or "") or "")
end

function InGameMenuFarmManager25:selectProductionPoint(index)
    local point = self.prodPoints[index]
    self.prodIndex = index
    self.prodLines = point ~= nil and point.lines or {}
    -- ⛔ ONE MERGED ARRAY, BUILT ONCE PER SELECTION. The two halves used to be
    -- two lists reading point.inputs and point.outputs directly. The merge
    -- happens HERE rather than inside the populator so the engine cannot be
    -- given a different row count halfway through one rebuild.
    self.prodFillRows = InGameMenuFarmManager25.buildFillTypeRows(point)
    self:setProductionDetailTitle(point)

    for _, list in pairs({ p1 = self.prodFillList, p2 = self.prodLineList }) do
        if list ~= nil then
            list:reloadData()
        end
    end
end

-- ---------------------------------------------------------------------------
-- FIELDS (items C1, C2, C3, C5). Master-detail over one SmoothList and a
-- BoxLayout of cloned detail rows.
--
-- ⛔ ZERO ENGINE READS FOR THE FIGURES. This renders what ONE core function
-- handed back -- FarmManager25:getFieldRows() -- and knows the SHAPE of a row,
-- not one figure, label or unit of its own. Every number was formatted in core,
-- where it is assertable headlessly; every WORD is resolved here, where the
-- i18n object lives.
--
-- ⛔ FRESHNESS IS PER CELL. Three columns are FILE/AS-OF under one header stamp;
-- the contract column is LIVE and says so in-cell.
-- ---------------------------------------------------------------------------

--- ⭐ THE ONE READ for this tab. Called from switchTab() into FIELDS and from
--  nowhere else, ever. Rebuilt per call, so the LIVE contract column is live.
--  ⛔ IT DOES NOT SHARE FARM'S READ MOMENT, and that is deliberate: FARM's F-1
--  defect was two figures on ONE screen disagreeing (the header chip and row
--  a1). Nothing on this page is visible from another tab, so there is no second
--  figure to keep in step and no reason to pay a file read on every switch.
function InGameMenuFarmManager25:refreshFieldData()
    local rows, meta = {}, nil
    if FarmManager25 ~= nil and FarmManager25.getFieldRows ~= nil then
        rows, meta = FarmManager25:getFieldRows()
    end
    rows = rows or {}
    self.fieldMeta = meta or { status = "unavailable" }

    -- ⛔ OWNED-ONLY IS A FILTER OVER THE PUBLISHED ROWS, NEVER A SECOND FETCH.
    -- The seam publishes all 104 with `owned` on each; the owner's scope for
    -- this tab is "the users field he owns", and 104 rows of which 26 are his
    -- would bury them. The constant lives in core so a live test can flip it.
    -- ⚠ `ownedUnknown` rows are KEPT. Dropping a field because we could not
    -- resolve its ownership would hide it entirely -- absence rendered as a
    -- shorter list, with nothing on screen to say a row went missing.
    self.fieldRows = {}
    for _, row in ipairs(rows) do
        if not FarmManager25.FIELDS_OWNED_ONLY or row.owned ~= false then
            table.insert(self.fieldRows, row)
        end
    end

    if self.fieldAsOfText ~= nil then
        local text = ""
        if self.fieldMeta.status == "ok" then
            text = self.i18n:getText("fm25_farm_asof") .. " "
                .. (self.fieldMeta.asOfText
                    or self.i18n:getText("fm25_farm_unknown"))
        end
        self.fieldAsOfText:setText(text)
    end

    -- ⛔ TWO EMPTY STATES, AND THEY ARE DIFFERENT FACTS. `status ~= "ok"` means
    -- WE could not ask -- nothing published, unreadable, or another savegame's
    -- document -- and the existing line names OUR gap. An empty list under
    -- `status == "ok"` is a real answer about the player's farm. Rendering the
    -- first as the second would put "you own no fields" in front of a man who
    -- owns twenty-six.
    local unavailable = (self.fieldMeta.status ~= "ok")
    -- EMPTY-3: the CARD is what shows and hides; the Text inside it stays
    -- visible and is hidden by its parent, which is what lets the Text keep
    -- its id and its static $l10n_ reference under the parity gate.
    if self.fieldsEmptyCard ~= nil then
        self.fieldsEmptyCard:setVisible(unavailable)
    end
    -- EMPTY-3: the CARD is what shows and hides; the Text inside it stays
    -- visible and is hidden by its parent, which is what lets the Text keep
    -- its id and its static $l10n_ reference under the parity gate.
    if self.fieldsNoneCard ~= nil then
        self.fieldsNoneCard:setVisible(not unavailable and #self.fieldRows == 0)
    end

    -- ⛔ SORT BEFORE THE LIST IS READ, and remember it across refreshes
    -- (chosen.html FIELDS: "remember the chosen column and direction").
    -- With no column chosen this returns the rows untouched, so the default
    -- order is still core's published order and not an invented one.
    --
    -- ⚠ THIS COMMENT USED TO SIT BELOW THE TWO CALLS IT DESCRIBES, asserting
    -- the invariant the code broke. reloadData() told the engine to render the
    -- UNSORTED array and selectField(1) built the detail pane and all six
    -- headline tiles from the UNSORTED first row, while the highlight sat on
    -- row 1 of the sorted order -- two different fields on one screen, under
    -- one highlight. MESSAGES always did this correctly (sort, THEN
    -- reloadData); FIELDS and PRODUCTIONS were the two parity halves that
    -- diverged. Ordering is the whole content of this block: keep the sort
    -- above both calls.
    local col, desc = self:currentSort("fields")
    if col ~= nil then
        self.fieldRows = InGameMenuFarmManager25.sortRows(
            self.fieldRows, "fields", col, desc)
    end

    if self.fieldList ~= nil then
        self.fieldList:reloadData()
    end
    self:selectField(1)

    -- FOOTER-2. Counts come from the SAME rows the list was just filled from.
    -- ⚠ Counts are ORDER-INDEPENDENT, so sorting first cannot change them --
    -- but they are computed after the sort anyway, so the footer can never
    -- describe a different array from the one on screen.
    -- ⛔ GATED ON status == "ok", EXACTLY AS THE AS-OF STAMP ABOVE IS.
    -- When we could not ask, self.fieldRows is empty because NOTHING WAS READ,
    -- not because the farm has no fields. buildFieldsFooter is a pure counter
    -- and its 0 is the truth ABOUT THE ARRAY IT WAS HANDED -- the defect is
    -- rendering that as a TOTAL. "TOTAL · 0 fields · 0.0 ha" printed beside a
    -- card saying we could not read anything is absence rendered as data
    -- ([[DEC-001]], [[RSK-001]]), and the footer is the more believable of the
    -- two because it carries numbers. Blank, exactly as the stamp blanks.
    if unavailable then
        self:setFooter(self.fieldsFooterText, {}, self.fieldsFooterLabel)
        return
    end

    local f = InGameMenuFarmManager25.buildFieldsFooter(self.fieldRows)
    local area
    if f.unknownAreas > 0 then
        -- ⛔ chosen.html FIELDS: "never count an unknown area as 0 (DEC-001).
        -- If any area is unknown the total SAYS SO". The partial sum is still
        -- shown, because it is true; what must not happen is presenting it as
        -- a total.
        area = self:fmt("fm25_footer_area_unknown",
            string.format("%.1f", f.area), f.unknownAreas)
    else
        area = self:fmt("fm25_footer_area_ha", string.format("%.1f", f.area))
    end
    self:setFooter(self.fieldsFooterText, {
        self.i18n:getText("fm25_footer_total"),
        self:fmt("fm25_footer_fields", f.count),
        area,
    }, self.fieldsFooterLabel)
end

--- chosen.html `.bt2`: the gap between the field name and its crop.
InGameMenuFarmManager25.SUBTITLE_GAP_PX = 14

-- ---------------------------------------------------------------------------
-- F12 (BUG-041, BUG-030 FIELDS, N12): crop and ground TOKENS are shown as words.
--
-- Core publishes the raw upper-case save token (`OAT`, `UNKNOWN`, `ROLLER_LINES`) --
-- it is pure and cannot translate, and the row icon resolves by the token. THIS side
-- turns a token into what the player reads.
-- ---------------------------------------------------------------------------

--- The save's crop token for BARE GROUND. `crop="UNKNOWN"` always comes from the save
--  (our producers never write it) and means no crop is planted; a value we could not
--  READ omits the attribute entirely and renders the dim `unknown` word instead.
InGameMenuFarmManager25.NO_CROP_TOKEN = "UNKNOWN"

--- Ground token -> OUR l10n key. Ground states are not fill types, so the engine has
--  no title to lend; these are ours ([[DEC-211]]/D-13: English copies marked
--  UNTRANSLATED in de/es/fr/pl). The set is what the saves carry; a token outside it
--  falls back to itself, never to a blank.
--  ⛔ D-5: HARVEST_READY and HARVEST_READY_OTHER are labelled as a plain ground STATE,
--  never as a harvest instruction -- the marker is REFUTED as a ripeness signal (it stays
--  set days after harvest; FarmManager25.lua:3283-3285, read_fields.py:307-309).
InGameMenuFarmManager25.GROUND_LABEL_KEYS = {
    NONE               = "fm25_ground_none",
    STUBBLE_TILLAGE    = "fm25_ground_stubble_tillage",
    CULTIVATED         = "fm25_ground_cultivated",
    PLOWED             = "fm25_ground_plowed",
    SOWN               = "fm25_ground_sown",
    DIRECT_SOWN        = "fm25_ground_direct_sown",
    RIDGE              = "fm25_ground_ridge",            -- ridged, not yet sown (SowingMachine.lua:202-203)
    RIDGE_SOWN         = "fm25_ground_ridge_sown",
    PLANTED            = "fm25_ground_planted",
    ROLLER_LINES       = "fm25_ground_roller_lines",
    GRASS              = "fm25_ground_grass",
    SEEDBED            = "fm25_ground_seedbed",          -- TD-165: engine FieldGroundType states
    ROLLED_SEEDBED     = "fm25_ground_rolled_seedbed",   -- not in the 5 saves read so far
    GRASS_CUT          = "fm25_ground_grass_cut",        -- (MapOverlayGenerator:276,278; WheelPhysics:867)
    HARVEST_READY      = "fm25_ground_harvest_state",
    HARVEST_READY_OTHER = "fm25_ground_harvest_state_other",
}

--- ⭐ One token in, the words out. `key` is the FIELD_DETAIL_SPEC key: only `crop` and
--  `ground` carry translatable tokens; every other key is returned untouched.
--
--  ⛔ THE "No crop" TEST COMES BEFORE THE FILL-TYPE TITLE LOOKUP, AND THE ORDER IS THE
--  WHOLE FIX. The engine REGISTERS a fill type named UNKNOWN whose title is the
--  hard-coded English "Unknown" (FillTypeDesc.lua:21-22; FillTypeManager.lua:203-207),
--  so getFillTypeByName("UNKNOWN").title SUCCEEDS -- a lookup-first render prints
--  "Unknown" for bare ground, in every language.
--
--  Crop names are the engine's OWN fill-type title (FillTypeManager.lua:512-515; the
--  engine displays that title directly): zero new strings, and it covers mod crops no key
--  of ours could. An unregistered token falls back to itself -- visible, never blank.
function InGameMenuFarmManager25.fieldValueLabel(key, token, i18n)
    if type(token) ~= "string" or token == "" then
        return token
    end
    if key == "crop" then
        if token == InGameMenuFarmManager25.NO_CROP_TOKEN then
            return i18n:getText("fm25_field_no_crop")
        end
        if g_fillTypeManager ~= nil then
            local ok, desc = pcall(g_fillTypeManager.getFillTypeByName, g_fillTypeManager, token)
            if ok and desc ~= nil and type(desc.title) == "string" and desc.title ~= "" then
                return desc.title
            end
        end
        return token
    elseif key == "ground" then
        local labelKey = InGameMenuFarmManager25.GROUND_LABEL_KEYS[token]
        if labelKey ~= nil then
            return i18n:getText(labelKey)
        end
        return token
    end
    return token
end

--- A merged field whose sub-parcels DISAGREE, as words: "45 Oat  46 Oat  36 No crop".
--  Built from core's structured `parts` (F12); `partsText` is the fallback for a row
--  that carries none, so a disagreement is never blank. Same layout core uses: the
--  sub-id, a space, the value, two spaces between parts; a sub-parcel that reported
--  nothing is `?`.
function InGameMenuFarmManager25.partsLabel(key, parts, partsText, i18n)
    if type(parts) ~= "table" or #parts == 0 then
        return partsText or ""
    end
    local out = {}
    for _, p in ipairs(parts) do
        local v = p.value
        out[#out + 1] = tostring(p.sub) .. " "
            .. (v ~= nil and tostring(InGameMenuFarmManager25.fieldValueLabel(key, v, i18n)) or "?")
    end
    return table.concat(out, "  ")
end

--- DEC-214: the FIELDS detail subtitle for a row. Returns (text, dim).
--  A disagreement is a MEASUREMENT (M1) and renders bright; an unknown crop,
--  or a row that carries no crop entry at all, says `unknown` in the dim
--  class. Absence never renders as a blank.
--  F12: a crop is shown by NAME, and bare ground says "No crop" -- a real answer, so
--  it is bright; only a crop we could not READ is the dim `unknown`.
function InGameMenuFarmManager25.cropSubtitle(row, i18n)
    local crop = nil
    for _, d in ipairs(row.detail or {}) do
        if d.key == "crop" then
            crop = d
            break
        end
    end
    if crop ~= nil and crop.differs then
        return i18n:getText("fm25_field_differs") .. " "
            .. InGameMenuFarmManager25.partsLabel("crop", crop.parts, crop.partsText, i18n), false
    end
    if crop == nil or crop.unknown or crop.text == nil or crop.text == "" then
        return i18n:getText("fm25_farm_unknown"), true
    end
    return InGameMenuFarmManager25.fieldValueLabel("crop", crop.text, i18n), false
end

--- M4 `.ctr`: the FIELDS contract box. `text` nil hides the whole box (no
--  field selected); otherwise it shows `text` -- dim only when `dim` (the
--  unreadable case), brt otherwise -- then LIVE 12px after it.
function InGameMenuFarmManager25:renderContractBox(text, dim)
    local parts = { self.fieldContractBox, self.fieldContractGlyph, self.fieldContractLabel,
                    self.fieldContractText, self.fieldContractFresh }
    for _, e in ipairs(parts) do
        if e ~= nil then
            e:setVisible(text ~= nil)
        end
    end
    if text == nil then
        return
    end
    local value = self.fieldContractText
    if value ~= nil then
        value:setText(text)
        local color = InGameMenuFarmManager25.themeColor("text", dim and "placeholder" or "title")
        if color ~= nil then
            value.textColor = color
        end
        InGameMenuFarmManager25.placeAfter(value, self.fieldContractLabel, 12, false)
    end
    InGameMenuFarmManager25.placeAfter(self.fieldContractFresh, value, 12, false)
    local cards = InGameMenuFarmManager25.themeColor("cards")
    InGameMenuFarmManager25.setGlyph(self.fieldContractGlyph, "contract",
        cards ~= nil and cards.info ~= nil and cards.info.accent or nil)
end

--- Master-list selection -> detail rebuild. ⛔ IT MAKES NO ENGINE CALL AND NO
--  FILE READ: the rows were fetched once by refreshFieldData().
function InGameMenuFarmManager25:selectField(index)
    self.selectedFieldIndex = index
    local row = self.fieldRows ~= nil and self.fieldRows[index] or nil

    -- The six tiles follow the selection. buildFieldTiles returns six for a
    -- nil row too -- all flagged unknown -- so deselecting empties the tiles
    -- rather than leaving the previous field's figures on screen.
    local tiles = InGameMenuFarmManager25.buildFieldTiles(row)
    for i = 1, 6 do
        self:renderTile(self["fieldTile" .. i], tiles[i])
    end
    if row == nil then
        self:renderContractBox(nil)
    end

    -- M4: chosen.html FIELDS `.bt2` opens with the CROP'S OWN PICTURE
    -- ("Detail title: atlas glyph + Text ..."). Exactly the row icon's rule
    -- (ICONS-2 / DEC-195): the crop's hudOverlayFilename by token, else our
    -- atlas glyph DIMMED. Hidden when nothing is selected, never stale.
    if self.fieldDetailGlyph ~= nil then
        self.fieldDetailGlyph:setVisible(row ~= nil)
        if row ~= nil and not InGameMenuFarmManager25.setFillTypeIcon(
                self.fieldDetailGlyph, row.cropToken) then
            InGameMenuFarmManager25.setGlyph(self.fieldDetailGlyph, "crop",
                InGameMenuFarmManager25.themeColor("text", "placeholder"))
        end
    end

    if self.fieldDetailTitle ~= nil then
        local title = ""
        if row ~= nil then
            title = row.name or ""
            -- ⛔ THE MARKER MEANS EXACTLY "this row sums n savegame parcels",
            -- derived from #subIds and NEVER from merge state. Under that
            -- definition an UNMARKED row is a true statement, not an omission --
            -- which is what makes the two PLANNED merges correct as plain rows.
            if row.merged then
                title = title .. string.format(" (%d)", row.subCount)
            end
        end
        self.fieldDetailTitle:setText(title)
    end

    -- ⛔⛔ DEC-214 (owner ruling 2026-09-17): the crop is the title's SUBTITLE,
    -- at NORMAL weight, and the separate Crop row is dropped (skipped below).
    -- chosen.html `.bt2 .sub` colours it with the dim class; DEC-199 reserves
    -- dim for "we cannot tell", so a KNOWN crop takes text.body. An unknown
    -- or missing crop still SAYS `unknown`, dim -- never a blank subtitle.
    if self.fieldDetailCrop ~= nil then
        local crop = self.fieldDetailCrop
        crop:setVisible(row ~= nil)
        if row == nil then
            crop:setText("")
        else
            local text, dim = InGameMenuFarmManager25.cropSubtitle(row, self.i18n)
            crop:setText(text)
            local color = InGameMenuFarmManager25.themeColor("text", dim and "placeholder" or "body")
            if color ~= nil then
                crop.textColor = color
            end
            -- `.bt2`: name, a 14px gap, then the crop -- placed from the name's
            -- MEASURED width, so a longer name pushes it right.
            InGameMenuFarmManager25.placeAfter(crop, self.fieldDetailTitle,
                InGameMenuFarmManager25.SUBTITLE_GAP_PX, false)
        end
    end

    local box, template = self.fieldDetailBox, self.fieldDetailRowTemplate
    if box == nil or template == nil then
        return
    end
    while #box.elements > 0 do
        box.elements[1]:delete()
    end
    if row == nil then
        box:invalidateLayout()
        return
    end

    local unknownText = self.i18n:getText("fm25_farm_unknown")
    --- ⛔ `dim` IS [[DEC-199]], AND IT IS NOT DECORATION. The design teaches
    --  bright = a real answer, dim = we cannot tell. Two kinds of cell are
    --  dim here and they are dim for the SAME reason even though they are
    --  different facts:
    --    - `unknown`      -- we asked the save and it could not tell us
    --    - OUR GAP        -- we never built the transport ("Not available yet.")
    --  Rendering either in the bright class makes the page look like it knows
    --  something it does not, which is what the ruling exists to stop. The
    --  WORDS still distinguish the two -- `unknown` blames the data, "Not
    --  available yet." blames us -- and that distinction is deliberate and
    --  must survive; only the COLOUR is shared.
    --  Reuses the exact palette entry setUnknownAwareText uses, so one dim
    --  cannot drift from the other.
    local function line(labelText, valueText, dim)
        local element = template:clone(box)
        element:setVisible(true)
        local label = element:getDescendantByName("dLabel")
        local value = element:getDescendantByName("dValue")
        if label ~= nil then label:setText(labelText or "") end
        if value ~= nil then
            value:setText(valueText or "")
            local theme = InGameMenuFarmManager25.engineTheme()
            if theme ~= nil and theme.text ~= nil then
                local color = dim and theme.text.placeholder or theme.text.body
                if color ~= nil then
                    value.textColor = color
                end
            end
        end
    end

    -- Block 1: field state, all FILE / AS-OF.
    -- ⛔⛔ FI-10 / BNA-1: A ROW WHOSE VALUE A TILE ALREADY SHOWS IS SKIPPED.
    -- The six tiles above and this list were both fed from row.detail, so
    -- GROWTH STAGE / WEEDS / PLOUGH LEVEL / LIME LEVEL rendered TWICE on one
    -- pane, and the conformance lane found the duplication is what pushes the
    -- Contract row off the bottom of the page.
    --
    -- ⛔ THE SKIP SET IS DERIVED FROM FIELD_TILES, NEVER RESTATED. A second
    -- hard-coded list of four keys is how the tiles and this list would drift
    -- apart the first time a tile is added or removed: add one and its row
    -- silently comes back, remove one and its value vanishes from the page
    -- entirely. Deriving it means the two CANNOT disagree.
    --
    -- ⛔ WHY THIS IS SAFE TO DELETE, CHECKED BRANCH BY BRANCH RATHER THAN BY
    -- EYE. The analogous "obvious dedup" on PRODUCTIONS would have deleted two
    -- buildings the owner owns (27 points, 27 unique ids, the apparent pair
    -- showing DIFFERENT values), so "these look the same" is not evidence.
    -- Here the tile and the row read the SAME row.detail entry, and every one
    -- of the three branches carries the same information:
    --   normal   tile value = d.text            row = d.text
    --   unknown  tile dim `unknown`             row dim `unknown`
    --   differs  tile value = the `differs` word AND tile HINT = d.partsText
    --            row = the `differs` word .. d.partsText
    -- The differs case is the one that looked unsafe -- the tile appears to
    -- show only "differs" while the row shows the full breakdown -- and it is
    -- the case that had to be checked in the code rather than in the
    -- screenshot, where the R6 displacement and the clipped detail pane hide
    -- the hint line. All six fieldTile elements DO carry a tHint child, and
    -- renderTile sets it to tile.valueText (= partsText) on a disagreement, so
    -- the breakdown survives the deletion.
    -- ⚠ NOT SKIPPED: `ground` backs no tile.
    -- ⛔ `crop` IS SKIPPED BY DEC-214: it renders as the title's subtitle
    -- above, which is now the place MAIZE appears on the pane.
    local tileBacked = { crop = true }
    for _, spec in ipairs(InGameMenuFarmManager25.FIELD_TILES) do
        if spec.detail ~= nil then
            tileBacked[spec.detail] = true
        end
    end

    for _, d in ipairs(row.detail or {}) do
      if not (d.key ~= nil and tileBacked[d.key]) then
        local text
        if d.differs then
            -- ⛔ A MERGED ROW REPORTS DISAGREEMENT **AS DISAGREEMENT** -- never by
            -- silently picking the canonical sub-id's answer, never by averaging,
            -- never by majority vote. The house rule says a merged field carries
            -- exactly one crop across all its sub-parcels, so a disagreement
            -- MEANS something and hiding it discards a signal.
            -- ⚠ Live today on field #45: 45 OAT · 46 OAT · 36 UNKNOWN.
            text = self.i18n:getText("fm25_field_differs") .. " "
                .. InGameMenuFarmManager25.partsLabel(d.key, d.parts, d.partsText, self.i18n)
        elseif d.unknown then
            text = unknownText
        else
            -- F12: `ground` (and `crop`, should it ever be listed) is shown as words.
            text = InGameMenuFarmManager25.fieldValueLabel(d.key, d.text, self.i18n)
        end
        -- ⛔ DO NOT "FIX" THIS TO DIM THE DISAGREEMENT. Confirmed as the
        -- intended behaviour 2026-09-12, and it reads like an oversight, so
        -- the reasoning is here rather than in a commit message.
        -- An unknown is dim. A DISAGREEMENT IS NOT: "45 OAT / 46 OAT / 36
        -- UNKNOWN" is a real, MEASURED finding about a real disagreement, not
        -- an admission of ignorance. Dimming it would file a measurement under
        -- "we cannot tell" -- [[DEC-001]] inverted, which is the same defect
        -- the production rows were fixed for today (data rendered as absence).
        -- ⭐ AND THE TWO DIM CLASSES SHARE ONLY THE COLOUR. The WORDS still
        -- separate "we asked and could not find out" (`unknown`) from "we
        -- never built the pipe" ("Not available yet."), and that separation is
        -- what makes the convention survive contact with a real page. Collapse
        -- the words and the colour stops meaning anything.
        -- Live today on field #45.
        line(self.i18n:getText(d.labelKey), text, d.unknown == true)
      end
    end

    -- Block 2: planned next crop, as the emitter published it. FOUR states a player can
    -- tell apart, in words true of THIS field. DEC-199: bright = a real answer (a plan, or
    -- "no plan yet" -- a gap is a finding), dim = we could not tell. A document with no
    -- <plan> element at all (an older emitter) keeps the old words: OUR gap, never `none`.
    local planText, planDim = InGameMenuFarmManager25.planLine(row.plan, self.i18n)
    line(self.i18n:getText("fm25_field_d_planned"), planText, planDim)

    -- Block 3, first line: merge status. ⛔ Derived from the row; a single field
    -- renders NOTHING here, not `unknown` -- "this field is not merged" is not a
    -- question anyone asked.
    if row.merged then
        line(self.i18n:getText("fm25_field_d_merged"),
             string.format(self.i18n:getText("fm25_field_merged_fmt"),
                           row.subCount, table.concat(row.subIds, " ")))
    end

    -- Block 3, rest: the field's notes (its dossier's `## Notes / quirks`), same rule.
    local notesText, notesDim = InGameMenuFarmManager25.notesLine(row.notes, self.i18n)
    line(self.i18n:getText("fm25_field_d_notes"), notesText, notesDim)

    -- C5: the contract, with its own LIVE mark because it is the one cell on
    -- this page that is not as-of.
    local contractText
    local contractDim = false
    if not row.contractKnown then
        contractText = unknownText
        contractDim = true
    elseif row.hasContract then
        -- ⚠ A CONTRACT WE FOUND BUT COULD NOT NAME still reads `unknown`, never
        -- blank: we know there IS one, and a blank would say there is not.
        contractText = row.contract or unknownText
        contractDim = row.contract == nil
        if row.contractReward ~= nil then
            contractText = contractText .. "  " .. self:formatMoney(row.contractReward)
        end
    else
        -- ⛔ "no contract" IS A REAL ANSWER, never `unknown` (D-4). In this detail box it
        -- is said in words; the master-list cell (fContract) stays blank. contractKnown
        -- is already true on this branch, so the words never assert an unchecked fact.
        contractText = self.i18n:getText("fm25_field_no_contract")
    end
    -- ⛔ THE FOURTH [[DEC-199]] SITE IN THIS FUNCTION. bad42b9 dimmed the
    -- other three and stopped one line short of this one: an unreadable
    -- contract rendered `unknown` in the BRIGHT class. `contractDim` is true
    -- only for the unreadable case -- "no contract" is a real answer, said in words above.
    -- M4 `.ctr`: rendered in the contract BOX above the rows, not as a line.
    self:renderContractBox(contractText, contractDim)

    box:invalidateLayout()
end

--- The detail pane's "Planned next crop" value: (text, dim). `plan` is the row's published
--  plan fact, or nil when the document carried none (older emitter).
function InGameMenuFarmManager25.planLine(plan, i18n)
    if plan == nil then
        return i18n:getText("fm25_field_planned_unavailable"), true
    end
    if plan.state == "reviewed" or plan.state == "unreviewed" then
        local key = plan.state == "reviewed" and "fm25_field_plan_reviewed_fmt"
            or "fm25_field_plan_unreviewed_fmt"
        return string.format(i18n:getText(key), tostring(plan.crop or "?"),
            tostring(plan.window or "?")), false
    end
    if plan.state == "none" then
        return i18n:getText("fm25_field_plan_none"), false
    end
    return string.format(i18n:getText("fm25_field_plan_unknown_fmt"),
        tostring(plan.reason or "?")), true
end

--- The detail pane's "Field notes" value: (text, dim). Same contract as planLine.
function InGameMenuFarmManager25.notesLine(notes, i18n)
    if notes == nil then
        return i18n:getText("fm25_field_notes_unavailable"), true
    end
    if notes.state == "note" then
        return tostring(notes.text or "") .. (notes.truncated and "..." or ""), false
    end
    if notes.state == "none" then
        return i18n:getText("fm25_field_notes_none"), false
    end
    return string.format(i18n:getText("fm25_field_notes_unknown_fmt"),
        tostring(notes.reason or "?")), true
end

function InGameMenuFarmManager25:onFrameOpen()
    InGameMenuFarmManager25:superClass().onFrameOpen(self)
    -- switchTab() ends in refreshFarmData(), which fills the header chip from
    -- the same read as the FARM table. No separate updateBalance() call here:
    -- a second call would be a second read moment, which is the defect F-1
    -- recorded.
    -- ⛔ BEFORE switchTab: switchTab ends in the per-tab refreshes, and each
    -- one reads currentSort() to order its list. Seeding afterwards would
    -- leave the first paint in the unsorted order.
    self:applySortDefaults()
    self:switchTab(self.currentTab or InGameMenuFarmManager25.TAB_FARM)
    self:refreshSettingsRows()
    -- ⛔ X-6 / FI-4 / M-10: THE ARROWS EXISTED AND WERE NEVER SHOWN. All 18
    -- Bitmaps ship visible="false" and refreshSortArrows() was called from
    -- exactly ONE place -- inside onClickSortHeader -- so a column indicated
    -- its sort only after the player had already clicked it. On first open
    -- nothing was marked, including the default sort seeded just above.
    -- The arrows were never missing; the refresh was never reached.
    self:refreshSortArrows()
    FocusManager:setFocus(self.messageTable)
end

function InGameMenuFarmManager25:onFrameClose()
    InGameMenuFarmManager25:superClass().onFrameClose(self)
end

function InGameMenuFarmManager25:onClickTab(state)
    self:switchTab(state)
end

function InGameMenuFarmManager25:switchTab(tabIndex)
    -- ⛔ AN OUT-OF-RANGE TAB FALLS BACK TO THE FIRST TAB, named by constant.
    -- It used to fall back to TAB_MESSAGES, which WAS the first tab; leaving
    -- that literal behind would have made a bad index quietly open the fourth.
    tabIndex = tonumber(tabIndex) or InGameMenuFarmManager25.TAB_FARM
    if tabIndex < 1 or tabIndex > InGameMenuFarmManager25.NUM_TABS then
        tabIndex = InGameMenuFarmManager25.TAB_FARM
    end

    self.currentTab = tabIndex

    for i = 1, InGameMenuFarmManager25.NUM_TABS do
        if self.subCategoryTabs[i] ~= nil then
            self.subCategoryTabs[i]:setSelected(i == tabIndex)
            self:tintTab(self.subCategoryTabs[i], i == tabIndex)
        end
    end

    if self.tabContainer1 ~= nil then
        self.tabContainer1:setVisible(tabIndex == InGameMenuFarmManager25.TAB_MESSAGES)
    end
    if self.tabContainer2 ~= nil then
        self.tabContainer2:setVisible(tabIndex == InGameMenuFarmManager25.TAB_SETTINGS)
    end
    if self.tabContainer3 ~= nil then
        self.tabContainer3:setVisible(tabIndex == InGameMenuFarmManager25.TAB_FARM)
    end
    if self.tabContainer4 ~= nil then
        self.tabContainer4:setVisible(tabIndex == InGameMenuFarmManager25.TAB_FIELDS)
    end
    if self.tabContainer5 ~= nil then
        self.tabContainer5:setVisible(tabIndex == InGameMenuFarmManager25.TAB_PRODUCTIONS)
    end

    if tabIndex == InGameMenuFarmManager25.TAB_MESSAGES then
        self:updateMessages()
    end

    -- ⛔ READ ONLY WHEN PRODUCTIONS IS THE OPEN TAB -- once per switchTab into
    -- it, which is the cadence getProductionRows() declares. Unlike the FARM
    -- read below there is nothing on this page visible from another tab, so
    -- there is no chip to keep in step and no reason to pay the file read on
    -- every switch.
    if tabIndex == InGameMenuFarmManager25.TAB_FIELDS then
        self:refreshFieldData()
    end

    if tabIndex == InGameMenuFarmManager25.TAB_PRODUCTIONS then
        self:refreshProductionData()
    end

    -- RE-READ ON EVERY SWITCH, deliberately. Group A is live money; rendering a
    -- table built once at load would show an hour-old balance under the word
    -- LIVE, which is precisely what guard 7 exists to prevent. The same applies
    -- to the header chip, which is why this sits outside the branch above:
    -- currentTab is already assigned, so refreshFarmData knows whether the FARM
    -- table needs rebuilding as well.
    self:refreshFarmData()
end

-- ---------------------------------------------------------------------------
-- MESSAGE FILTERS (chosen.html MESSAGES: "Filter row: 5 Buttons with onClick,
-- the active one tinted cards.ok"; "Filters: Lua state + 5 Buttons (counts per
-- severity)")
-- ---------------------------------------------------------------------------

InGameMenuFarmManager25.FILTER_ALL = "all"

--- The five filters: ALL, then the severities in SEVERITY_ORDER (NOT the strip
--  order -- FILTER_BUTTONS holds that; both callers here are order-
--  independent). ⛔ THE FOUR SEVERITIES ARE DERIVED FROM
--  FarmManager25.SEVERITY_ORDER AT CALL TIME, never copied: a copy would keep
--  the old set silently if a severity were ever added or renamed, and the
--  filter row would then hide a whole class of message with no error. ALL is
--  prepended because it is not a severity and must not be one.
--  ⚠ Resolved lazily for the same reason footerStatusOrder is -- this file is
--  not an extraSourceFile and must not race FarmManager25.lua at load.
function InGameMenuFarmManager25.messageFilters()
    local out = { InGameMenuFarmManager25.FILTER_ALL }
    for _, sev in ipairs(FarmManager25 ~= nil
            and FarmManager25.SEVERITY_ORDER or {}) do
        out[#out + 1] = sev
    end
    return out
end

--- ⭐ PURE. Rows in, the rows that filter admits out.
--  ⛔ AN UNRECOGNISED FILTER SHOWS EVERYTHING, NOT NOTHING. A filter name that
--  no longer matches any severity would otherwise empty the tab, and an empty
--  transcript reads as "you have no messages" -- a statement about the
--  player's farm, when the truth is that our filter broke. Showing too much is
--  recoverable by eye; showing nothing is a lie.
function InGameMenuFarmManager25.filterMessages(rows, filter)
    if filter == nil or filter == InGameMenuFarmManager25.FILTER_ALL then
        return rows or {}
    end
    local known = false
    for _, f in ipairs(InGameMenuFarmManager25.messageFilters()) do
        if f == filter then known = true break end
    end
    if not known then
        return rows or {}
    end
    local out = {}
    for _, row in ipairs(rows or {}) do
        if row.severity == filter then
            out[#out + 1] = row
        end
    end
    return out
end

--- ⭐ PURE. The count beside each filter button.
--  ⛔ COUNTED OVER THE UNFILTERED ROWS, ALWAYS. Counting the filtered set would
--  make every button read 0 except the active one, so the strip would stop
--  being able to tell the player where his messages are -- which is the only
--  reason to put counts on it.
--  ⛔ A severity nobody anticipated is counted in ALL but has no button, so the
--  buttons deliberately need not sum to ALL. `ALL` is #rows, never a sum.
function InGameMenuFarmManager25.messageFilterCounts(rows)
    local counts = { [InGameMenuFarmManager25.FILTER_ALL] = 0 }
    for _, f in ipairs(InGameMenuFarmManager25.messageFilters()) do
        counts[f] = 0
    end
    for _, row in ipairs(rows or {}) do
        counts[InGameMenuFarmManager25.FILTER_ALL] =
            counts[InGameMenuFarmManager25.FILTER_ALL] + 1
        if row.severity ~= nil and counts[row.severity] ~= nil then
            counts[row.severity] = counts[row.severity] + 1
        end
    end
    return counts
end

--- ⭐ PURE. filter  ->  group by day  ->  sort WITHIN each group.
--
--  ⚠ AN EARLIER VERSION OF THIS COMMENT OVERSTATED THE SORT STEP, and the
--  correction is worth keeping. It claimed sorting the flat list before
--  grouping would give "a DIFFERENT order inside the groups". It would not:
--  buildMessageGroups is a STABLE PARTITION and the group order is decided
--  independently by day, so flat-sort-then-group and group-then-sort produce
--  identical output for every comparator we have. A mutation swapping them
--  stayed green (N5), and it stayed green because it is a NO-OP, not because
--  the suite is weak.
--  ⭐ The per-group form is still the right shape: it stays correct if the
--  grouping ever stops being stable, or if group ORDER ever becomes
--  content-dependent. But it is a design margin, not a behaviour difference,
--  and claiming otherwise would have sent the next reader hunting a bug that
--  is not there.
--
--  ⛔ THE FILTER STEP IS DIFFERENT AND ITS ORDER *IS* OBSERVABLE. Filtering
--  BEFORE grouping means a day whose every message is filtered out loses its
--  HEADING; filtering after leaves an empty DAY 7 above nothing. Mutation N6
--  reddens on that, as it should.
--  ⛔ FILTERING BEFORE GROUPING, NOT AFTER: a day whose every message is
--  filtered out must lose its HEADING too, not keep an empty one.
function InGameMenuFarmManager25.buildMessageView(rows, today, filter, column, descending)
    local kept = InGameMenuFarmManager25.filterMessages(rows, filter)
    local groups = InGameMenuFarmManager25.buildMessageGroups(kept, today)
    if column ~= nil then
        for _, group in ipairs(groups) do
            group.items = InGameMenuFarmManager25.sortRows(
                group.items, "messages", column, descending)
        end
    end
    return groups
end

-- ---------------------------------------------------------------------------
-- MESSAGE DAY GROUPS (chosen.html:631, :649, :654-656)
-- ---------------------------------------------------------------------------

InGameMenuFarmManager25.MSG_GROUP_TODAY   = "fm25_msg_group_today"
InGameMenuFarmManager25.MSG_GROUP_DAY     = "fm25_msg_group_day"
InGameMenuFarmManager25.MSG_GROUP_EARLIER = "fm25_msg_group_earlier"

--- ⭐ PURE. Zero engine references, zero l10n, zero self. Takes the published
--  message rows and today's farm day and returns the ordered day groups. Split
--  out for the same reason core split buildFarmRows() from readLiveValues():
--  this is the half a headless test can honestly gate, and it is where a
--  mutated ANSWER has to show up.
--
--  Returns an array of { day = <number|nil>, items = { row, ... } }:
--    - known days first, NEWEST DAY FIRST
--    - the unknown-day group LAST, always, whatever day numbers exist
--  Rows keep their incoming order within a group. That is deliberate and it is
--  not "unsorted": getMessageLog() publishes live-then-history, not strict
--  recency (FarmManager25.lua, the ORDER paragraph on the seam), and a page
--  that re-sorted by time here would silently claim an ordering core explicitly
--  says it does not provide.
--
--  ⛔ A ROW WITH NO DAY IS NOT DAY ZERO. `day = nil` means the clock was dead
--  when the card was stamped, or the card predates the field. Those group under
--  EARLIER -- which is exactly what chosen.html:654 specifies for cards saved
--  before the day existed -- and never under a fabricated heading. A `0` here
--  would be indistinguishable from a real day 0 on a fresh save.
function InGameMenuFarmManager25.buildMessageGroups(rows, today)
    local groups, byDay, unknown = {}, {}, nil

    for _, row in ipairs(rows or {}) do
        local day = nil
        if type(row.day) == "number" then
            day = math.floor(row.day)
        end

        local group
        if day == nil then
            if unknown == nil then
                unknown = { day = nil, items = {} }
            end
            group = unknown
        else
            group = byDay[day]
            if group == nil then
                group = { day = day, items = {} }
                byDay[day] = group
                groups[#groups + 1] = group
            end
        end

        group.items[#group.items + 1] = row
    end

    -- Newest day first. table.sort is not stable, but every `day` here is
    -- distinct by construction (byDay dedupes), so there are no ties to be
    -- unstable about.
    table.sort(groups, function(a, b) return a.day > b.day end)

    if unknown ~= nil then
        groups[#groups + 1] = unknown
    end

    for _, group in ipairs(groups) do
        if group.day == nil then
            group.titleKey = InGameMenuFarmManager25.MSG_GROUP_EARLIER
        elseif today ~= nil and group.day == today then
            group.titleKey = InGameMenuFarmManager25.MSG_GROUP_TODAY
        else
            group.titleKey = InGameMenuFarmManager25.MSG_GROUP_DAY
        end
    end

    return groups
end

--- The heading text for one group. Separated from buildMessageGroups so the
--  grouping stays pure and testable and only this one line touches l10n.
--  fm25_msg_group_day carries a %d; TODAY and EARLIER do not.
function InGameMenuFarmManager25:messageGroupTitle(group)
    if group == nil then
        return nil
    end
    local text = self.i18n:getText(group.titleKey)
    if group.titleKey == InGameMenuFarmManager25.MSG_GROUP_DAY and group.day ~= nil then
        -- string.format would throw on a translation that dropped the %d.
        -- A heading that crashes the page is worse than one that reads oddly,
        -- and a GUI callback that throws is what froze the load at 57% once
        -- already (see fixInGameMenu). Guarded, and the raw text is the
        -- fallback so a broken translation is VISIBLE rather than silent.
        local ok, formatted = pcall(string.format, text, group.day)
        if ok then
            return formatted
        end
        return text
    end
    return text
end

--- ⛔ THE ONE PLACE THAT DECIDES WHAT AN UNKNOWN LOOKS LIKE -- the COLOUR
--  half of [[DEC-199]], for every cell whose text is chosen by an explicit
--  FLAG rather than by emptiness.
--
--  ⚠ WHY THIS EXISTS ALONGSIDE setUnknownAwareText. That setter infers
--  `unknown` from an empty string, which is exactly wrong for the cells below:
--  the FIELDS contract cell renders "" to mean "this field is under NO
--  contract" -- a real, complete answer -- and routing it through an
--  emptiness test would relabel it `unknown`. The flag is the only safe
--  discriminator, so the two setters split on how they LEARN the fact and
--  share the one thing that must never drift: the dim colour.
--
--  ⛔ THE KNOWN COLOUR IS THE ELEMENT'S OWN, CAPTURED BEFORE WE FIRST TOUCH
--  IT. These cells inherit $preset_fs25_colorMainLight from their profile and
--  the design is the owner's, not ours -- so a known value must render exactly
--  as it does today. Restoring is NOT optional: list cells are RECYCLED, so a
--  cell dimmed for row 3 stays dim when row 4 reuses it unless the known path
--  puts the colour back.
function InGameMenuFarmManager25.applyUnknownColor(element, unknown)
    if element == nil then
        return
    end
    local theme = InGameMenuFarmManager25.engineTheme()
    if theme == nil or theme.text == nil then
        return
    end
    if element.fm25BaseTextColor == nil then
        element.fm25BaseTextColor = element.textColor or theme.text.body
    end
    local color = element.fm25BaseTextColor
    if unknown then
        color = theme.text.placeholder
    end
    if color ~= nil then
        element.textColor = color
    end
end

--- ⛔ [[DEC-197]] IN PIXELS. Applies one STOCK_RENDER rule to a cell.
--  Routes through applyUnknownColor FIRST so the element's own baseline is
--  captured before anything overrides it -- painting the warning colour
--  straight on would make the NEXT call capture the WARNING as the baseline
--  and the cell would never return to normal.
--    lowKey  -> dim   (notStarted, unknown: present, not competing)
--    flagged -> warn  (empty: a real, measured problem)
function InGameMenuFarmManager25.applyStockColor(element, render)
    if element == nil or render == nil then
        return
    end
    InGameMenuFarmManager25.applyUnknownColor(element, render.lowKey == true)
    if render.flagged ~= true then
        return
    end
    local theme = InGameMenuFarmManager25.engineTheme()
    local warn = theme ~= nil and theme.cards ~= nil and theme.cards.warn or nil
    if warn ~= nil and warn.accent ~= nil then
        element.textColor = warn.accent
    end
end

--- ⛔ ONE PLACE THAT DECIDES WHAT AN UNKNOWN LOOKS LIKE. Bright real value, dim
--  flagged word -- "I cannot tell" and "the answer is zero" must never render
--  alike (DEC-001, RSK-001). Called for every cell whose source may be absent.
--  `text` is the published value; "" and nil both mean absent, because the
--  message-log contract publishes "" for a dead clock and nil is what every
--  other seam publishes.
function InGameMenuFarmManager25:setUnknownAwareText(element, text)
    if element == nil then
        return
    end
    local known = text ~= nil and text ~= ""
    if known then
        element:setText(text)
    else
        element:setText(self.i18n:getText("fm25_farm_unknown"))
    end
    -- The dim/bright distinction is carried in the colour, not the words: a
    -- translation cannot accidentally remove it, and a player scanning the
    -- column sees the difference before reading it.
    -- Reuses the palette FarmManagerTheme.lua already ships -- `body` for a
    -- real value, `placeholder` for the dim flagged one. NO NEW THEME KEYS:
    -- placeholder is already exactly the dim grey this needs
    -- ({0.52,0.51,0.51,1}, FarmManagerTheme.lua:76), and a second name for the
    -- same colour is how two dims start to drift apart.
    local theme = InGameMenuFarmManager25.engineTheme()
    if theme ~= nil and theme.text ~= nil then
        local color = known and theme.text.body or theme.text.placeholder
        if color ~= nil then
            element.textColor = color
        end
    end
end

-- ---------------------------------------------------------------------------
-- THE MERGED IN/OUT FILL-TYPE LIST (chosen.html PRODUCTIONS: "Inputs and
-- outputs in ONE list (replaces prodInputList + prodOutputList): IN rows
-- first, then OUT; new IN/OUT tag element")
--
-- ⛔ ONE LIST, TWO MEANINGS PER COLUMN -- WHICH IS EXACTLY WHY THE TAG IS NOT
-- DECORATION. Merging the two tables makes three columns ambiguous:
--      rate    IN = burn rate L/h        OUT = tank capacity L
--      trail   IN = hours until empty    OUT = how full, as a percentage
--      bar     IN = time left vs a week  OUT = fullness vs capacity
-- A reader who cannot tell an IN row from an OUT row is reading numbers whose
-- UNITS he cannot know. So every merged row carries `kind` and a tag key, and
-- the tag is the thing that makes the shared columns legible rather than a
-- label on top of them. ⚠ Do not "tidy" the tag away as redundant with the
-- ordering: the list scrolls, and the IN/OUT boundary goes off-screen.
--
-- ⛔ THE TWO BAR RATIOS ARE NOT THE SAME QUANTITY AND MUST NOT BE COMPARED.
-- An input bar at 50% means "half a week of stock"; an output bar at 50%
-- means "the tank is half full". They are deliberately drawn in one column
-- because the tag disambiguates them, and for no other reason.
-- ---------------------------------------------------------------------------

-- ---------------------------------------------------------------------------
-- [[DEC-197]] STOCK STATES -- how each one RENDERS.
--
-- The ruling, 2026-09-12: a line is NOT STARTED (excluded from the urgent
-- count, rendered low-key) iff EVERY ONE OF ITS OUTPUTS IS ALSO ABSENT; it is
-- EMPTY (a real stockout, a measured 0, flagged) if the input is absent but an
-- output IS recorded; `unknown` is retained only for the genuinely
-- unmeasurable, so the word keeps its meaning (DEC-001).
--
-- ⛔ THE CLASSIFICATION IS NOT DONE HERE AND MUST NOT BE. DEC-197 puts it in
-- emit_productions_xml.py at `classify_absent_stock`, and it carries a NAMED
-- EXCEPTION -- a line that sells its output directly never banks it, so the
-- naive test misreads it as never-started. Re-deriving the rule in Lua would
-- give one ruling two implementations that can disagree, and would have to
-- duplicate that exception or silently lose it. This file only DECIDES WHAT
-- EACH STATE LOOKS LIKE.
--
-- ⚠ CONTRACT DEPENDENCY, STATED SO IT CANNOT BE FORGOTTEN: the `stockState`
-- attribute is owed by the emitter and is not written yet (lane dev-td139).
-- Until it arrives every row degrades to `unknown` by the fallback below,
-- which is exactly today's behaviour -- so nothing regresses in the meantime
-- and nothing silently improves either. ⛔ If the emitter ships a DIFFERENT
-- attribute name, this join fails silently and every line reads `unknown`
-- with no error anywhere. tests/test_stock_states.py pins the value set; the
-- NAME has to be agreed between the two lanes, not assumed.
-- ⛔ THE VALUE IS `stocked`, NOT `measured`. Measured, not agreed: read out of
--  emit_productions_xml.py at fix/td139-round2-2026-09-12 @ 5036af5, where
--  STOCK_STOCKED = "stocked" (:533). `measured` was this lane's own plausible
--  guess before the contract was checked, and it would have matched NOTHING --
--  every row falling through to `unknown`, no error, nothing in log.txt. The
--  near-miss is left recorded here because the next person to add a state will
--  be tempted by exactly the same kind of reasonable-sounding synonym.
InGameMenuFarmManager25.STOCK_STOCKED     = "stocked"
InGameMenuFarmManager25.STOCK_EMPTY       = "empty"
InGameMenuFarmManager25.STOCK_NOT_STARTED = "notStarted"
InGameMenuFarmManager25.STOCK_UNKNOWN     = "unknown"

--- How each state renders. DATA, not branches, so adding a state is one row
--  here rather than an edit in three populators.
--    urgent   counts toward the "under 24 h" alarm
--             ⚠ NOT CONSUMED YET, and said here rather than left to be
--             discovered: the "under 24 h" count is computed per POINT from
--             runwayHours (buildProductionFooter), and no point-level roll-up
--             from input rows exists. Wiring one would be inventing a measure
--             nobody has specified. lowKey/flagged/word ARE consumed, by
--             populateProductionCell.
--    lowKey   drawn dimmed -- present, but not competing for attention
--    flagged  drawn in the warning colour: this is a real, measured problem
--    word     render the l10n unknown WORD instead of a figure
InGameMenuFarmManager25.STOCK_RENDER = {
    stocked    = { urgent = true,  lowKey = false, flagged = false, word = false },
    -- ⛔ EMPTY IS A MEASURED ZERO AND IS FLAGGED. It is the loudest state on
    -- the tab: the line has run before, and right now it has nothing.
    empty      = { urgent = true,  lowKey = false, flagged = true,  word = false },
    -- ⛔ NOT STARTED IS NOT A PROBLEM AND MUST NOT SOUND LIKE ONE. The player
    -- never began this line; calling it starved would send him to fix
    -- something he never set up.
    notStarted = { urgent = false, lowKey = true,  flagged = false, word = false },
    -- ⛔ AND UNKNOWN IS STILL THE WORD. DEC-197's closing clause is that
    -- `unknown` keeps its meaning, which it only does if the states above stop
    -- borrowing it.
    unknown    = { urgent = false, lowKey = true,  flagged = false, word = true  },
}

--- The state for one published input row. Consumes the emitter's answer when
--  it is there; otherwise falls back to what this build can honestly say --
--  a flagged-or-absent held level is `unknown`, anything else is `measured`.
--  ⛔ THE FALLBACK NEVER INVENTS `empty` OR `notStarted`. Those two are exactly
--  the distinction DEC-197 introduced and they need the output evidence the
--  emitter has and this file does not. Guessing one of them here would be a
--  fabricated classification wearing the ruling's name.
function InGameMenuFarmManager25.stockState(row)
    if row == nil then
        return InGameMenuFarmManager25.STOCK_UNKNOWN
    end
    local state = row.stockState
    if InGameMenuFarmManager25.STOCK_RENDER[state] ~= nil then
        return state
    end
    if row.heldUnknown == true or row.heldText == nil then
        return InGameMenuFarmManager25.STOCK_UNKNOWN
    end
    return InGameMenuFarmManager25.STOCK_STOCKED
end

function InGameMenuFarmManager25.stockRender(state)
    return InGameMenuFarmManager25.STOCK_RENDER[state]
        or InGameMenuFarmManager25.STOCK_RENDER.unknown
end

InGameMenuFarmManager25.FILL_KIND_IN  = "in"
InGameMenuFarmManager25.FILL_KIND_OUT = "out"
InGameMenuFarmManager25.FILL_TAG_KEYS = {
    ["in"]  = "fm25_prod_tag_in",
    ["out"] = "fm25_prod_tag_out",
}

--- D3 ([[DEC-210]] as amended by [[DEC-211]]): the tag a REFUSED PRODUCTIONS
--  figure shows instead of the word `unknown`. A closed set, chosen by WHICH
--  reason field the producer wrote -- never by its prose, which is English
--  and open-ended and is never rendered.
InGameMenuFarmManager25.REFUSAL_TAG_KEYS = {
    rate     = "fm25_prod_refused_rate",
    capacity = "fm25_prod_refused_capacity",
    stock    = "fm25_prod_unreadable_stock",
}

--- The input `rate` tokens that mean "the burn rate was refused".
--  ⛔ NOT `excluded` (the input passes through the building) and NOT `resolved`
--  (there a `reason` says "a resolved ZERO, it never runs dry"). Both carry a
--  `reason` too, so tagging on the reason alone would call an answer a refusal.
InGameMenuFarmManager25.RATE_REFUSED_TOKENS = {
    ambiguous = true, unreadable = true, unknown = true,
}

--- ⭐ PURE. The tag key for one PRODUCTIONS cell, or nil when no refusal
--  explains it. `cell` is the element name. The populator consults it only for
--  an UNKNOWN cell, so a reason never replaces a measured value.
function InGameMenuFarmManager25.refusalTag(cell, row)
    if row == nil then
        return nil
    end
    local K = InGameMenuFarmManager25.REFUSAL_TAG_KEYS
    if cell == "lnOutput" then
        -- core publishes a line's outReason as `reason`
        return row.reason ~= nil and K.rate or nil
    end
    local stock = row.heldReason ~= nil and K.stock or nil
    if row.kind == InGameMenuFarmManager25.FILL_KIND_IN then
        local rate = (row.rateReason ~= nil
            and InGameMenuFarmManager25.RATE_REFUSED_TOKENS[row.rateToken] == true)
            and K.rate or nil
        if cell == "ftHeld" then return stock end
        if cell == "ftRate" then return rate end
        if cell == "ftTrail" then
            -- ⛔ [[DEC-211]] clarification: a pass-through input or a line never
            -- started has NO runway to refuse, so its runway keeps the word even
            -- when the stock or the rate on the same row was refused. The held
            -- and rate cells above keep their own, true, tags.
            if row.rateToken == "excluded"
                    or row.state == InGameMenuFarmManager25.STOCK_NOT_STARTED then
                return nil
            end
            -- the runway needs both a level and a rate
            return stock or rate
        end
    elseif row.kind == InGameMenuFarmManager25.FILL_KIND_OUT then
        local capacity = row.capacityReason ~= nil and K.capacity or nil
        if cell == "ftHeld" then return stock end
        if cell == "ftRate" then return capacity end
        -- the percentage needs both a capacity and a level; when both were
        -- refused it names the capacity ([[DEC-211]] clarification, pinned by
        -- test_an_output_with_capacity_and_stock_both_refused_names_capacity_on_the_pct)
        if cell == "ftTrail" then return capacity or stock end
    end
    return nil
end

--- ⭐ PURE. One production point in, the merged fill-type rows out, IN first
--  then OUT, each half keeping core's published order.
--
--  Every row has the same SHAPE whatever its kind, so the populator has no
--  per-kind branching and cannot put an output's number in an input's column:
--      kind, tagKey, label, ft,
--      heldText/heldUnknown,      -- both kinds: litres held
--      rateText/rateUnknown,      -- IN burn L/h   | OUT capacity L
--      trailText/trailUnknown,    -- IN hours left | OUT percent full
--      ratio                      -- nil = DRAW NO BAR
--      heldReason                 -- both kinds; plus IN rateToken/rateReason,
--                                 -- OUT capacityReason (D3, refusalTag only)
--
--  ⛔ nil ratio AND 0 ratio ARE DIFFERENT FACTS AND STAY DIFFERENT HERE.
--  0 = "measured, and it is empty" and draws an empty fill inside a visible
--  track; nil = "we cannot tell" and draws no track at all. A zero-width bar
--  and an absent bar look identical on screen, so they have to be told apart
--  before the pixels (core says this too, at buildProductionRows).
function InGameMenuFarmManager25.buildFillTypeRows(point)
    local out = {}
    point = point or {}

    for _, i in ipairs(point.inputs or {}) do
        out[#out + 1] = {
            kind          = InGameMenuFarmManager25.FILL_KIND_IN,
            tagKey        = InGameMenuFarmManager25.FILL_TAG_KEYS["in"],
            label         = i.label or "",
            ft            = i.ft,
            heldText      = i.heldText,
            heldUnknown   = i.heldUnknown == true or i.heldText == nil,
            rateText      = i.burnText,
            rateUnknown   = i.burnUnknown == true or i.burnText == nil,
            trailText     = i.runwayText,
            trailUnknown  = i.runwayUnknown == true or i.runwayText == nil,
            ratio         = i.ratio,
            -- [[DEC-197]]. Outputs have no stock state -- the ruling is about
            -- an absent INPUT -- so only this half carries one.
            state         = InGameMenuFarmManager25.stockState(i),
            -- D3 ([[DEC-211]]): the refusal FIELDS, never rendered as text.
            -- refusalTag() reads them to pick a tag. rateToken travels with
            -- rateReason because an input `reason` is not always a refusal.
            rateToken     = i.rate,
            rateReason    = i.reason,
            heldReason    = i.heldReason,
        }
    end

    for _, o in ipairs(point.outputs or {}) do
        out[#out + 1] = {
            kind          = InGameMenuFarmManager25.FILL_KIND_OUT,
            tagKey        = InGameMenuFarmManager25.FILL_TAG_KEYS["out"],
            label         = o.label or "",
            ft            = o.ft,
            heldText      = o.heldText,
            heldUnknown   = o.heldUnknown == true or o.heldText == nil,
            rateText      = o.capText,
            rateUnknown   = o.capUnknown == true or o.capText == nil,
            trailText     = o.pctText,
            trailUnknown  = o.pctUnknown == true or o.pctText == nil,
            ratio         = o.ratio,
            -- D3: core publishes an output's capacityReason as `reason`.
            capacityReason = o.reason,
            heldReason     = o.heldReason,
        }
    end

    return out
end

-- ---------------------------------------------------------------------------
-- SORTING (chosen.html SORT-2, on FIELDS and the PRODUCTIONS master)
--
-- ⛔ TWO RULES DECIDE EVERY COMPARATOR HERE, AND BOTH ARE ANSWERS, NOT STYLE.
--
-- 1. UNKNOWN IS ALWAYS LAST, IN BOTH DIRECTIONS. Not "largest", not
--    "smallest" -- OUT of the ordering entirely, pinned to the bottom whether
--    the column is ascending or descending. Sorting unknowns as if they were
--    a value puts "we could not read this" in the middle of a ranked list,
--    where it reads as a measurement (DEC-001). ⚠ The consequence a reviewer
--    should check for: reversing the direction must NOT move an unknown row.
--
-- 2. FIELD NUMBERS SORT NATURALLY. "Field 6" comes before "Field 30".
--    chosen.html FIELDS says so explicitly, because lexicographic order puts
--    Field 30 before Field 6 and the tab is a list of the player's own fields
--    in the order he thinks of them.
--
-- ⛔ AND THE SORT IS STABLE, BY CONSTRUCTION, NOT BY table.sort. table.sort is
-- NOT stable in Lua, and two fields of equal area would otherwise swap places
-- on every refresh -- a list that reshuffles under the cursor while nothing
-- changed. Each row is decorated with its original index and that index is
-- the final tie-break, which makes the order total and therefore reproducible.
-- ---------------------------------------------------------------------------

--- Pull the trailing integer out of a field name for natural ordering.
--  Returns nil when there is none, which sorts as unknown (last).
local function fieldNumber(name)
    if type(name) ~= "string" then
        return nil
    end
    return tonumber(name:match("(%d+)%s*$"))
end

--- The sort keys each column offers. `value(row)` returns
--      nil            -> unknown, pinned last
--      number|string  -> the ordering key
--  ⛔ A COLUMN'S KEY IS READ FROM THE ROW'S DATA, NEVER FROM ITS RENDERED
--  TEXT. "1,234 ha" sorts as a string after "999 ha"; the number does not.
InGameMenuFarmManager25.SORT_COLUMNS = {
    fields = {
        -- ⛔ NO TEXT FALLBACK. A name with no trailing number has no field
        -- NUMBER, and this column sorts by field number (chosen.html). Falling
        -- back to the name string would make it a known key, which puts it in
        -- the middle of the order and -- worse -- MOVES IT when the direction
        -- flips, breaking rule 1 for the one row most likely to be odd.
        name     = { value = function(r) return fieldNumber(r.name) end },
        area     = { value = function(r)
                         if r.areaUnknown == true then return nil end
                         return type(r.areaHa) == "number" and r.areaHa or nil
                     end },
        owned    = { value = function(r)
                         if r.ownedUnknown == true then return nil end
                         if r.owned == nil then return nil end
                         return r.owned and 1 or 0
                     end },
        -- ⛔ THREE PLACES, NOT TWO. "Harvest" is a contract; "no contract" is
        -- a REAL, COMPLETE answer that is not a contract; "we could not read
        -- the contracts" is unknown. chosen.html asks for blank LAST among the
        -- known, which is a different place from unknown -- so `rank` sinks it
        -- below the named ones while `value` nil still sinks unknown below
        -- everything.
        contract = { rank  = function(r)
                         return (r.contract == nil or r.contract == "") and 1 or 0
                     end,
                     value = function(r)
                         if r.contractKnown ~= true then return nil end
                         return r.contract or ""
                     end },
    },
    productions = {
        name   = { value = function(r) return r.name end },
        runway = { value = function(r)
                       if r.runwayUnknown == true then return nil end
                       return type(r.runwayHours) == "number" and r.runwayHours or nil
                   end },
    },
    messages = {
        -- "When (day, then time)". Composed into one sortable number so the
        -- two halves cannot disagree: a nil day sorts unknown, and within a
        -- day the HH:MM text orders correctly as a string because it is
        -- zero-padded (%02d:%02d) -- which is why it is safe here and would
        -- not be if the format ever lost its padding.
        -- ⛔ DAY **AND THEN TIME**, composed into ONE number. chosen.html says
        -- "When (day, then time)". Keying on the day ALONE was a real defect
        -- and an invisible one: inside a day group every row shares a day, so
        -- every key was equal and sorting by When did nothing at all -- in
        -- exactly the place the spec says sorting works. Found by asking why a
        -- pipeline-order mutation survived, not by reading the code.
        -- whenText is zero-padded "%02d:%02d" (FarmManager25.stampText), which
        -- is why the minutes can be parsed back out reliably; if that format
        -- ever loses its padding this breaks, so the parse is anchored.
        when   = { value = function(r)
                       if type(r.day) ~= "number" then return nil end
                       local h, m = tostring(r.whenText or ""):match("^(%d%d):(%d%d)")
                       local minutes = 0
                       if h ~= nil then
                           minutes = tonumber(h) * 60 + tonumber(m)
                       end
                       return r.day * 1440 + minutes
                   end,
                   -- A row with a known DAY but a dead clock still belongs to
                   -- that day; it sinks to the BOTTOM of its own group rather
                   -- than being guessed into a time slot. rank is not reversed
                   -- by direction, so it stays at the bottom either way.
                   rank  = function(r)
                       return tostring(r.whenText or ""):match("^%d%d:%d%d") == nil
                           and 1 or 0
                   end },
        from   = { value = function(r) return r.fromText end },
        status = { value = function(r) return r.statusText end },
    },
}

--- ⭐ PURE. Returns a NEW array; the input is never reordered in place, so a
--  caller still holding the unsorted rows (the footer counts them) is not
--  quietly changed underneath.
--
--  `tableName` and `column` name a SORT_COLUMNS entry; `descending` flips the
--  KNOWN rows only. An unrecognised column returns the rows in their original
--  order rather than an arbitrary one -- absence of a comparator is not a
--  licence to invent an ordering.
function InGameMenuFarmManager25.sortRows(rows, tableName, column, descending)
    local out = {}
    for i, r in ipairs(rows or {}) do
        out[i] = r
    end

    local columns = InGameMenuFarmManager25.SORT_COLUMNS[tableName]
    local spec = columns ~= nil and columns[column] or nil
    if spec == nil then
        return out
    end

    -- Decorate: original index for stability, key, and the unknown flag.
    local keyed = {}
    for i, r in ipairs(out) do
        local v = spec.value(r)
        if v == nil and spec.fallback ~= nil then
            v = spec.fallback(r)
            if v == "" then v = nil end
        end
        -- `rank` is an optional coarse bucket applied BEFORE the key and, like
        -- unknown, NOT reversed by `descending`: it expresses "this kind of
        -- answer belongs at the bottom", which is a fact about the answer and
        -- not about the direction the player clicked.
        local rank = 0
        if spec.rank ~= nil and v ~= nil then
            rank = spec.rank(r) or 0
        end
        keyed[i] = { row = r, index = i, key = v, rank = rank,
                     unknown = (v == nil) }
    end

    table.sort(keyed, function(a, b)
        -- Rule 1. Unknowns sink, and the direction flag does not reach them.
        if a.unknown ~= b.unknown then
            return b.unknown
        end
        if not a.unknown and a.rank ~= b.rank then
            return a.rank < b.rank
        end
        if not a.unknown and a.key ~= b.key then
            -- Mixed types would error in Lua; compare as text when they differ.
            local ak, bk = a.key, b.key
            if type(ak) ~= type(bk) then
                ak, bk = tostring(ak), tostring(bk)
            end
            if descending then
                return ak > bk
            end
            return ak < bk
        end
        -- Rule 3. Original order breaks every tie, unknowns included.
        return a.index < b.index
    end)

    local sorted = {}
    for i, k in ipairs(keyed) do
        sorted[i] = k.row
    end
    return sorted
end

--- Remember the chosen column and direction per table (chosen.html FIELDS:
--  "remember the chosen column and direction"). Clicking the ACTIVE column
--  flips the direction; clicking another column selects it ASCENDING -- the
--  idiom ProductionAdvisorSellPointsDialog.lua:273-279 already uses, so the
--  two tabs behave the same way under the same click.
function InGameMenuFarmManager25:toggleSort(tableName, column)
    self.sortState = self.sortState or {}
    local st = self.sortState[tableName]
    if st ~= nil and st.column == column then
        st.descending = not st.descending
    else
        self.sortState[tableName] = { column = column, descending = false }
    end
    return self.sortState[tableName]
end

--- ⛔ P-6: THE ORDER A LIST IS IN BEFORE THE PLAYER TOUCHES A HEADER.
--  chosen.html renders the PRODUCTIONS master runway-ascending with the
--  unmeasurable points last; the build sorted nothing until a header was
--  clicked, so the tab opened in core's emission order.
--  ⛔ SEEDED AS REAL SORT STATE, not applied as a hidden pre-sort. If the
--  default lived only inside the data refresh, the list would be sorted while
--  currentSort() still said "no column is active" -- so refreshSortArrows()
--  would draw no arrow and the page would order 27 rows without saying by
--  what. A sort the player cannot see is a sort they cannot trust.
--  ⚠ MESSAGES IS DELIBERATELY ABSENT. chosen.html: "today's order is
--  live-then-history, not strict time", and sorting happens WITHIN day groups.
--  A default there would overwrite an ordering core publishes on purpose.
--  ⚠ FIELDS IS ABSENT TOO -- it is not one of F4's ten shortfalls, and
--  re-ordering a list nobody reported is scope this task did not ask for.
--  `unknown last` is not implemented here: the runway comparator already
--  returns nil for an unmeasurable point, which sorts last in both directions.
InGameMenuFarmManager25.SORT_DEFAULTS = {
    productions = { column = "runway", descending = false },
}

--- Seed any table's default sort, once, without disturbing a chosen one.
function InGameMenuFarmManager25:applySortDefaults()
    self.sortState = self.sortState or {}
    for tableName, def in pairs(InGameMenuFarmManager25.SORT_DEFAULTS) do
        if self.sortState[tableName] == nil then
            self.sortState[tableName] = {
                column = def.column, descending = def.descending == true,
            }
        end
    end
end

--- Which arrow pair belongs to which (table, column). ⛔ ONE TABLE, so the
--  handlers below and the arrow refresh cannot disagree about which column a
--  header stands for -- the same reason LIST_SOURCES exists.
InGameMenuFarmManager25.SORT_HEADERS = {
    { table = "fields",      column = "name",     id = "fhName"     },
    { table = "fields",      column = "area",     id = "fhArea"     },
    { table = "fields",      column = "owned",    id = "fhOwned"    },
    { table = "fields",      column = "contract", id = "fhContract" },
    { table = "productions", column = "name",     id = "phName"     },
    { table = "productions", column = "runway",   id = "phRunway"   },
    { table = "messages",    column = "when",     id = "mhWhen"     },
    { table = "messages",    column = "from",     id = "mhFrom"     },
    { table = "messages",    column = "status",   id = "mhStatus"   },
}

--- ⛔ SIX THIN NAMED HANDLERS, ONE PER COLUMN, and this is a deliberate
--  departure from the identity dispatch the LISTS use. `sendAction`, which
--  dispatches a Button's onClick, is CALLED but never DEFINED in the 951-file
--  gameSource subset, so what arguments reach the handler cannot be
--  established from that corpus -- and a partial corpus's silence is not
--  evidence of absence. FS25_ProductionAdvisor, which ships and works, names
--  one handler per column (ProductionAdvisorFrame.xml:57,61,65) and does not
--  rely on the argument. Copying the proven shape costs six three-line
--  functions; assuming the element is passed would risk a header that does
--  nothing, silently.
function InGameMenuFarmManager25:onClickSortFieldName()     self:onClickSortHeader("fields", "name")     end
function InGameMenuFarmManager25:onClickSortFieldArea()     self:onClickSortHeader("fields", "area")     end
function InGameMenuFarmManager25:onClickSortFieldOwned()    self:onClickSortHeader("fields", "owned")    end
function InGameMenuFarmManager25:onClickSortFieldContract() self:onClickSortHeader("fields", "contract") end
function InGameMenuFarmManager25:onClickSortProdName()      self:onClickSortHeader("productions", "name")   end
function InGameMenuFarmManager25:onClickSortProdRunway()    self:onClickSortHeader("productions", "runway") end
function InGameMenuFarmManager25:onClickSortMsgWhen()      self:onClickSortHeader("messages", "when")   end
function InGameMenuFarmManager25:onClickSortMsgFrom()      self:onClickSortHeader("messages", "from")   end
function InGameMenuFarmManager25:onClickSortMsgStatus()    self:onClickSortHeader("messages", "status") end

--- Show exactly one arrow, on exactly the active column of each table.
--  ⛔ EVERY ARROW IS HIDDEN FIRST. Toggling only the one that changed leaves
--  the previous column's arrow up, so the page would claim two active sorts --
--  and the stale one would be the more believable, because it is where the
--  player last clicked.
function InGameMenuFarmManager25:refreshSortArrows()
    for _, h in ipairs(InGameMenuFarmManager25.SORT_HEADERS) do
        local asc  = self[h.id .. "Asc"]
        local desc = self[h.id .. "Desc"]
        local column, descending = self:currentSort(h.table)
        local active = (column == h.column)
        if asc ~= nil then
            asc:setVisible(active and not descending)
        end
        if desc ~= nil then
            desc:setVisible(active and descending)
        end
    end
end

--- ⛔ M4 SECTIONS-3: put the accent glyph into a list's SECTION-HEADER
--  TEMPLATE, so every header cell the engine clones from it carries it.
--  WHY THE TEMPLATE AND NOT A PER-CELL HOOK. The header cell has a child named
--  `title`, and when it does the engine sets that text from
--  getTitleForSectionHeader and does NOT call populateSectionHeader
--  (gameSource SmoothListElement.lua:912-916, an if/elseif). Renaming `title`
--  to reach the hook would move the day-group headings onto a new path, and
--  those headings render correctly today ("EARLIER" in messages4.png). The
--  glyph is the SAME on every header of a list, so the template is enough:
--  dequeueReusableCell clones cellDatabase[name] (:514) and
--  BitmapElement:copyAttributes copies the overlay (BitmapElement.lua:101).
--  ⚠ It must run BEFORE the list's first reloadData, or a header cloned
--  earlier would lack it. It is idempotent, so every reload re-applies it.
function InGameMenuFarmManager25.applySectionGlyph(list, headerName, iconName)
    local db = list ~= nil and list.cellDatabase or nil
    local template = db ~= nil and db[headerName] or nil
    local glyph = template ~= nil and template.getDescendantByName ~= nil
        and template:getDescendantByName("secGlyph") or nil
    if glyph == nil then
        return false
    end
    InGameMenuFarmManager25.setGlyph(glyph, iconName,
        InGameMenuFarmManager25.themeColor("cards", "ok", "accent"))
    return true
end

--- chosen.html: MESSAGES day groups are "accent bar + ICONS.schedule + accent
--  text"; SETTINGS group headings are "SECTIONS-3 ... with ICONS.gear".
InGameMenuFarmManager25.SECTION_GLYPHS = {
    messageTable = { header = "messageDayHeader",    icon = "schedule" },
    settingsList = { header = "settingsGroupHeader", icon = "gear" },
}

--- chosen.html `.tab{padding:0 20px;gap:8px}` + a 22px inline glyph: the
--  label must sit 22 + 8 = 30px further right than the stock tab puts it.
InGameMenuFarmManager25.TAB_GLYPH_ROOM_PX = 30

--- ⛔ H2: MOVE THE LABEL, NEVER THE GLYPH ONTO IT.
--  The tab is widened by TAB_GLYPH_ROOM_PX and its label shifted so that ALL
--  of the new room lands on the LEFT and the right padding is unchanged.
--
--  ⛔ HOW FAR TO SHIFT DEPENDS ON THE STOCK ALIGNMENT, AND IT IS READ, NOT
--  ASSUMED. From the engine (gameSource TextElement:getTextPositionX): the
--  label's x is absPosition + absSize*0.5 for CENTER, absPosition for LEFT,
--  absPosition + absSize for RIGHT, and renderText adds textOffset on top.
--  Widening by D therefore moves a CENTRED label D/2 by itself; to put the
--  whole D on the left it needs another D/2. A LEFT label needs all of D, a
--  RIGHT label none. The stock profile cannot be read on this machine (no GUI
--  profile XML in gameSource.zip), so guessing CENTER would be a guess about
--  exactly the thing that decides whether the glyph is covered.
--  ⛔ EVERY STATE'S OFFSET MOVES. getTextOffset() substitutes
--  textSelectedOffset / textFocusedOffset / ... when set, so shifting only
--  textOffset would let the label jump back over the glyph the moment the
--  tab became active.
function InGameMenuFarmManager25.makeRoomForTabGlyph(tab)
    if tab == nil or tab.size == nil or g_pixelSizeScaledX == nil then
        return
    end
    local d = InGameMenuFarmManager25.TAB_GLYPH_ROOM_PX * g_pixelSizeScaledX
    local share = 1
    if RenderText ~= nil and tab.textAlignment == RenderText.ALIGN_CENTER then
        share = 0.5
    elseif RenderText ~= nil and tab.textAlignment == RenderText.ALIGN_RIGHT then
        share = 0
    end
    for _, field in ipairs({ "textOffset", "textSelectedOffset", "textFocusedOffset",
                             "textHighlightedOffset", "textPressedOffset" }) do
        local o = tab[field]
        if o ~= nil then
            tab[field] = { (o[1] or 0) + d * share, o[2] or 0 }
        end
    end
    -- ⛔⛔ N1 (review round 2): A TEXT-FITTED BUTTON IS RE-FITTED BY THE ENGINE.
    -- ButtonElement:updateSize (gameSource.zip :834-862) sets a fitToContent /
    -- textAutoWidth button's width to iconWidth + textWidth + fitExtraWidth,
    -- and it runs on the FIRST DRAW (setInputMode :317/:331 -- isGamepadMode
    -- starts nil) and on every setText. A plain setSize is thrown away there,
    -- leaving the shifted label over the glyph and the plate 30px too wide.
    -- So the room goes into fitExtraWidth, the engine's own knob, and the
    -- engine's refit then KEEPS it. Whether the stock tab is fitted cannot be
    -- read (its profile is packed), so it is read off the live element, like
    -- the alignment above; a fixed-width tab is widened directly.
    if (tab.fitToContent or tab.textAutoWidth) and tab.updateSize ~= nil then
        tab.fitExtraWidth = (tab.fitExtraWidth or 0) + d
        tab:updateSize()
    else
        tab:setSize(tab.size[1] + d, tab.size[2])
    end
end

--- Clone the ring fill and the glyph into one tab, and remember both so
--  tintTab can drive them per state.
function InGameMenuFarmManager25:addTabChrome(tab, tabIndex)
    if tab == nil then
        return
    end
    if self.tabFillTemplate ~= nil then
        local fill = self.tabFillTemplate:clone(tab)
        if fill ~= nil and g_pixelSizeScaledX ~= nil and g_pixelSizeScaledY ~= nil then
            fill:setSize(tab.size[1] - 4 * g_pixelSizeScaledX,
                         tab.size[2] - 4 * g_pixelSizeScaledY)
            fill:setVisible(false)
            tab.fm25Fill = fill
        end
    end
    if self.tabGlyphTemplate ~= nil then
        local glyph = self.tabGlyphTemplate:clone(tab)
        if glyph ~= nil then
            glyph:setVisible(true)
            InGameMenuFarmManager25.setGlyph(glyph,
                InGameMenuFarmManager25.TAB_GLYPHS[tabIndex],
                InGameMenuFarmManager25.themeColor("text", "body"))
            tab.fm25Glyph = glyph
        end
    end
end

--- ⛔ C1: THE TAB STRIP IS THE LAST PLACE THEME B DOES NOT REACH.
--  chosen.html STRIP-4: "Active tab: THEME.cards.ok.bg fill, 2 px
--  THEME.cards.ok.border, text THEME.cards.ok.accent", applied "to the stock
--  elements with setImageColor / text colour, the way tintBar already tints
--  the PRODUCTIONS bar". This is that call, and it deliberately reuses
--  tintBar's idiom rather than inventing a second one.
--
--  ⚠ THE TAB PREFAB IS STOCK AND IS NOT REPLACED. Only its colours move: the
--  cloned ThreePartBitmap named "background" is tinted, and the tab's own text
--  takes the accent when active. Everything else -- geometry, focus handling,
--  the clone itself -- is the base game's and is untouched, which is why this
--  is a tint and not a rebuild.
--
--  ⚠ AN INACTIVE TAB IS RESTORED TO ITS STOCK COLOURS, captured before the
--  first tint - see the H1 note on tintTab below. (The first version said
--  inactive tabs were "left alone"; with in-place colour writes that meant
--  "left tinted", and it also named nine tabs where there are four.)
--  ⛔ pcall'd like tintBar: a stock prefab that has no "background" child on
--  some layout must not take the whole page down with it.
-- ⛔⛔ H1 (review 2026-09-17): THE INACTIVE PATH RESTORES, IT DOES NOT
-- "LEAVE ALONE". The first version did nothing when a tab went inactive, and
-- setImageColor writes IN PLACE (gameSource BitmapElement:setImageColor: it
-- edits the table GuiOverlay.getOverlayColor returns), so a tint once applied
-- stayed: after a few clicks every tab read as active. The test that should
-- have caught it switched tabs once.
--
-- ⛔ AND IT TINTED THE WRONG STATE. A Button's children receive its selected
-- state (GuiElement.updateChildrenState defaults to TRUE and setSelected
-- recurses), and a selected element draws colorSelected (getOverlayState ->
-- STATE_SELECTED). The stock tab paints its green plate exactly that way -
-- inactive tabs show no plate at all. Tinting only the NORMAL state therefore
-- never showed on the ACTIVE tab and showed only on tabs already left.
-- So BOTH states are tinted when active and BOTH are restored when not.
--
-- ⛔ THE RESTORE VALUE IS CAPTURED, NEVER GUESSED. The stock colours are read
-- once, before the first tint, and put back exactly. If they cannot be read
-- (no overlay, no GuiOverlay), the tab is NOT tinted at all: a tint that
-- cannot be undone is the defect this function exists to avoid.
local TAB_TEXT_FIELDS = { "textColor", "textSelectedColor",
                          "textFocusedSelectedColor", "textHighlightedSelectedColor" }

local function copyColor(c)
    if c == nil then return nil end
    return { c[1], c[2], c[3], c[4] }
end

local function captureTabStock(tab, background)
    if tab.fm25Stock ~= nil then
        return tab.fm25Stock
    end
    if background == nil or background.overlay == nil or GuiOverlay == nil
        or GuiOverlay.getOverlayColor == nil then
        return nil
    end
    local stock = {
        bgNormal   = copyColor(GuiOverlay.getOverlayColor(background.overlay, nil)),
        bgSelected = copyColor(GuiOverlay.getOverlayColor(background.overlay,
                                                          GuiOverlay.STATE_SELECTED)),
        text = {},
    }
    for _, f in ipairs(TAB_TEXT_FIELDS) do
        stock.text[f] = copyColor(tab[f])
    end
    tab.fm25Stock = stock
    return stock
end

local function paint(element, c)
    if element ~= nil and element.setImageColor ~= nil and c ~= nil then
        element:setImageColor(nil, c[1], c[2], c[3], c[4])
        if GuiOverlay ~= nil and GuiOverlay.STATE_SELECTED ~= nil then
            element:setImageColor(GuiOverlay.STATE_SELECTED, c[1], c[2], c[3], c[4])
        end
    end
end

function InGameMenuFarmManager25:tintTab(tab, active)
    if tab == nil then
        return
    end
    local background = tab.getDescendantByName ~= nil
        and tab:getDescendantByName("background") or nil
    local stock = captureTabStock(tab, background)
    if stock == nil then
        return
    end
    local accent = InGameMenuFarmManager25.themeColor("cards", "ok", "accent")
    local border = InGameMenuFarmManager25.themeColor("cards", "ok", "border")
    local body   = InGameMenuFarmManager25.themeColor("text", "body")

    if active then
        -- chosen.html `.tab.on{background:--tabOn;box-shadow:inset 0 0 0 2px
        -- --tabOnB;color:--tabOnT}`: the plate becomes the BORDER colour and
        -- the inset fill supplies --tabOn over it, leaving a 2px ring.
        paint(background, border)
        if tab.fm25Fill ~= nil then tab.fm25Fill:setVisible(true) end
        for _, f in ipairs(TAB_TEXT_FIELDS) do
            if f == "textColor" or f == "textSelectedColor" or stock.text[f] ~= nil then
                tab[f] = accent
            end
        end
        paint(tab.fm25Glyph, accent)
    else
        -- Restore BOTH states exactly as captured.
        if background ~= nil and background.setImageColor ~= nil then
            local n, sel = stock.bgNormal, stock.bgSelected
            if sel ~= nil and GuiOverlay.STATE_SELECTED ~= nil then
                background:setImageColor(GuiOverlay.STATE_SELECTED, sel[1], sel[2], sel[3], sel[4])
            end
            if n ~= nil then
                background:setImageColor(nil, n[1], n[2], n[3], n[4])
            end
        end
        if tab.fm25Fill ~= nil then tab.fm25Fill:setVisible(false) end
        for _, f in ipairs(TAB_TEXT_FIELDS) do
            tab[f] = copyColor(stock.text[f])
        end
        -- chosen.html: inactive glyphs are #ededed (text.body).
        paint(tab.fm25Glyph, body)
    end
end

--- ⛔ THE ENTRY POINT A SORT HEADER CALLS. It exists ahead of the header
--  Buttons on purpose: the STATE and the COMPARATORS are testable and are
--  tested, while the header widgets are render-and-input and are the owner's
--  live test. Wiring a Button to this is then one attribute, and the
--  behaviour it triggers is already proved.
--  ⚠ The lists re-sort on their next refresh, which is also when the footer
--  recounts -- so the rows and the count can never describe different arrays.
function InGameMenuFarmManager25:onClickSortHeader(tableName, column)
    self:toggleSort(tableName, column)
    self:refreshSortArrows()
    if tableName == "fields" then
        self:refreshFieldData()
    elseif tableName == "productions" then
        self:refreshProductionData()
    elseif tableName == "messages" then
        -- ⛔ MESSAGES re-runs the WHOLE view, not just a sort: the sort applies
        -- INSIDE each day group, so the groups have to be rebuilt for it to
        -- land anywhere.
        self:updateMessages()
    end
end

function InGameMenuFarmManager25:currentSort(tableName)
    local st = (self.sortState or {})[tableName]
    if st == nil then
        return nil, false
    end
    return st.column, st.descending == true
end

-- ---------------------------------------------------------------------------
-- THE HEADLINE TILES (chosen.html: 4 on FARM, 6 on FIELDS)
--
-- ⭐ THE GEOMETRY IS DERIVED, NOT CHOSEN, and it is recorded here because it
-- is the first thing the owner is asked to eyeball:
--     FARM    4 tiles across the 1320px content width, 20px gaps:
--             (1320 - 3*20) / 4 = 1260 / 4 = 315 px exactly
--     FIELDS  6 tiles in the 930px detail pane -- and chosen.html lays them
--             out as `grid-template-columns: repeat(3, 1fr); gap: 12px`, i.e.
--             TWO ROWS OF THREE, not one row of six:
--             (930 - 2*12) / 3 = 906 / 3 = 302 px exactly
-- ⚠ Both divide evenly. A single row of six would NOT -- (930 - 5*20)/6 =
-- 138.33 -- which is where the "930 does not divide" reading came from. There
-- is no remainder to distribute and no judgement call on WIDTH; the only open
-- choice was tile HEIGHT, and all tiles take the taller of the two so the two
-- FIELDS rows are regular (a hint line is simply empty on the tiles without
-- one).
--
-- ⛔ TILES READ THE ROWS ALREADY FETCHED. chosen.html says so explicitly --
-- "values from the rows already read, no second getFarmRows() call" -- and it
-- is the same rule the balance chip had to learn: two reads of the same figure
-- at two moments is how a tile and a table end up disagreeing on screen.
-- ---------------------------------------------------------------------------

--- Paint one tile element. ⛔ ONE RENDERER FOR BOTH TILE SETS, so a FARM tile
--  and a FIELDS tile cannot drift into showing an unknown two different ways.
--  `tile` is whatever buildFarmTiles / buildFieldTiles produced.
function InGameMenuFarmManager25:renderTile(element, tile)
    if element == nil then
        return
    end
    if tile == nil then
        element:setVisible(false)
        return
    end
    element:setVisible(true)

    local label = element:getDescendantByName("tLabel")
    if label ~= nil then
        label:setText(self.i18n:getText(tile.labelKey or ""))
    end

    local glyph = element:getDescendantByName("tGlyph")
    if glyph ~= nil and tile.glyph ~= nil then
        InGameMenuFarmManager25.setGlyph(glyph, tile.glyph,
            InGameMenuFarmManager25.themeColor("cards", "ok", "accent"))
    end

    -- ⛔ THE VALUE GOES THROUGH THE ONE UNKNOWN-AWARE SETTER. Bright = a real
    -- answer, dim = we cannot tell (DEC-199). Money is formatted by the SAME
    -- formatter the header chip uses, so a tile and the chip can never render
    -- one figure two ways.
    local text = nil
    if tile.differs then
        -- ⛔ BRIGHT, and the same WORD the detail list uses for the same fact
        -- (:1380). The breakdown itself goes in the hint line below -- it does
        -- not fit a tile's value area, which is why the two are split.
        text = self.i18n:getText("fm25_field_differs")
    elseif not tile.unknown then
        if tile.valueNumber ~= nil then
            text = self:formatMoney(tile.valueNumber)
        elseif tile.isKey then
            text = self.i18n:getText(tile.valueText)
        else
            text = tile.valueText
        end
    end
    self:setUnknownAwareText(element:getDescendantByName("tValue"), text)

    -- F-2 / A-10: the freshness marker, in the same words the FARM detail
    -- rows already use so one figure cannot be stamped two ways on one page.
    local fresh = element:getDescendantByName("tFresh")
    if fresh ~= nil then
        local text = ""
        if tile.freshness ~= nil and FarmManager25 ~= nil then
            text = InGameMenuFarmManager25.freshMarkText(
                tile.freshness == FarmManager25.FARM_FRESH_LIVE,
                self.i18n:getText("fm25_farm_live"),
                self.i18n:getText("fm25_farm_asof"), tile.asOfText)
        end
        fresh:setText(text)
    end

    local hint = element:getDescendantByName("tHint")
    if hint ~= nil then
        -- ⛔ A MERGED FIELD WHOSE PARTS DISAGREE SAYS SO IN THE HINT LINE, and
        -- the static hint gives way to it. "45 OAT / 46 OAT / 36 UNKNOWN" is
        -- a real answer about a real disagreement; "0 = needs lime" beside it
        -- would be noise on top of the thing the player needs to read.
        if tile.differs then
            -- ⚠ THIS BRANCH WAS INERT. tile.valueText was nil for every
            -- disagreeing tile (buildFieldTiles classed them `unknown` and so
            -- never set it), so the promised breakdown rendered as "" AND the
            -- static legend was suppressed -- strictly worse than leaving it.
            -- valueText now carries partsText.
            hint:setText(tile.valueText or "")
        else
            hint:setText(tile.hintKey ~= nil
                and self.i18n:getText(tile.hintKey) or "")
        end
        -- ⛔⛔ M1 (review 2026-09-17): A DISAGREEMENT IS NOT DIM, EVEN HERE.
        -- FI-10 deleted the detail row that used to carry a merged field's
        -- per-parcel breakdown BRIGHT at 15px, leaving it only in this hint -
        -- whose profile, fm25_cellFresh, is the DIM class. That relocated the
        -- one measured, actionable fact on the pane into "we cannot tell",
        -- which is exactly what the ruling above the detail-row loop forbids:
        -- "DO NOT 'FIX' THIS TO DIM THE DISAGREEMENT ... Dimming it would file
        -- a measurement under 'we cannot tell' - DEC-001 inverted."
        -- Live on Field 70, a 7-parcel merge.
        -- So the breakdown takes the BODY colour; the static legend ("0 =
        -- needs lime") stays dim, as it is a caption, not a value.
        -- ⛔ BOTH BRANCHES SET IT. Tiles are persistent elements re-rendered
        -- per selection, so a colour set only on the differs path would stay
        -- bright on the next, agreeing field.
        local color = tile.differs
            and InGameMenuFarmManager25.themeColor("text", "body")
            or InGameMenuFarmManager25.themeColor("text", "placeholder")
        if color ~= nil then
            hint.textColor = color
        end
    end
end

--- The four FARM tiles, in order, with the row id each one reads.
--  chosen.html FARM: "tile glyphs finances, profit, field, contract".
InGameMenuFarmManager25.FARM_TILES = {
    { id = "a1", labelKey = "fm25_farm_a1_balance", glyph = "finances" },
    { id = "a3", labelKey = "fm25_farm_a3_equity",  glyph = "profit"   },
    { id = "b3", labelKey = "fm25_farm_b3_value",   glyph = "field"    },
    { id = "d2", labelKey = "fm25_farm_d2_reward",  glyph = "contract" },
}

--- ⭐ PURE. The farm rows in, four tiles out, ALWAYS FOUR.
--  Returns { labelKey, glyph, valueText, valueNumber, unknown }.
--
--  ⛔ A TILE WHOSE ROW IS ABSENT IS AN UNKNOWN TILE, NOT A MISSING ONE. The
--  four are a fixed frame; dropping one would reflow the other three and make
--  an absent figure invisible rather than reported (DEC-001).
--  ⛔ AND valueText IS NOT PUBLISHED WHEN THE VALUE IS UNKNOWN -- same rule as
--  the master headline: the flag is the answer, and a text left beside it is
--  a stale figure waiting to be printed.
--  valueNumber is passed through untouched: core publishes money as a raw
--  number, and the page runs it through the ONE money formatter the header
--  chip uses, so a tile and the chip cannot format the same figure two ways.
function InGameMenuFarmManager25.buildFarmTiles(rows)
    local byId = {}
    for _, r in ipairs(rows or {}) do
        if r.id ~= nil then
            byId[r.id] = r
        end
    end

    local out = {}
    for i, spec in ipairs(InGameMenuFarmManager25.FARM_TILES) do
        local row = byId[spec.id]
        local unknown = row == nil or row.unknown == true
            or (row.valueNumber == nil
                and (row.valueText == nil or row.valueText == ""))
        out[i] = {
            labelKey    = spec.labelKey,
            glyph       = spec.glyph,
            unknown     = unknown,
            valueText   = (not unknown) and row.valueText or nil,
            valueNumber = (not unknown) and row.valueNumber or nil,
            -- ⛔ F-2 / A-10: THE TILE CARRIES ITS OWN FRESHNESS. chosen.html
            -- prints "LIVE" or "as of HH:MM" on all four. Without it a figure
            -- read from a ten-day-old file looks exactly like one read this
            -- second -- the failure F-117 and F-410 both caught, and the exact
            -- confusion that made the 2026-09-17 live test look like broken
            -- code when the data was simply stale.
            -- ⚠ Carried even when the value is unknown: WHEN we last managed
            -- to ask is still a fact, and is the one that explains the gap.
            freshness   = row ~= nil and row.freshness or nil,
            -- D-8 (DEC-222): the time an as-of tile prints beside its mark.
            asOfText    = row ~= nil and row.asOfText or nil,
        }
    end
    return out
end

--- The six FIELDS tiles, in chosen.html's grid order (row 1 then row 2).
--  `source` says where the value comes from: a named field on the row, or a
--  key in its `detail` array.
InGameMenuFarmManager25.FIELD_TILES = {
    { labelKey = "fm25_field_t_area",   source = "area"  },
    { labelKey = "fm25_field_t_owned",  source = "owned" },
    { labelKey = "fm25_field_t_growth", detail = "growth" },
    { labelKey = "fm25_field_t_weeds",  detail = "weeds"  },
    { labelKey = "fm25_field_t_plow",   detail = "plow",  hintKey = "fm25_field_t_plow_hint" },
    { labelKey = "fm25_field_t_lime",   detail = "lime",  hintKey = "fm25_field_t_lime_hint" },
}

--- ⭐ PURE. One field row in, six tiles out, ALWAYS SIX.
--  Returns { labelKey, hintKey, valueText, unknown, differs }.
--
--  ⛔ `differs` IS CARRIED, NOT FLATTENED INTO THE TEXT. A merged field whose
--  parts disagree publishes both the text and the fact that they differ; the
--  page dims it. Folding "they disagree" into the string would make it
--  untranslatable and unstylable, and would let a disagreement read as a
--  measurement.
--  ⛔ A tile for a row that is nil is UNKNOWN, not omitted -- six tiles are a
--  fixed frame, like the four above.
function InGameMenuFarmManager25.buildFieldTiles(row)
    local detail = {}
    for _, d in ipairs((row or {}).detail or {}) do
        if d.key ~= nil then
            detail[d.key] = d
        end
    end

    local out = {}
    for i, spec in ipairs(InGameMenuFarmManager25.FIELD_TILES) do
        local text, unknown, differs = nil, true, false

        if row ~= nil and spec.source == "area" then
            unknown = row.areaUnknown == true or row.areaText == nil
            text = (not unknown) and row.areaText or nil
        elseif row ~= nil and spec.source == "owned" then
            -- ⛔ owned is a BOOLEAN and its l10n keys are the page's, not
            -- core's -- the same yes/no pair populateFieldCell already uses.
            unknown = row.ownedUnknown == true or row.owned == nil
            if not unknown then
                text = row.owned and "fm25_field_yes" or "fm25_field_no"
            end
        elseif row ~= nil and spec.detail ~= nil then
            local d = detail[spec.detail]
            differs = d ~= nil and d.differs == true
            if differs then
                -- ⛔ A DISAGREEMENT IS A MEASUREMENT, NOT AN ABSENCE, and core
                -- says so explicitly: agreeOrDiffer publishes `unknown = FALSE`
                -- with `text = nil` and the breakdown in `partsText`
                -- (FarmManager25.lua:3388). The old test `d.text == nil` folded
                -- that into `unknown`, OVERRIDING the seam's own flag, so every
                -- disagreeing tile rendered the dim `unknown` word -- [[DEC-001]]
                -- running the other way, and the opposite of what the detail
                -- list beside it does with the identical row (:1380, bright).
                -- The same fact must not be dim on the tile and bright in the
                -- list on one screen.
                unknown = false
                -- partsText is the payload; renderTile puts it in the HINT and
                -- puts the `differs` word in the value, which is what the hint
                -- branch below has always claimed to do.
                text = d.partsText
            else
                unknown = d == nil or d.unknown == true or d.text == nil
                text = (not unknown) and d.text or nil
            end
        end

        out[i] = {
            labelKey  = spec.labelKey,
            hintKey   = spec.hintKey,
            valueText = text,
            unknown   = unknown,
            differs   = differs,
            -- Only the owned tile publishes a KEY rather than a rendered
            -- value; the page has to know which, or it would print the key.
            isKey     = (spec.source == "owned") and not unknown or false,
        }
    end
    return out
end

-- ---------------------------------------------------------------------------
-- FOOTERS (chosen.html FOOTER-2, on FIELDS / PRODUCTIONS / MESSAGES only)
--
-- ⛔ ALL THREE ARE PURE COUNTERS AND NONE OF THEM FORMATS A SENTENCE. Each
-- returns the NUMBERS; the page hands them to one l10n string. That split is
-- what makes [[DEC-198]]'s warning obeyable -- "the denominator MOVES with
-- DEC-197 (13/6 -> 16/11), so it must never be hard-coded". A counter that
-- returned "4 of 13 under 24 h" would have baked today's 13 into Lua, where
-- changing it is a code edit in five translated forms rather than a number
-- that moves on its own.
-- ---------------------------------------------------------------------------

--- The order the MESSAGES footer lists statuses in, and the ONLY place that
--  order is stated. ⛔ Built from the STATUS_* CONSTANTS, never from literal
--  key strings: core owns those values, and a copied literal would keep the
--  old spelling silently if one were ever renamed.
--  ⚠ THIS IS A DISPLAY ORDER, NOT A WHITELIST. buildMessagesFooter counts
--  EVERY status it sees, including one added later that is missing here; such
--  a status simply does not get a footer slot until it is added, while the
--  total still includes it. That is why the total is printed from f.total and
--  never summed from these buckets.
--  ⛔ RESOLVED AT CALL TIME, NOT AT LOAD TIME, AND THAT IS NOT A STYLE CHOICE.
--  Written as a table literal dereferencing FarmManager25.STATUS_* at the top
--  level, this file would capture whatever those were WHEN THIS FILE LOADED.
--  FarmManager25.lua is an extraSourceFile and this one is not, so the order
--  is not ours to guarantee -- and if it lost the race every entry would be
--  nil, ipairs would yield nothing, and the footer breakdown would simply
--  never appear. No error, no log line. A function cannot lose that race.
function InGameMenuFarmManager25.footerStatusOrder()
    if FarmManager25 == nil then
        return {}
    end
    return {
        FarmManager25.STATUS_LIVE,
        FarmManager25.STATUS_ANSWERED,
        FarmManager25.STATUS_EXPIRED,
        FarmManager25.STATUS_DISMISSED,
        FarmManager25.STATUS_EVICTED,
        FarmManager25.STATUS_NATIVE,
    }
end

--- ⛔ THE ONLY PLACE A FOOTER SENTENCE IS ASSEMBLED, and it assembles it from
--  NUMBERS the builders returned -- never from a count written into an l10n
--  string. [[DEC-198]]: "the denominator MOVES with DEC-197 (13/6 -> 16/11),
--  so it must never be hard-coded". Every figure below arrives as a %d.
--
--  Parts are joined with a middle dot, the separator chosen.html uses.
local FOOTER_SEP = " \u{00B7} "

--- FOOTER-2 (chosen.html `.fo`): the gap between "TOTAL" and the figures.
InGameMenuFarmManager25.FOOTER_GAP_PX = 22

--- Move `element` to start `gapPx` after `anchor`'s MEASURED text, and --
--  when `keepRightEdge` -- narrow it by the same amount so it never runs past
--  where it used to end. Returns false when either element cannot be
--  measured (no geometry bound), leaving the element where it was.
function InGameMenuFarmManager25.placeAfter(element, anchor, gapPx, keepRightEdge)
    if element == nil or anchor == nil or anchor.position == nil
            or element.position == nil or g_pixelSizeScaledX == nil then
        return false
    end
    local x = anchor.position[1] + anchor:getTextWidth() + gapPx * g_pixelSizeScaledX
    if keepRightEdge and element.size ~= nil then
        element.fm25Home = element.fm25Home or { element.position[1], element.size[1] }
        local home = element.fm25Home
        element:setSize(home[1] + home[2] - x, nil)
    end
    element:setPosition(x, nil)
    return true
end

--- ⛔ FOOTER-2: with a `label`, the first part ("TOTAL") goes in the label
--  (the dim `.fo span:first-child`) and the figures follow it 22px later in
--  the bright element. Without one, the whole sentence goes in `element`, as
--  before. The WORDING is identical either way -- only where TOTAL is drawn
--  moves -- which is what keeps PRODUCTIONS's DEC-198 sentence untouched.
--  An empty `parts` clears BOTH: a lone TOTAL over nothing is still a claim.
function InGameMenuFarmManager25:setFooter(element, parts, label)
    if element == nil then
        return
    end
    local kept = {}
    for _, part in ipairs(parts or {}) do
        if part ~= nil and part ~= "" then
            kept[#kept + 1] = part
        end
    end
    if label == nil then
        element:setText(table.concat(kept, FOOTER_SEP))
        return
    end
    label:setText(kept[1] or "")
    -- Size BEFORE text: RESIZE fits the text to the width it has when set.
    InGameMenuFarmManager25.placeAfter(element, label,
        InGameMenuFarmManager25.FOOTER_GAP_PX, true)
    element:setText(table.concat(kept, FOOTER_SEP, 2))
end

--- ⛔ string.format IS pcall-GUARDED EVERYWHERE IT TOUCHES A TRANSLATION. A
--  translation that dropped a %d would otherwise THROW inside a GUI callback,
--  and a footer that crashes the page is far worse than one that reads oddly.
--  The raw text is the fallback, so a broken translation is VISIBLE rather
--  than silent.
function InGameMenuFarmManager25:fmt(key, ...)
    local text = self.i18n:getText(key)
    local ok, out = pcall(string.format, text, ...)
    if ok then
        return out
    end
    return text
end

--- PRODUCTIONS footer. [[DEC-198]], ruled 2026-09-12: the wording names BOTH
--  counts -- "N of 13 under 24 h · 14 unmeasurable".
--
--  ⛔ THIS SUPERSEDES chosen.html, WHICH PREDATES THE RULING. The mockup says
--  the choice was "NOT DECIDED: (a) 'N under 24 h', or (b) 'N of 13 measurable
--  under 24 h'. Ship BOTH l10n keys and pick at build time." The owner picked
--  NEITHER -- he ruled a third wording carrying both numbers, because
--  "4 under 24 h" on a 27-point farm reads as "23 are fine" when 14 were never
--  assessed: a partial measurement phrased as a total, which is DEC-001's harm
--  one level up. [[DEC-199]] establishes the precedence direction -- when a
--  mockup and a later ruling disagree, the picture is corrected, not the rule.
--
--  Returns { total, measurable, urgent, unmeasurable }. All four, always, so
--  the page never has to infer one from the others:
--    total        every point on the tab
--    measurable   points whose runway is KNOWN (runwayUnknown == false)
--    urgent       of those, the ones at or under the cut-off
--    unmeasurable total - measurable, the count DEC-198 exists to surface
--
--  ⛔ AN UNMEASURABLE POINT IS NOT A SAFE POINT. It is never counted as urgent
--  and never counted as fine -- it is reported separately. Folding it either
--  way is the lie the ruling names.
--  ⛔ AND `urgent` IS COUNTED ON THE NUMBER, NOT THE TEXT. row.runwayHours is
--  the value row.runwayText was rendered from; re-parsing the string would be
--  a second derivation that could disagree with the first.
--  ⚠ `<=` not `<`: a runway of exactly 0 is STARVED RIGHT NOW, the most urgent
--  state the tab has, and a strict `<` on a cut-off of 24 still catches it --
--  but the boundary at exactly 24.0 belongs inside the warning, not outside.
function InGameMenuFarmManager25.buildProductionFooter(points, cutoffHours)
    local cutoff = cutoffHours
    if type(cutoff) ~= "number" then
        cutoff = FarmManager25 ~= nil and FarmManager25.RUNWAY_CUTOFF_H or nil
    end

    local total, measurable, urgent = 0, 0, 0
    for _, p in ipairs(points or {}) do
        total = total + 1
        local hours = p.runwayHours
        if p.runwayUnknown ~= true and type(hours) == "number" then
            measurable = measurable + 1
            if cutoff ~= nil and hours <= cutoff then
                urgent = urgent + 1
            end
        end
    end

    return {
        total        = total,
        measurable   = measurable,
        urgent       = urgent,
        unmeasurable = total - measurable,
    }
end

--- FIELDS footer. chosen.html FIELDS: "never count an unknown area as 0
--  (DEC-001). If any area is unknown the total says so, e.g.
--  '232.5 ha + 1 unknown'".
--
--  Returns { count, area, unknownAreas }. `area` is the sum of the areas we
--  COULD read, and `unknownAreas` is how many we could not.
--  ⛔ A FIELD WITH AN UNKNOWN AREA CONTRIBUTES NOTHING TO THE SUM AND IS
--  COUNTED SEPARATELY. Treating it as 0 would understate the farm silently,
--  and a total that silently understates is worse than one that says it is
--  incomplete -- the player would plan against it.
--  ⛔ `area` IS A NUMBER, NOT A FORMATTED STRING. Same reason as above: the
--  page formats once, and a partial sum stays arithmetic until it is rendered.
function InGameMenuFarmManager25.buildFieldsFooter(rows)
    local count, area, unknownAreas = 0, 0, 0
    for _, r in ipairs(rows or {}) do
        count = count + 1
        local ha = r.areaHa
        if r.areaUnknown == true or type(ha) ~= "number" then
            unknownAreas = unknownAreas + 1
        else
            area = area + ha
        end
    end
    return { count = count, area = area, unknownAreas = unknownAreas }
end

--- MESSAGES footer. chosen.html MESSAGES shows the total plus a breakdown by
--  status: "6 messages · 2 live · 2 answered · 1 expired · 1 dismissed".
--
--  Returns { total, byStatus = { [statusText] = n } }. Keyed on the STATUS
--  STRING core publishes, never on a position, so a new status appears in the
--  table instead of being silently folded into an existing bucket.
--  ⛔ A ROW WITH NO STATUS IS COUNTED IN `total` BUT IN NO BUCKET, and
--  `unstated` says how many. The buckets are then guaranteed not to sum to the
--  total, which is the honest shape: quietly inventing a status to make the
--  arithmetic tidy is how a count starts lying.
function InGameMenuFarmManager25.buildMessagesFooter(rows)
    local total, unstated, byStatus = 0, 0, {}
    for _, r in ipairs(rows or {}) do
        total = total + 1
        local st = r.statusText
        if type(st) == "string" and st ~= "" then
            byStatus[st] = (byStatus[st] or 0) + 1
        else
            unstated = unstated + 1
        end
    end
    return { total = total, unstated = unstated, byStatus = byStatus }
end

-- ---------------------------------------------------------------------------
-- FARM MASTER LIST (chosen.html FARM: "Master-detail replaces the two static
-- BoxLayout columns farmBoxLeft / farmBoxRight")
-- ---------------------------------------------------------------------------

--- Render order for the master list. ⛔ This is FARM_COLUMNS flattened, not a
--  second opinion about order: the two-column layout it replaces read
--  d_contracts, a_money down the left and b_land, c_productions, e_fleet down
--  the right, so a player who has used the old tab finds the groups where they
--  left them. Core still PUBLISHES in citation order (a1..e4); only the render
--  order differs, exactly as FARM_COLUMNS already documented.
InGameMenuFarmManager25.FARM_GROUP_ORDER = {
    "d_contracts", "a_money", "b_land", "c_productions", "e_fleet",
}

--- chosen.html FARM: "Group-to-glyph map: CONTRACTS contract, MONEY finances,
--  LAND field, PRODUCTIONS building, FLEET fleet".
InGameMenuFarmManager25.FARM_GROUP_GLYPHS = {
    d_contracts   = "contract",
    a_money       = "finances",
    b_land        = "field",
    c_productions = "building",
    e_fleet       = "fleet",
}

--- The one row whose value is shown beside the group name in the master list.
--  chosen.html: "The headline per group (d1 / a1 / b2 / c1 / e1) is a design
--  choice the owner can change" -- so it lives here as data, one edit.
InGameMenuFarmManager25.FARM_GROUP_HEADLINE = {
    d_contracts   = "d1",
    a_money       = "a1",
    b_land        = "b2",
    c_productions = "c1",
    e_fleet       = "e1",
}

--- ⭐ PURE. Rows in, master-list entries out. No engine call, no l10n, no self.
--  Returns an array of
--      { group, titleKey, glyph, headlineText, headlineNumber,
--        headlineUnknown, items }
--  one per entry in FARM_GROUP_ORDER, ALWAYS ALL FIVE.
--
--  ⛔ A GROUP WITH NO ROWS IS STILL SHOWN, WITH AN UNKNOWN HEADLINE. Dropping
--  it would silently shrink the menu, and "we could read nothing about your
--  fleet" is information the player needs more than a tidy list -- it is the
--  difference between a missing answer and a missing question (DEC-001). The
--  same rule covers a headline row that is present but flagged unknown.
--
--  ⛔ headlineText IS NOT SET WHEN THE VALUE IS UNKNOWN. The flag is the
--  answer; the page renders the WORD from l10n. Publishing a text here that
--  the page might print instead is how a fabricated value gets on screen.
function InGameMenuFarmManager25.buildFarmMaster(rows)
    local byGroup = {}
    for _, row in ipairs(rows or {}) do
        if row.group ~= nil then
            byGroup[row.group] = byGroup[row.group] or {}
            local g = byGroup[row.group]
            g[#g + 1] = row
        end
    end

    local out = {}
    for _, group in ipairs(InGameMenuFarmManager25.FARM_GROUP_ORDER) do
        local items = byGroup[group] or {}
        local headlineId = InGameMenuFarmManager25.FARM_GROUP_HEADLINE[group]
        local headline = nil
        for _, row in ipairs(items) do
            if row.id == headlineId then
                headline = row
                break
            end
        end
        -- ⛔ D1: A MONEY HEADLINE HAS NO valueText, AND THAT IS THE CONTRACT.
        --  Core resolves a row into EXACTLY ONE of (valueNumber, valueText)
        --  (FarmManager25.lua:2071-2073); valueNumber means "money, and the
        --  page formats it". Testing valueText alone therefore called the
        --  only money headline of the five UNKNOWN while its figure sat right
        --  there in valueNumber -- a real answer reported as an absent one,
        --  which is DEC-001 pointing the wrong way.
        --  The test below is buildFarmTiles' own `unknown` test verbatim: the two
        --  read the same rows and must not disagree about what "unknown"
        --  means, or a tile and its master row would contradict each other
        --  on one figure.
        local unknown = headline == nil or headline.unknown == true
            or (headline.valueNumber == nil
                and (headline.valueText == nil or headline.valueText == ""))
        out[#out + 1] = {
            group           = group,
            titleKey        = InGameMenuFarmManager25.FARM_GROUP_KEYS[group],
            glyph           = InGameMenuFarmManager25.FARM_GROUP_GLYPHS[group],
            headlineText    = (not unknown) and headline.valueText or nil,
            -- Passed through UNFORMATTED, exactly as buildFarmTiles does
            -- (`valueNumber = (not unknown) and row.valueNumber`). This function is pure and static -- it has no self and
            -- so no access to the one money formatter -- and that is the
            -- point: the renderer runs it through the SAME formatter the
            -- header chip uses, so a headline and the chip cannot render one
            -- figure two ways.
            headlineNumber  = (not unknown) and headline.valueNumber or nil,
            headlineUnknown = unknown,
            items           = items,
        }
    end
    return out
end

--- The detail rows for whichever master entry is selected. nil selection or an
--  out-of-range index yields an EMPTY list, never the first group's rows: a
--  detail panel showing CONTRACTS under a heading that says FLEET is the exact
--  class of lie the section work above was written to stop.
function InGameMenuFarmManager25:farmDetailRows()
    local master = self.farmMaster or {}
    local entry = master[self.selectedFarmGroup or 0]
    return entry ~= nil and entry.items or {}
end

-- ---------------------------------------------------------------------------
-- SETTINGS LIST (chosen.html SETTINGS: "List: SmoothList ... SECTIONS-3 group
-- headings with ICONS.gear")
-- ---------------------------------------------------------------------------

--- chosen.html SETTINGS: "Group per row: overlay, scale, width, textSize,
--  cardAlpha -> OVERLAY PANEL; linger, maxTtl, retention, minSeverity ->
--  CARDS & MESSAGES; resetPosition -> POSITION."
--  Keyed on SETTINGS_ROWS[].key, which is core's stable id -- never on the
--  row's position in that table, which is display order and may move.
InGameMenuFarmManager25.SETTINGS_GROUPS = {
    { titleKey = "fm25_settings_group_overlay",
      keys = { "overlay", "scale", "width", "textSize", "cardAlpha" } },
    { titleKey = "fm25_settings_group_cards",
      keys = { "linger", "maxTtl", "retention", "minSeverity" } },
    { titleKey = "fm25_settings_group_position",
      keys = { "resetPosition" } },
}

--- ⭐ PURE. SETTINGS_ROWS in, sectioned groups out:
--      { titleKey, glyph = "gear", items = { row, ... } }
--
--  ⛔ A SETTING IN NO GROUP IS APPENDED, NEVER DROPPED. If core adds an
--  eleventh SETTINGS_ROWS entry and nobody updates SETTINGS_GROUPS above, the
--  tempting behaviour -- render the three known groups -- makes that setting
--  VANISH from the menu with no error: the player simply cannot reach it. So
--  orphans are appended to the last group and remain usable, and
--  tests/test_farm_and_settings_lists.py fails so the grouping gets fixed.
--  Reachable-but-misfiled beats unreachable-and-silent.
--
--  ⛔ A group whose keys all resolve to nothing is OMITTED -- an empty heading
--  over no rows is furniture, not information. That is different from the FARM
--  rule above, and deliberately so: there, the group IS the subject and its
--  emptiness is the finding; here the group is only a divider.
function InGameMenuFarmManager25.buildSettingsGroups(rows)
    local byKey, seen = {}, {}
    for _, row in ipairs(rows or {}) do
        if row.key ~= nil then
            byKey[row.key] = row
        end
    end

    local out = {}
    for _, spec in ipairs(InGameMenuFarmManager25.SETTINGS_GROUPS) do
        local items = {}
        for _, key in ipairs(spec.keys) do
            local row = byKey[key]
            if row ~= nil then
                items[#items + 1] = row
                seen[key] = true
            end
        end
        if #items > 0 then
            out[#out + 1] = { titleKey = spec.titleKey, glyph = "gear", items = items }
        end
    end

    -- Orphans, in the order core published them.
    local orphans = {}
    for _, row in ipairs(rows or {}) do
        if row.key ~= nil and not seen[row.key] then
            orphans[#orphans + 1] = row
        end
    end
    if #orphans > 0 then
        if #out == 0 then
            out[1] = { titleKey = InGameMenuFarmManager25.SETTINGS_GROUPS[1].titleKey,
                       glyph = "gear", items = {} }
        end
        local last = out[#out]
        for _, row in ipairs(orphans) do
            last.items[#last.items + 1] = row
        end
    end
    return out
end

-- ---------------------------------------------------------------------------
-- ATLAS GLYPHS (chosen.html FARM/FIELDS/PRODUCTIONS/MESSAGES build notes)
-- ---------------------------------------------------------------------------

--- ⛔ THE CALL FORM IS THE WHOLE POINT, AND THE WRONG ONE FAILS SILENTLY.
--  The engine signature is
--      BitmapElement:setImageUVs(state, v0,u0, v1,u1, v2,u2, v3,u3)
--  (BitmapElement.lua:197, re-measured 2026-09-12 against gameSource.zip, 951
--  files). Passing an ICONS entry directly -- `setImageUVs(ICONS.leaf)` -- puts
--  the {x,y,w,h} TABLE in `state` and leaves every UV argument nil. The body
--  then does `uvs[i] = v or uvs[i]` (:201-208), so every UV keeps its previous
--  value. ⚠ THE SYMPTOM IS A WRONG ATLAS REGION, NOT A BLANK: the element draws
--  whatever slice it was already showing, which on a fresh Bitmap is the whole
--  2048x1024 sheet. No error, no log line, nothing to grep for.
--
--  ⚠ AND `ref` IS NOT OPTIONAL HERE. GuiUtils.getUVs(str, ref, ...) defaults
--  ref to {1024, 1024} (GuiUtils.lua:230,242). Our atlas is 2048x1024, so
--  omitting ref would halve every u coordinate -- again silently, again a wrong
--  region rather than a blank. Pass {ATLAS_W, ATLAS_H} every time.
--
--  Attested correct form: CpHelpFrame.lua:171 and our own
--  ProductionAdvisor.lua:19231. `state` is nil on purpose --
--  Utils.getNoNil(state, self:getOverlayState()) (:198) supplies the element's
--  current state, which is what we want.
--
--  Returns true when the glyph was applied. Returns FALSE, and leaves the
--  element untouched, for an unknown icon name -- it does not throw: a GUI
--  callback that throws freezes the menu load (see fixInGameMenu), and one
--  missing glyph must not cost the page. ⛔ The gate against a typo is
--  tests/test_atlas_glyphs.py, which asserts every name this file asks for
--  exists in FarmManager25.ICONS -- a runtime false is the last line, not the
--  first.
function InGameMenuFarmManager25.setGlyph(bitmap, iconName, color)
    if bitmap == nil or iconName == nil then
        return false
    end
    local icon = FarmManager25 ~= nil and FarmManager25.ICONS ~= nil
        and FarmManager25.ICONS[iconName] or nil
    if icon == nil then
        return false
    end
    -- ⛔ R1: BIND THE SOURCE, THEN THE UVs. setImageUVs sets UVs and NOTHING
    --  else -- BitmapElement:setImageUVs only writes overlay.uvs[1..8]; the
    --  texture comes from overlay.filename, which it never touches. Our profile
    --  fm25_menuHeaderIcon binds its source via `imageSliceId`, and
    --  GuiOverlay.loadProfileUVs resolves a sliceId to BOTH uvs AND filename
    --  from the BASE GAME's slice table:
    --      overlay["uvs"..st]      = table.clone(slice.uvs)
    --      overlay["filename"..st] = slice.filename
    --  So every one of these Bitmaps starts life pointed at the base game's UI
    --  sheet, and setting only the UVs cropped OUR icon rectangle out of THEIR
    --  texture. The symptom is a wrong picture, never a blank and never a log
    --  line -- which is why this shipped past 2,908 green tests: the reference
    --  resolves, it just resolves to the wrong sheet.
    --
    --  The engine agrees, in its own words: BitmapElement:setImageSlice sets
    --  the UVs and THEN calls setImageFilename(slice.filename). A slice is a
    --  (filename, uvs) PAIR; we were applying half of it.
    --
    --  Attested in-file precedent: setFillTypeIcon (:2978-2980 pre-fix) does
    --  filename-then-UVs, and that path renders correctly today. spec.md:85
    --  prescribed exactly this call and only :86's UV hazard was built.
    --
    --  ⚠ CHEAP TO REPEAT, so it goes on the hot path rather than in an init we
    --  would have to remember to call. GuiOverlay.createOverlay early-returns
    --  ("already created / loaded") when overlay.filename already equals the
    --  filename passed, so after the first glyph this is a string compare.
    --  ⚠ FILENAME FIRST, then UVs: createOverlay deletes and rebuilds the
    --  overlay when the filename CHANGES, so a bitmap that was showing a
    --  fill-type icon must be re-pointed BEFORE its UVs are written, or the
    --  rebuild would discard them.
    bitmap:setImageFilename(Utils.getFilename(FarmManager25.ATLAS_FILE, FarmManager25.MOD_DIR))
    bitmap:setImageUVs(nil, unpack(GuiUtils.getUVs(
        icon, {FarmManager25.ATLAS_W, FarmManager25.ATLAS_H})))
    if color ~= nil then
        bitmap:setImageColor(nil, color[1], color[2], color[3], color[4])
    end
    return true
end

--- [[DEC-195]]: a FILL-TYPE row shows the product's OWN game icon, with our
--  atlas glyph -- DIMMED -- as the fallback. Returns true when a real icon was
--  applied, false when the caller must draw the fallback.
--
--  ⛔ RESOLVED BY TOKEN, NEVER BY THE DISPLAY LABEL. The label is a title and
--  would not match in another language; the token is stable. `getFillTypeByName`
--  upper-cases internally (FillTypeManager.lua:512-514) and rejects anything
--  that is not a valid index name, so a nil or odd token returns nil rather
--  than throwing.
--
--  ⛔ AN EMPTY STRING IS AN ABSENT ICON, NOT AN ICON. `hudOverlayFilename` can
--  be "" as well as nil, and the engine's OWN consumer guards it that way
--  (ControlBarDisplay.lua:709-712). Treating "" as a filename would ask the
--  renderer for a texture called nothing and draw a blank square -- the exact
--  "hides the icon" failure DEC-195 named in the reference mod.
--
--  ⛔ AND THE UVs MUST BE RESET. This Bitmap may already be showing an ATLAS
--  glyph, whose UVs are a small sub-rect of a 2048x1024 sheet. Pointing it at
--  a new file without restoring the full 0..1 range would draw a crop of the
--  crop icon -- silently, and only on rows that had previously fallen back.
--  Same for the tint: a real picture is drawn at full colour, not in the
--  accent the glyph was tinted with.
function InGameMenuFarmManager25.setFillTypeIcon(bitmap, token)
    if bitmap == nil or type(token) ~= "string" or token == "" then
        return false
    end
    if g_fillTypeManager == nil then
        return false
    end
    local ok, desc = pcall(g_fillTypeManager.getFillTypeByName, g_fillTypeManager, token)
    if not ok or desc == nil then
        return false
    end
    local filename = desc.hudOverlayFilename
    if type(filename) ~= "string" or filename == "" then
        return false
    end
    bitmap:setImageFilename(filename)
    bitmap:setImageUVs(nil, 0, 0, 0, 1, 1, 0, 1, 1)
    bitmap:setImageColor(nil, 1, 1, 1, 1)
    return true
end

--- The sender-title -> glyph map for the MESSAGES list (chosen.html:MESSAGES,
--  "Sender glyph map"). fromText is FREE TEXT, so only the known titles map;
--  everything else takes `report`. ⛔ Matched case-insensitively on the exact
--  title, never on a substring: a message from "FIELDS REPORT" is not a FIELDS
--  card, and a substring match would quietly give it the wrong glyph.
InGameMenuFarmManager25.SENDER_GLYPHS = {
    ["PRODUCTIONS"]      = "building",
    ["MORNING BRIEFING"] = "briefing",
    ["CONTRACTS"]        = "contract",
    ["FIELDS"]           = "field",
    ["FLEET"]            = "fleet",
}

function InGameMenuFarmManager25.senderGlyph(fromText)
    if type(fromText) ~= "string" then
        return "report"
    end
    return InGameMenuFarmManager25.SENDER_GLYPHS[fromText:upper()] or "report"
end

--- The five filter buttons, in strip order, with the element id and label key
--  each one uses. ⛔ ONE TABLE so the buttons, their counts and the active
--  highlight cannot disagree about which filter a button stands for.
--  The four severity labels REUSE fm25_severity_* (chosen.html says so
--  explicitly), so only ALL is a new string.
--  M4: chosen.html orders the pills MOST SEVERE FIRST after ALL.
InGameMenuFarmManager25.FILTER_BUTTONS = {
    { filter = "all",      id = "mfAll",      labelKey = "fm25_msg_filter_all" },
    { filter = "critical", id = "mfCritical", labelKey = "fm25_severity_critical" },
    { filter = "warn",     id = "mfWarn",     labelKey = "fm25_severity_warn"     },
    { filter = "info",     id = "mfInfo",     labelKey = "fm25_severity_info"     },
    { filter = "ok",       id = "mfOk",       labelKey = "fm25_severity_ok"       },
}

--- Label each filter button with its name and its count, and highlight the
--  active one. ⛔ COUNTS COME FROM THE UNFILTERED ROWS -- see
--  messageFilterCounts. ⛔ AND EVERY BUTTON IS RE-TINTED, not just the one
--  that changed: highlighting the new one without clearing the old leaves two
--  filters looking active, and the stale one is where the player last clicked.
function InGameMenuFarmManager25:refreshMessageFilters()
    local counts = InGameMenuFarmManager25.messageFilterCounts(self.rows)
    local theme = InGameMenuFarmManager25.engineTheme()
    for _, spec in ipairs(InGameMenuFarmManager25.FILTER_BUTTONS) do
        local button = self[spec.id]
        if button ~= nil then
            local n = counts[spec.filter] or 0
            button:setText(self.i18n:getText(spec.labelKey) .. " " .. n)
            local active = (self.messageFilter == spec.filter)
            if theme ~= nil and theme.text ~= nil then
                -- ⚠ NOT the DEC-199 bright/dim rule wearing a second hat:
                -- nothing here is an unknown. This is SELECTION.
                -- ⛔ M4 (review 2026-09-17): `.fb{color:--brt}` - an INACTIVE
                -- label is BRIGHT on its --rowB pill; `.fb.on{color:--tabOnT}`.
                -- Round 1 dimmed inactive labels because there was no pill to
                -- say "not selected"; now the pill says it.
                local color = active
                    and (theme.cards ~= nil and theme.cards.ok ~= nil
                         and theme.cards.ok.accent or theme.text.body)
                    or theme.text.title
                if color ~= nil then
                    button.textColor = color
                end
            end
            -- `.fb.on{background:--sel;box-shadow:inset 0 0 0 2px --selB}`: the
            -- plate takes the border colour and the inset fill shows over it.
            local plate = self[spec.id .. "Bg"]
            local inset = self[spec.id .. "Fill"]
            local pc = active and InGameMenuFarmManager25.themeColor("cards", "ok", "border")
                or InGameMenuFarmManager25.themeColor("bar", "track")
            if plate ~= nil and plate.setImageColor ~= nil and pc ~= nil then
                plate:setImageColor(nil, pc[1], pc[2], pc[3], pc[4])
            end
            if inset ~= nil and inset.setVisible ~= nil then
                inset:setVisible(active)
            end
        end
    end
end

--- ⛔ THE SELECTED MESSAGE IS CLEARED ON EVERY FILTER CHANGE. A row filtered
--  off the list must not leave its text in the strip below, or the page shows
--  a message the table no longer contains.
function InGameMenuFarmManager25:setMessageFilter(filter)
    self.messageFilter = filter
    self:selectMessage(nil)
    self:updateMessages()
end

--- ⛔ FIVE THIN NAMED HANDLERS, for the same measured reason the sort headers
--  have six: `sendAction`, which dispatches a Button's onClick, is CALLED but
--  never DEFINED in the 951-file gameSource subset, so what arguments reach
--  the handler cannot be established from that corpus.
function InGameMenuFarmManager25:onClickFilterAll()      self:setMessageFilter("all")      end
function InGameMenuFarmManager25:onClickFilterOk()       self:setMessageFilter("ok")       end
function InGameMenuFarmManager25:onClickFilterInfo()     self:setMessageFilter("info")     end
function InGameMenuFarmManager25:onClickFilterWarn()     self:setMessageFilter("warn")     end
function InGameMenuFarmManager25:onClickFilterCritical() self:setMessageFilter("critical") end

--- Selection in the MESSAGES table drives the full-text strip (chosen.html:660).
--  ⚠ The strip element does not exist yet -- the MESSAGES visual rebuild is not
--  in this change -- so this is deliberately a no-op beyond remembering the
--  row. It is here because the SELECTION PROTOCOL is what this change fixes,
--  and a branch that resolves the right row through sectionRows() is the part
--  that had to be got right while the section arithmetic was being written.
--- ⛔ M-8 / A-5: SELECT THE FIRST MESSAGE WHEN NOTHING IS SELECTED.
--  The strip element and the selection branch both already existed, and the
--  strip still rendered EMPTY on the owner's messages4.png while the table
--  painted its first row highlighted. Nothing was broken: the engine paints a
--  default highlight but only calls the delegate on a CHANGE, so
--  onListSelectionChanged never fired and selectMessage was never reached.
--  A highlighted row above an empty strip reads as a strip that does not work.
--  ⚠ Runs AFTER the view is built, and only when nothing is selected, so it
--  cannot fight a real selection or a filter change (which clears on purpose).
function InGameMenuFarmManager25:selectFirstMessageIfNone()
    if self.selectedMessage ~= nil then
        return
    end
    local groups = self.messageGroups
    if groups == nil then
        return
    end
    for _, g in ipairs(groups) do
        local items = g.items
        if items ~= nil and items[1] ~= nil then
            self:selectMessage(items[1])
            return
        end
    end
end

--- ⛔ THE ONE SEVERITY LOOKUP. A message's accent, with the INFO fallback
--  for a severity nobody anticipated. The row (bar, chip, word) and the strip
--  header (glyph, chip, word) both call this, so no two parts of one message
--  can disagree about its colour.
function InGameMenuFarmManager25.severityAccent(severity)
    local cards = InGameMenuFarmManager25.themeColor("cards")
    local family = cards ~= nil and (cards[severity] or cards.info) or nil
    return family ~= nil and family.accent or nil
end

function InGameMenuFarmManager25:selectMessage(row)
    self.selectedMessage = row
    -- ⛔ BLANK WHEN NOTHING IS SELECTED -- not the previous row's text, and
    -- NOT the unknown WORD. "No message selected" is an absence of a QUESTION,
    -- not of data, and the unknown word would answer one nobody asked (the
    -- same distinction the FIELDS merge row already makes). The header's glyph
    -- and chip hide with it, so nothing floats over an empty strip.
    if self.messageStripText ~= nil then
        self.messageStripText:setText(row ~= nil and (row.messageText or "") or "")
    end

    -- M4 `.strip2` header (`.mhd`): sender glyph + sender, `.when`, `.chipS`.
    local glyph, chip = self.messageStripGlyph, self.messageStripChip
    if glyph ~= nil then glyph:setVisible(row ~= nil) end
    if chip ~= nil then chip:setVisible(row ~= nil) end
    if row == nil then
        for _, e in ipairs({ self.messageStripFrom, self.messageStripWhen, self.messageStripStatus }) do
            e:setText("")
        end
        return
    end
    local accent = InGameMenuFarmManager25.severityAccent(row.severity)
    if self.messageStripFrom ~= nil then
        self.messageStripFrom:setText(row.fromText or "")
    end
    -- The same rule as the row's when cell: a real time bright, `unknown` dim.
    self:setUnknownAwareText(self.messageStripWhen, row.whenText)
    if self.messageStripStatus ~= nil then
        self.messageStripStatus:setText(row.statusText ~= nil and self.i18n:getText(row.statusText) or "")
        if accent ~= nil then
            self.messageStripStatus.textColor = accent
        end
    end
    if chip ~= nil and accent ~= nil then
        chip:setImageColor(nil, accent[1], accent[2], accent[3], accent[4])
    end
    if glyph ~= nil then
        InGameMenuFarmManager25.setGlyph(glyph, InGameMenuFarmManager25.senderGlyph(row.fromText), accent)
    end
end

--- FARM master selection. Stores the INDEX, not the entry: farmDetailRows()
--  re-resolves through the current farmMaster, so a refresh that rebuilds the
--  master cannot leave the detail panel holding rows from the previous read.
function InGameMenuFarmManager25:selectFarmGroup(index)
    if type(index) ~= "number" or index < 1
            or index > #(self.farmMaster or {}) then
        self.selectedFarmGroup = nil
        return
    end
    self.selectedFarmGroup = index
    -- Re-render the pane. Guarded because the pure builders above are driven
    -- headlessly by the tests, where no element exists.
    if self.farmDetailBox ~= nil then
        self:buildFarmDetail()
    end
end

--- SETTINGS selection drives the detail pane (chosen.html SETTINGS).
function InGameMenuFarmManager25:selectSetting(row)
    self.selectedSetting = row
    -- Guarded: the pure builders are driven headlessly by the tests, where no
    -- element exists.
    if self.settingsBox ~= nil then
        self:buildSettingsDetail()
    end
end

--- Zero engine reads by design (Stage 1): pulls whatever
--  FarmManager25:getMessageLog() returns, plain data, and renders it as-is.
--  No hardcoded row list.
--  ⛔ CORRECTED 2026-09-01 (F3, MEDIUM, both reviewers): this used to
--  re-sort so `answered == false` rows floated to the top ("unanswered
--  action cards pinned to top"). That was wrong on the data: core derives
--  `answered = (status == STATUS_ANSWERED)`, which in Lua is always `true`
--  or `false`, never `nil` -- proved by execution, nil count 0 against the
--  real log. So `row.answered == false` matched every live, expired,
--  evicted, dismissed AND native card, and pushed every ANSWERED exchange
--  to the bottom -- exactly the reconstruction problem this feature exists
--  to fix. The pin is REMOVED; getMessageLog()'s own newest-first order is
--  rendered unchanged. The contract already documents live-then-history
--  ordering, so no core change is needed for this fix.
function InGameMenuFarmManager25:updateMessages()
    self.rows = {}

    -- ⚠ THE MESSAGE LOG HAS NO meta.status, AND THAT IS NOT AN OVERSIGHT.
    -- getMessageLog() rebuilds from core's in-memory stack/retained arrays
    -- (FarmManager25.lua:1856) -- there is no file, so there is no read that
    -- can fail and no "unavailable" to publish. An empty log with core loaded
    -- is a REAL ANSWER ("No messages yet."), not a gap, which is why
    -- fm25_messages_empty states it affirmatively where fm25_fields_empty
    -- deliberately names OUR gap instead.
    -- The one absence this seam CAN express is core being unreachable, which
    -- is what the guard below has always been for. On that path self.rows
    -- stays empty for a completely different reason, and a footer reading
    -- "TOTAL · 0 messages" would be the same fabrication [[DEC-001]] forbids
    -- on the other two tabs. Captured, and the footer is gated on it.
    local logAvailable = (FarmManager25 ~= nil
        and FarmManager25.getMessageLog ~= nil)
    if logAvailable then
        self.rows = FarmManager25:getMessageLog() or {}
    end

    -- ⛔ GROUPS ARE BUILT BEFORE reloadData(), NOT LAZILY INSIDE THE PROTOCOL
    -- METHODS. The engine asks for the section count once and then indexes into
    -- sections (SmoothListElement.lua:612, :624, :656, :923); if the grouping
    -- were recomputed per call it could answer a different shape halfway through
    -- one rebuild and index past the end of a group. One read moment, one
    -- answer -- the same rule the balance chip had to learn (F-1).
    -- today is nil when the clock is dead; buildMessageGroups then simply never
    -- labels a group TODAY, which is honest rather than wrong.
    local today = FarmManager25 ~= nil and FarmManager25.gameDay ~= nil
        and FarmManager25.gameDay() or nil
    -- ⛔ FILTER, THEN GROUP, THEN SORT WITHIN THE GROUP. The order is the
    -- contract (see buildMessageView): sorting the flat list first would put
    -- the same rows in the same groups in a DIFFERENT order inside them.
    local column, descending = self:currentSort("messages")
    self.messageGroups = InGameMenuFarmManager25.buildMessageView(
        self.rows, today, self.messageFilter, column, descending)
    self:refreshMessageFilters()

    if self.messageTable ~= nil then
        local sg = InGameMenuFarmManager25.SECTION_GLYPHS.messageTable
        InGameMenuFarmManager25.applySectionGlyph(self.messageTable, sg.header, sg.icon)
        self.messageTable:reloadData()
    end

    -- M-8 / A-5: fill the strip for the row the table is already highlighting.
    -- ⛔ AFTER reloadData(), never before: the groups the helper walks are the
    -- ones the table has just been given, so the strip cannot show a message
    -- the list no longer holds.
    self:selectFirstMessageIfNone()

    -- Empty state (owner ruling 2026-09-03): four column headers drawn over
    -- nothing read as a broken page. Driven off the SAME self.rows the list
    -- renders, in the same function, so the line and the list can never
    -- disagree about whether there is anything to show -- the one-read-moment
    -- rule this page already had to learn for the balance chip (F-1).
    -- The string itself lives in the GUI XML, not here: a $l10n_ reference
    -- there is covered by the l10n parity gate, a getText() call here is not.
    -- EMPTY-3: the CARD is what shows and hides; the Text inside it stays
    -- visible and is hidden by its parent, which is what lets the Text keep
    -- its id and its static $l10n_ reference under the parity gate.
    if self.messagesEmptyCard ~= nil then
        self.messagesEmptyCard:setVisible(#self.rows == 0)
    end

    -- FOOTER-2. The per-status breakdown is keyed on the status STRING core
    -- published, so a status nobody anticipated appears in the footer instead
    -- of being folded into an existing bucket.
    -- ⛔ GATED, for the reason recorded at the top of this function: a zero
    -- from an unreachable core is absence, not a count.
    if not logAvailable then
        self:setFooter(self.messagesFooterText, {}, self.messagesFooterLabel)
        return
    end

    local f = InGameMenuFarmManager25.buildMessagesFooter(self.rows)
    local parts = {
        self.i18n:getText("fm25_footer_total"),
        self:fmt("fm25_footer_messages", f.total),
    }
    for _, status in ipairs(InGameMenuFarmManager25.footerStatusOrder()) do
        local n = f.byStatus[status]
        if n ~= nil and n > 0 then
            parts[#parts + 1] = n .. " " .. self.i18n:getText(status)
        end
    end
    -- ⛔ THE NUMBER THAT EXPLAINS THE GAP, AND IT USED TO BE DISCARDED.
    -- buildMessagesFooter's own docstring says a row with no status is counted
    -- in `total` but in NO bucket, so the buckets deliberately do not sum to
    -- the total -- and `unstated` is the only thing that accounts for the
    -- difference. It was computed and asserted by tests and never rendered, so
    -- the player read "6 messages · 2 live · 2 answered" with two
    -- unexplained. Appended only when non-zero, the same rule the runway tail
    -- follows: "0 unstated" is noise, hiding a real 2 is the misreading.
    if f.unstated > 0 then
        parts[#parts + 1] = self:fmt("fm25_footer_unstated", f.unstated)
    end
    self:setFooter(self.messagesFooterText, parts, self.messagesFooterLabel)
end

-- getFarmBalance() REMOVED 2026-09-03 (F-1). It was a three-line delegation to
-- FarmManager25.readLiveValues({}).a1 and updateBalance() was its only caller;
-- the chip now takes row a1 out of the same getFarmRows() result the FARM table
-- renders, so the accessor had no callers left. Its reasoning was not lost with
-- it -- the documented-Farm:getBalance()-first / FOD-fallback rule it carried
-- moved into core on 2026-09-02 and is stated at FarmManager25.lua:1980, which
-- is now the single place that logic lives. Leaving a second balance accessor
-- standing beside the row contract is exactly how one figure grows two answers.

--- Fill the header balance chip. Leaves the chip EMPTY when the balance cannot
--  be read -- the same rule the message log's blank whenText follows: showing a
--  fabricated number is worse than showing nothing.
--  g_i18n:formatMoney is NOT in the fs25-lookup corpus (searched 2026-09-02), so
--  it is called guarded, on FOD's shipping evidence alone
--  (scripts/FarmOperationsDashboard.lua:3322-3330), with a plain-format fallback.
--- The ONE money formatter in this file. Extracted 2026-09-02 so the header
--  balance chip and the FARM money rows cannot render the same figure in two
--  different formats on one screen -- the inconsistency class this work exists
--  to remove. g_i18n:formatMoney is NOT in the fs25-lookup corpus (searched
--  2026-09-02), so it stays guarded, on FOD's shipping evidence alone
--  (scripts/FarmOperationsDashboard.lua:3322-3330), with a plain fallback.
function InGameMenuFarmManager25:formatMoney(v)
    if v == nil then
        return ""
    end
    if g_i18n ~= nil and g_i18n.formatMoney ~= nil then
        return g_i18n:formatMoney(v, 0, true, true)
    end
    return string.format("%d", v)
end

--- Fill the header balance chip from row a1 of the shared getFarmRows() result.
--  Blank when a1 cannot be read; otherwise the figure plus a1's own freshness
--  label.
--
--  ⛔ CORRECTED 2026-09-03 (F-1, adversarial review). This function used to
--  claim the chip and FARM row a1 "CANNOT disagree ... because there is only
--  one accessor." THAT WAS FALSE, and it taught the next reader something
--  untrue. One accessor is not one answer: readLiveValues had one definition
--  but TWO invocations on two cadences (updateBalance from onFrameOpen only;
--  buildFarmRows from initialize and from every switchTab into FARM), so
--  returning to the FARM tab re-read the rows and left the chip showing the
--  balance from whenever the menu was opened. The authors saw this hazard for
--  the row and guarded it; the chip was left unguarded, on all four tabs, with
--  no freshness label to give it away.
--  ⭐ What actually makes two figures agree is ONE READ MOMENT, not one
--  function: the chip is now rendered from row a1 of the very table
--  refreshFarmData() just fetched. It also carries a1's own freshness label, so
--  "is the header live or as-of?" is now answered ON SCREEN rather than by an
--  argument in a comment.
function InGameMenuFarmManager25:updateBalance(rows)
    if self.currentBalanceText == nil then
        return
    end

    -- Row ids are core's published contract (FarmManager25.FARM_ROW_SPEC); a1 is
    -- the balance. Addressed by id, not by position: the render order of the
    -- FARM columns is this file's business and must not move the chip.
    local a1 = nil
    for i = 1, #(rows or {}) do
        if rows[i].id == "a1" then
            a1 = rows[i]
            break
        end
    end

    -- Blank, not "0": a fabricated number is worse than showing nothing, and
    -- guard 8's `unknown` is exactly the flag that says we could not read it.
    if a1 == nil or a1.unknown or a1.valueNumber == nil then
        self.currentBalanceText:setText("")
        return
    end

    -- GUARD 7 reaches the header chrome. Read off the row, never pinned here: if
    -- a1 ever moves to the as-of transport in FARM_ROW_SPEC, the chip follows on
    -- its own. The stamp is appended for an as-of figure, as on every other
    -- as-of mark (D-8, DEC-222).
    local fresh
    if a1.freshness == FarmManager25.FARM_FRESH_LIVE then
        fresh = self.i18n:getText("fm25_farm_live")
    else
        fresh = self.i18n:getText("fm25_farm_asof")
        if a1.asOfText ~= nil then
            fresh = fresh .. " " .. a1.asOfText
        end
    end

    self.currentBalanceText:setText(self:formatMoney(a1.valueNumber) .. " " .. fresh)
end

-- ---------------------------------------------------------------------------
-- THE SECTIONED-LIST PROTOCOL -- one delegate, six lists, and why the shape
-- below is not a matter of taste.
--
-- ⛔ THE DEFECT THIS REPLACES SHIPPED SILENTLY AND WAS INVISIBLE IN REVIEW.
-- `getNumberOfSections()` used to take NO `list` parameter and `return 1`
-- unconditionally, while `getNumberOfItemsInSection(list, section)` and
-- `populateCellForItemInSection(list, section, index, cell)` accepted `section`
-- and IGNORED it. That is coherent only while every list has exactly one
-- section. The moment ANY list needs more -- MESSAGES day groups, below -- the
-- engine asks EVERY list for that same section count, because the count is
-- per-list and ours was not:
--     SmoothListElement.lua:612  numberOfSections = dataSource:getNumberOfSections(self)
--     SmoothListElement.lua:656  section.numItems = dataSource:getNumberOfItemsInSection(self, s)
--     SmoothListElement.lua:923  dataSource:populateCellForItemInSection(self, s, i, element)
-- (measured 2026-09-12 against gameSource.zip, 951 files.) The engine loops
-- `for s = 1, numberOfSections` (:624) and indexes WITHIN each section. A
-- FIELDS list told "there are 4 sections" would answer `#self.fieldRows` four
-- times and render every field FOUR TIMES OVER -- no error, no log line, no
-- crash. A reviewer reading either function alone sees nothing wrong; the bug
-- only exists in the relationship between them.
--
-- ⭐ SO THE SECTION COUNT AND THE ROW SOURCE MUST COME FROM ONE PLACE, KEYED BY
-- LIST IDENTITY. That place is LIST_SOURCES + listPlan(). Every protocol method
-- below is a thin read of the same plan, so the three answers cannot drift
-- apart again -- which is the actual fix. Adding a list is ONE table entry, not
-- four edits in four functions; the FARM master list and the SETTINGS list that
-- chosen.html adds are exactly that one entry each.
--
-- ⛔ AN UNKNOWN LIST RENDERS NOTHING, AND THAT IS DELIBERATE. The old code fell
-- through to `return #self.rows` -- the MESSAGES rows -- so a list that had not
-- loaded, or one added later without a registry entry, would silently borrow the
-- message log's row COUNT and then be populated by the message populator. It
-- would draw message text under field headings. `listPlan` returns nil for an
-- unrecognised list and every method below turns nil into zero rows. Absence
-- renders as empty, never as another list's data (DEC-001).
-- ---------------------------------------------------------------------------

--- Which member holds the rows for which list. `list` and `rows`/`groups` are
--  MEMBER NAMES on self, resolved at call time: the elements do not exist until
--  onGuiSetupFinished has run, and the row arrays are replaced wholesale on
--  every refresh, so neither can be captured once.
InGameMenuFarmManager25.LIST_SOURCES = {
    { list = "fieldList",      rows = "fieldRows"   },
    { list = "prodPointList",  rows = "prodPoints"  },
    -- ONE list for both halves (chosen.html PRODUCTIONS). prodInputList and
    -- prodOutputList are gone; prodFillRows is what buildFillTypeRows produced.
    { list = "prodFillList",   rows = "prodFillRows" },
    { list = "prodLineList",   rows = "prodLines"    },
    -- The FARM master is FLAT: five fixed group entries, one row each. The
    -- GROUPING is what it displays, not how it is sectioned.
    { list = "farmMasterList", rows = "farmMaster" },
    -- Grouped lists. `groups` instead of `rows` is what makes one sectioned;
    -- nothing else in this file branches on list identity for them.
    { list = "messageTable",   groups = "messageGroups" },
    { list = "settingsList",   groups = "settingsGroups" },
}

--- Resolve a list element to its row source. Returns
--    { groups = <array> }  for a sectioned list, or
--    { rows   = <array> }  for a flat one,
--  or nil when the element is not one of ours.
--  ⛔ COMPARES THE ELEMENT ITSELF. Never an index, a name, or a stored
--  "current list": a list that has not loaded is nil and compares equal to
--  nothing, which is the behaviour we want.
function InGameMenuFarmManager25:listPlan(list)
    if list == nil then
        return nil
    end
    for _, src in ipairs(InGameMenuFarmManager25.LIST_SOURCES) do
        local element = self[src.list]
        if element ~= nil and element == list then
            if src.groups ~= nil then
                return { groups = self[src.groups] or {} }
            end
            return { rows = self[src.rows] or {} }
        end
    end
    return nil
end

--- Rows for one section of one list, or nil.
function InGameMenuFarmManager25:sectionRows(list, section)
    local plan = self:listPlan(list)
    if plan == nil then
        return nil
    end
    if plan.groups ~= nil then
        local group = plan.groups[section]
        return group ~= nil and group.items or nil
    end
    -- A flat list has exactly one section. Asked for any other, it has no rows
    -- -- it does not repeat section 1, which is the whole defect above.
    if section ~= 1 then
        return nil
    end
    return plan.rows
end

function InGameMenuFarmManager25:getNumberOfSections(list)
    local plan = self:listPlan(list)
    if plan == nil then
        return 0
    end
    if plan.groups ~= nil then
        return #plan.groups
    end
    return 1
end

function InGameMenuFarmManager25:getNumberOfItemsInSection(list, section)
    local rows = self:sectionRows(list, section)
    return rows ~= nil and #rows or 0
end

--- ⛔ THE NAME IS THE WIRING, AND IT IS NOT A FREE CHOICE.
--  SmoothListElement notifies its DELEGATE by a HARDCODED method name:
--    `if self.delegate.onListSelectionChanged ~= nil then
--         self.delegate:onListSelectionChanged(self, self.selectedSectionIndex, self.selectedIndex)`
--  (gameSource.zip dataS/scripts/gui/elements/SmoothListElement.lua:1937-1938).
--  A frame that spells the method any other way is simply never called, and
--  `~= nil` means it fails SILENTLY -- no error, no log line, no crash.
--  ⛔ AND THE XML ATTRIBUTE IS NOT AN ALTERNATIVE ROUTE. This page used to wire
--  selection with `onSelectionChanged="onFieldListSelectionChanged"` /
--  `="onProdSelectionChanged"` on the two <SmoothList> tags. THE ENGINE NEVER
--  READS THAT ATTRIBUTE: SmoothListElement:loadFromXML registers exactly four
--  callback attributes -- #onScroll, #onDoubleClick, #onClick, #onPressed
--  (:137-140) -- and the string `onSelectionChanged` appears in ZERO of the
--  951 engine Lua files in gameSource.zip. (Both re-measured 2026-09-12; the
--  control, `onListSelectionChanged`, appears in exactly 1.) So both detail
--  panels rendered row 1 from refreshFieldData()/refreshProductionData() and
--  never re-rendered again; the owner saw "Field 35" highlighted beside a panel
--  headed "FIELD 6".
--  ⭐ Our own FS25_Distribution_Redux works for exactly one reason: it happens
--  to name its handler `onListSelectionChanged` on every page
--  (DistributionProductionsPage.lua:279). Its `onSelectionChanged=` attributes
--  are inert cargo. FS25_ProductionAdvisor defines BOTH names with identical
--  bodies (ProductionAdvisorFrame.lua:3071 and :3077) -- only :3077 ever runs.
--  ⚠ SO: DO NOT RENAME THIS METHOD, and do not "tidy" it into per-tab handlers.
--  ⛔ The three PRODUCTIONS detail lists fall through deliberately: they are
--  display-only, and selecting a row in one must not rebuild the panel that
--  owns it.
--  ⚠ `index` IS AN INDEX WITHIN ITS SECTION, not a position in the flat array.
--  For the flat lists the two are the same number and always will be. For
--  messageTable they are NOT, which is why the branch resolves through
--  sectionRows() rather than indexing self.rows directly.
function InGameMenuFarmManager25:onListSelectionChanged(list, section, index)
    if list == self.fieldList then
        self:selectField(index)
    elseif list == self.prodPointList then
        self:selectProductionPoint(index)
    elseif list == self.messageTable then
        local rows = self:sectionRows(list, section)
        self:selectMessage(rows ~= nil and rows[index] or nil)
    elseif list == self.farmMasterList then
        -- The master is flat, so `index` IS the position in farmMaster.
        self:selectFarmGroup(index)
    elseif list == self.settingsList then
        local rows = self:sectionRows(list, section)
        self:selectSetting(rows ~= nil and rows[index] or nil)
    end
end

--- ⛔ RETURNS nil, NOT "", FOR A LIST WITH NO HEADINGS. The engine treats nil as
--  "this section has no header" and skips the header cell entirely
--  (SmoothListElement.lua:641-643); "" would reserve and draw an EMPTY heading
--  row above every list. Today that difference is invisible because no flat
--  list declares #listSectionHeader in the XML, so `hasHeader` is already false
--  for them (:640, cell name read at :197) -- but the moment one does, "" would
--  silently open a blank band. Return the honest nil now.
function InGameMenuFarmManager25:getTitleForSectionHeader(list, section)
    -- ⛔ RESOLVED THROUGH listPlan, NOT AGAINST ONE NAMED LIST. This used to
    -- read `if list ~= self.messageTable then return nil end`, which was
    -- correct while MESSAGES was the only sectioned list -- and became a
    -- SILENT defect the moment SETTINGS became the second one: its three group
    -- headings would simply never appear, the list rendering ungrouped with no
    -- error. Same shape as the section-count defect this registry was built to
    -- kill, one method along.
    local plan = self:listPlan(list)
    if plan == nil or plan.groups == nil then
        return nil
    end
    local group = plan.groups[section]
    if group == nil then
        return nil
    end
    -- MESSAGES titles carry a %d (DAY 3); SETTINGS titles are plain. Both are
    -- l10n keys on the group, so one call serves both and a new sectioned list
    -- needs no branch here at all.
    return self:messageGroupTitle(group)
end

function InGameMenuFarmManager25:populateCellForItemInSection(list, section, index, cell)
    if list == self.fieldList then
        return self:populateFieldCell(index, cell)
    end
    if list == self.prodPointList or list == self.prodFillList
            or list == self.prodLineList then
        return self:populateProductionCell(list, index, cell)
    end
    if list == self.farmMasterList then
        return self:populateFarmMasterCell(index, cell)
    end
    if list == self.settingsList then
        return self:populateSettingsCell(list, section, index, cell)
    end
    if list ~= self.messageTable then
        -- Not one of ours. Draw nothing rather than guess.
        return
    end

    local rows = self:sectionRows(list, section)
    local row = rows ~= nil and rows[index] or nil
    if row == nil then
        return
    end

    -- fromText/messageText are RAW pass-through (sender title, message body) --
    -- never resolved as l10n, per contract.
    -- ⛔ whenText IS NOT RAW PASS-THROUGH, AND THIS LINE USED TO SAY IT WAS.
    -- It read: `whenText can be "" (dead clock); render the blank, no fallback
    -- string.` That shipped a blank cell, and a blank cell in a time column
    -- reads as midnight, or as a column that failed to draw -- it is absence
    -- wearing the costume of data, which is the one thing this product exists
    -- not to do (DEC-001). chosen.html:640 rules it explicitly: render the
    -- flagged word, dim, exactly as every other tab already does for unknowns.
    -- The key is the SAME fm25_farm_unknown the FARM and FIELDS tabs use -- one
    -- word for one meaning across the whole menu, and it already ships in all
    -- five translation files.
    self:setUnknownAwareText(cell:getAttribute("whenText"), row.whenText)
    cell:getAttribute("fromText"):setText(row.fromText)

    -- ⛔ THE SEVERITY BAR AND THE SENDER GLYPH. An unrecognised severity takes
    -- the INFO colour and the report glyph rather than nothing: a row with no
    -- bar reads as a row that failed to draw, and a missing glyph leaves a
    -- 34px hole the eye reads as a broken cell. Neither absence is
    -- informative, so neither is rendered as one.
    -- ⛔ ONE severity lookup for BOTH the bar and the chip. Resolving the
    -- family twice would let the two disagree about an unrecognised severity,
    -- and the whole point of the info fallback is that a row never renders
    -- half-coloured.
    local accent = InGameMenuFarmManager25.severityAccent(row.severity)

    local sevBar = cell:getAttribute("sevBar")
    if sevBar ~= nil and sevBar.setImageColor ~= nil and accent ~= nil then
        sevBar:setImageColor(nil, accent[1], accent[2], accent[3], accent[4])
    end

    -- C1: the status CHIP (chosen.html MESSAGES: "Status 190 (RoundCorner
    -- fs25_shopMoneyBoxBg + Text, tinted by severity)"). The plate takes the
    -- family's BG so the status word keeps its contrast; the word itself is
    -- tinted with the accent further down, the same pairing the cards use.
    -- ⛔ The plate is the chip's BORDER (chosen.html `.chipS` sets
    -- border-color to the severity accent); its inset fill carries the page
    -- background and is static. Round 2 painted this plate cards[sev].bg.
    local chip = cell:getAttribute("statusChip")
    if chip ~= nil and chip.setImageColor ~= nil and accent ~= nil then
        chip:setImageColor(nil, accent[1], accent[2], accent[3], accent[4])
    end
    InGameMenuFarmManager25.setGlyph(cell:getAttribute("senderGlyph"),
        InGameMenuFarmManager25.senderGlyph(row.fromText),
        InGameMenuFarmManager25.themeColor("text", "body"))
    cell:getAttribute("messageText"):setText(row.messageText)

    -- statusText is an l10n KEY, not resolved text -- getMessageLog() is zero
    -- engine calls by design, so core cannot call g_i18n:getText itself. One
    -- of six contract keys: fm25_status_{live,answered,dismissed,expired,
    -- evicted,native}. All six live in every translation_*.xml alongside our
    -- own static keys.
    local statusText = row.statusText ~= nil and self.i18n:getText(row.statusText) or ""
    cell:getAttribute("statusText"):setText(statusText)

    -- Reuse the existing severity palette (FarmManagerTheme.lua) rather than
    -- inventing a second one -- adapted from FOD's priority->colour treatment
    -- at InGameMenuFarmOperationsDashboard.lua:195-202, keyed by our own
    -- severity names instead of a numeric priority.
    -- ⛔ THE SAME `accent` THE BAR AND THE CHIP USE, resolved ONCE above with
    -- the info fallback. This used to run its OWN lookup WITHOUT the fallback,
    -- so an unrecognised severity drew an info-coloured bar and chip around a
    -- WHITE word -- the "two lookups disagree" defect round 2 claimed to have
    -- removed, still standing on the third element. Found in review round 3.
    if accent ~= nil then
        cell:getAttribute("statusText").textColor = accent
    end
end

--- Splice the page into the in-game menu. Isolated in one function, same as
--  FOD's FarmOperationsDashboard.fixInGameMenu (:284-351) -- "the most
--  fragile part of menu work", per the reference mod's own author, so a
--  future game patch has one address to break.
--
--  ⛔ CORRECTED 2026-09-02 (CRITICAL, load stuck at 57%): TabbedMenu:addPage
--  (pageFrameElement, position, tabIconFilename, tabIconUVs,
--  enablingPredicateFunction), documented in the fs25-lookup corpus
--  (docs/script/GUI/TabbedMenu.md#addpage: "Add a page frame to be displayed
--  in the menu at runtime"), was tried first but is REMOVED. Its own
--  registerPage (TabbedMenu.lua:711) inserts the FRAME into pageFrames while
--  :713/:789 register pageRoot = pageFrameElement.elements[1] -- a DIFFERENT
--  object -- into the paging element. rebuildTabList (:262-263) later
--  resolves pageFrames entries BY FRAME via getPageIdByElement, finds no
--  record, and PagingElement.lua:249 throws "attempt to index nil with
--  'disabled'" inside an async i3d-load completion callback -- uncaught
--  there, so the load state machine never advances. The pcall that used to
--  wrap this call did not catch it: the throw happens later, asynchronously,
--  outside the pcall's frame. FOD's manual splice (already shipping,
--  unverified-by-corpus but verified-by-running) registers the SAME object
--  on both sides and has no such defect -- it is now the only path.
--  ⚠ WHICH PATH ACTUALLY RUNS, AND WHERE THE TAB LANDS ON SCREEN, IS A
--  LIVE-TEST QUESTION. Nothing here is asserted by any test in this repo --
--  Testing doctrine forbids stubbing the g_gui boundary, so this function is
--  render-untested by design, not by oversight.
function InGameMenuFarmManager25.fixInGameMenu(frame, pageName, uvs, position, predicateFunc)
    local inGameMenu = g_gui ~= nil and g_gui.screenControllers ~= nil and g_gui.screenControllers[InGameMenu] or nil

    if inGameMenu == nil or inGameMenu.pagingElement == nil then
        return
    end

    -- The TAB icon, NOT icon_FarmManager25.dds -- that one is modDesc.xml's
    -- <iconFilename>, the ModHub store icon: opaque 512px DXT1 with no mip
    -- chain, which is correct there and is exactly what rendered this tab as a
    -- near-black aliased square. Two jobs, two files (as FOD ships them).
    local iconFileName = Utils.getFilename("textures/menuIcon_FarmManager25.dds", FarmManager25.MOD_DIR)

    -- FOD's manual splice (FarmOperationsDashboard.lua:284-351), adapted
    -- variable-for-variable -- the only path now; see the function header for
    -- why TabbedMenu:addPage was removed. `uvs` is passed to addPageTab below
    -- RAW (not GuiUtils.getUVs-wrapped) because addPageTab does no conversion
    -- of its own, unlike addPage's internal call.
    local abovePrices = 0

    if inGameMenu.controlIDs ~= nil then
        inGameMenu.controlIDs[pageName] = nil
    end

    for i = 1, #inGameMenu.pagingElement.elements do
        local child = inGameMenu.pagingElement.elements[i]
        if child == inGameMenu.pageStatistics or child == inGameMenu.pagePrices then
            abovePrices = i
            break
        end
    end

    if abovePrices == 0 then
        abovePrices = position
    end

    inGameMenu[pageName] = frame
    inGameMenu.pagingElement:addElement(inGameMenu[pageName])

    if inGameMenu.exposeControlsAsFields ~= nil then
        inGameMenu:exposeControlsAsFields(pageName)
    end

    for i = 1, #inGameMenu.pagingElement.elements do
        local child = inGameMenu.pagingElement.elements[i]
        if child == inGameMenu[pageName] then
            table.remove(inGameMenu.pagingElement.elements, i)
            table.insert(inGameMenu.pagingElement.elements, abovePrices, child)
            break
        end
    end

    for i = 1, #inGameMenu.pagingElement.pages do
        local child = inGameMenu.pagingElement.pages[i]
        if child.element == inGameMenu[pageName] then
            table.remove(inGameMenu.pagingElement.pages, i)
            table.insert(inGameMenu.pagingElement.pages, abovePrices, child)
            break
        end
    end

    inGameMenu.pagingElement:updateAbsolutePosition()
    inGameMenu.pagingElement:updatePageMapping()
    inGameMenu:registerPage(inGameMenu[pageName], position, predicateFunc)
    inGameMenu:addPageTab(inGameMenu[pageName], iconFileName, GuiUtils.getUVs(uvs))

    for i = 1, #inGameMenu.pageFrames do
        local child = inGameMenu.pageFrames[i]
        if child == inGameMenu[pageName] then
            table.remove(inGameMenu.pageFrames, i)
            table.insert(inGameMenu.pageFrames, abovePrices, child)
            break
        end
    end

    inGameMenu:rebuildTabList()
end

--- Publish the page: load profiles + GUI, splice it into the menu, hand core
--  a single entry point to call from loadMap. No FarmManager25.lua edits
--  happen here -- core wires the call in on their side, and must `source()`
--  this file first (see file header).
--  ⛔ ADDED 2026-09-01 (F4, MEDIUM): register() is called from loadMap, which
--  can run more than once per process (map reload / return to main menu and
--  load again). Without a re-entry guard, a second call would build a
--  second frame and splice it in again via addElement/registerPage/
--  addPageTab/rebuildTabList, which only ever APPEND -- never checked
--  whether the page was already spliced. The retired modal guarded exactly
--  this (`if FarmManager25.settingsGui == nil then`, "instantiated ONCE and
--  reused across map reloads") and that guard had no replacement here until
--  now. ⚠ How many times loadMap actually runs per process is a LIVE-TEST
--  question, not settled by the corpus or by this repo's other code (the
--  reference mod sets an equivalent flag it never reads) -- the guard costs
--  nothing if it never re-enters, and prevents a duplicated tab if it does.
function InGameMenuFarmManager25.register()
    if InGameMenuFarmManager25.frame ~= nil then
        return
    end

    if g_gui == nil then
        return
    end

    local ok, err = pcall(function()
        g_gui:loadProfiles(FarmManager25.MOD_DIR .. "gui/guiProfiles.xml")

        local frame = InGameMenuFarmManager25.new(g_i18n)
        g_gui:loadGui(FarmManager25.MOD_DIR .. "gui/InGameMenuFarmManager25.xml",
            InGameMenuFarmManager25.PAGE_NAME, frame, true)

        --  ⛔ CORRECTED 2026-09-01 (F4, MEDIUM): {0, 0, 512, 512} -> full rect.
        --  GuiUtils.getUVs normalizes against `ref or {1024, 1024}`
        --  (gameSource.zip dataS/scripts/gui/base/GuiUtils.lua:230) and neither
        --  call site passes a ref, so the reference is 1024 REGARDLESS of the
        --  texture's real size. A 512-wide rect therefore selected the
        --  bottom-left QUARTER of the icon. The texture's own dimensions are
        --  irrelevant here -- what matters is the space the rect is stated in.
        InGameMenuFarmManager25.fixInGameMenu(frame, InGameMenuFarmManager25.PAGE_NAME,
            {0, 0, 1024, 1024}, 2, function()
                return g_currentMission ~= nil
            end)

        frame:initialize()
        InGameMenuFarmManager25.frame = frame
    end)

    if not ok then
        print("FarmManager25: in-game menu page registration failed -- " .. tostring(err))
    end
end

--- The open-call for core's keybind repoint (relayed via team-lead,
--  2026-09-01): register() only loads and splices the page; this is the
--  separate call that actually SHOWS the in-game menu on our tab. Opens the
--  menu via g_gui:showGui("InGameMenu") (corpus-documented,
--  docs/script/GUI/Gui.md#showgui: "Display and return a screen identified
--  by name"), then best-effort navigates to our page via
--  TabbedMenu:goToPage(page, muteSound) -- documented in signature only, no
--  Description, so whether this lands on our tab is a LIVE-TEST question,
--  not asserted; if it does nothing, the page is still reachable by clicking
--  its tab.
--
--  No isOpen() predicate is exposed. Per team-lead's 2026-09-01 ruling the
--  onToggleSettings guard stays exactly as it is (g_gui:getIsGuiVisible()):
--  the blocked case (menu already open, key pressed again) has a working
--  manual path (click the tab), so core needs nothing beyond this one call.
function InGameMenuFarmManager25.open()
    if g_gui == nil then
        return
    end

    pcall(function()
        g_gui:showGui("InGameMenu")

        local inGameMenu = g_gui.screenControllers ~= nil and g_gui.screenControllers[InGameMenu] or nil
        if inGameMenu ~= nil and inGameMenu.goToPage ~= nil and InGameMenuFarmManager25.frame ~= nil then
            inGameMenu:goToPage(InGameMenuFarmManager25.frame)
        end
    end)
end
