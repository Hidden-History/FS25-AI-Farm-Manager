--[[
    FarmManagerSettingsGui.lua
    --------------------------
    The g_gui settings dialog for AI Farm Manager 25 (S158; rows redesigned
    item 19/S162). A THIN DialogElement shell: it renders a titled modal
    (base-game dialog chrome), reflects the live settings as native ‹value›
    stepper rows, and routes each change to the matching FarmManager25 method,
    which owns the apply + persist. All real logic lives on FarmManager25 so it
    stays lupa-testable; this file is engine-only and is skipped wholesale in a
    headless environment.

    The three preferences (overlay on/off, panel size, off-mode linger) are
    base-game MultiTextOption steppers, the idiom Distribution Redux uses
    (DistributionSettingsPage.lua): setTexts() the choice labels once, setState()
    the live index on open, and on each click apply by the 1-based state index.
    getScaleIndex/getLingerIndex + cfgSetScaleIndex/cfgSetLingerIndex on
    FarmManager25 are the index-addressable counterparts of the cfgCycle*
    keybind path (identical apply+persist). The one action (Reset position) has
    no value, so it stays a plain button -> cfgResetPosition.

    Base class + lifecycle are AutoDrive's VERIFIED DialogElement shape
    (ScanConfirmationGUI.lua / NotificationsHistoryGUI.lua): Class(x,
    DialogElement); x.new(target) -> DialogElement.new(target, mt); onOpen
    chains its superclass then re-reads live state. The XML wires
    onOpen/onClose/onCreate on the root <GUI> and the stepper onClick + row
    onCreate handlers by name; element ids in the XML surface here as self.<id>.

    Registered by FarmManager25:registerSettingsGui (g_gui:loadProfiles +
    loadGui) and shown by FarmManager25:onToggleSettings (g_gui:showDialog,
    default Ctrl+Alt+Period). Usable on foot or in a vehicle -- it's a modal
    GUI, so there is no camera-suppression concern here.
]]

FarmManagerSettingsGui = FarmManagerSettingsGui or {}

-- Headless guard: the g_gui framework (Class / DialogElement) is absent in the
-- lupa test harness and on a dedicated server. Without it this file cannot and
-- must not define a screen -- leave FarmManagerSettingsGui a bare table (its
-- .new stays nil, so FarmManager25:registerSettingsGui skips it cleanly) and
-- return. The settings key then no-ops; nothing else is affected.
if Class == nil or DialogElement == nil then
    return
end

-- Stepper choice labels. Order MUST mirror the FarmManager25 preset arrays:
-- SCALE_PRESETS {0.5,0.6,0.72,0.85,1.0,1.25} and LINGER_PRESETS_MS
-- {10000,15000,30000,60000}. Overlay is a plain binary: index 1 = ON, 2 = OFF.
local OVERLAY_TEXTS = {"ON", "OFF"}
local SCALE_TEXTS   = {"50%", "60%", "72%", "85%", "100%", "125%"}
local LINGER_TEXTS  = {"10s", "15s", "30s", "60s"}

local FarmManagerSettingsGui_mt = Class(FarmManagerSettingsGui, DialogElement)

function FarmManagerSettingsGui.new(target)
    return DialogElement.new(target, FarmManagerSettingsGui_mt)
end

--- Populate a stepper's choice labels + current index (onOpen only: labels are
--  static, so setTexts runs once here, not on every change). Every access is
--  nil-guarded: a profile/id mismatch or an engine without setTexts/setState
--  must degrade to a static (still clickable) control, never a dialog-open crash.
local function applyOption(element, texts, index)
    if element == nil then return end
    if element.setTexts ~= nil then
        element:setTexts(texts)
    end
    if element.setState ~= nil then
        element:setState(index)
    end
end

--- Re-sync ONE stepper's selected index after its own change, without touching
--  its labels or the other rows (setState only -- no setTexts, matching the
--  DistributionSettingsPage idiom: setTexts once at setup, setState on change).
local function syncOption(element, index)
    if element ~= nil and element.setState ~= nil then
        element:setState(index)
    end
end

--- Per-row: subtle alternating tint, matching the base settings look. Verbatim
--  DistributionSettingsPage shape -- start from false, use, then toggle -- so
--  row 1 = pal[false]. Best-effort and fully guarded; an engine without the
--  palette just skips it.
function FarmManagerSettingsGui:onCreateSettingRow(element)
    if self._rowEven == nil then self._rowEven = false end
    local pal = (InGameMenuSettingsFrame ~= nil) and InGameMenuSettingsFrame.COLOR_ALTERNATING or nil
    if pal ~= nil and pal[self._rowEven] ~= nil and element ~= nil and element.setImageColor ~= nil then
        element:setImageColor(nil, table.unpack(pal[self._rowEven]))
    end
    self._rowEven = not self._rowEven
end

--- setTexts (once) + setState the live index for all three steppers.
function FarmManagerSettingsGui:onOpen()
    FarmManagerSettingsGui:superClass().onOpen(self)
    applyOption(self.fm25OverlayOption, OVERLAY_TEXTS, FarmManager25.overlayOn and 1 or 2)
    applyOption(self.fm25ScaleOption,   SCALE_TEXTS,   FarmManager25:getScaleIndex())
    applyOption(self.fm25LingerOption,  LINGER_TEXTS,  FarmManager25:getLingerIndex())
end

--- Overlay stepper: state 1 = ON, 2 = OFF. Same flip as the keybind's
--  setOverlayOn. Re-sync only this row to the applied mode.
function FarmManagerSettingsGui:onOverlayChanged(state)
    FarmManager25:setOverlayOn(state == 1)
    syncOption(self.fm25OverlayOption, FarmManager25.overlayOn and 1 or 2)
end

--- Panel-size stepper: apply SCALE_PRESETS[state] (rebuild + persist); re-sync
--  only this row.
function FarmManagerSettingsGui:onScaleChanged(state)
    FarmManager25:cfgSetScaleIndex(state)
    syncOption(self.fm25ScaleOption, FarmManager25:getScaleIndex())
end

--- Off-mode-linger stepper: apply LINGER_PRESETS_MS[state] (persist, MAX>=MIN);
--  re-sync only this row.
function FarmManagerSettingsGui:onLingerChanged(state)
    FarmManager25:cfgSetLingerIndex(state)
    syncOption(self.fm25LingerOption, FarmManager25:getLingerIndex())
end

--- Reset panel position: an action, not a value -> plain button.
function FarmManagerSettingsGui:onClickResetPosition()
    FarmManager25:cfgResetPosition()
end
