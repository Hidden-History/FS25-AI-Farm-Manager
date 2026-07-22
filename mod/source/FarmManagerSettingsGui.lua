--[[
    FarmManagerSettingsGui.lua
    --------------------------
    The g_gui settings dialog for AI Farm Manager 25 (S158). A THIN
    DialogElement shell: it renders a titled modal (base-game dialog chrome),
    reflects the live settings as button labels, and routes each click to the
    matching FarmManager25:cfg* method, which owns the apply + persist. All real
    logic lives on FarmManager25 so it stays lupa-testable; this file is
    engine-only and is skipped wholesale in a headless environment.

    Base class + lifecycle are AutoDrive's VERIFIED DialogElement shape
    (ScanConfirmationGUI.lua / NotificationsHistoryGUI.lua): Class(x,
    DialogElement); x.new(target) -> DialogElement.new(target, mt); onOpen
    chains its superclass; each onClick* handler applies then refreshLabels()
    re-reads state; the Back button closes via the inherited onClickBack(). The
    XML wires onOpen/onClose/onCreate on the root <GUI> and the button onClick
    handlers by name; element ids in the XML surface here as self.<id>.

    Registered by FarmManager25:registerSettingsGui (g_gui:loadProfiles +
    loadGui, AutoDrive Gui.lua:3,60) and shown by FarmManager25:onToggleSettings
    (g_gui:showDialog, default Ctrl+Alt+Period). Usable on foot or in a vehicle
    -- it's a modal GUI, so there is no camera-suppression concern here.
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

local FarmManagerSettingsGui_mt = Class(FarmManagerSettingsGui, DialogElement)

function FarmManagerSettingsGui.new(target)
    return DialogElement.new(target, FarmManagerSettingsGui_mt)
end

--- Reflect the live settings into the button labels. Every element access is
--  nil-guarded: a profile/id mismatch or an engine without ButtonElement:setText
--  must degrade to a static (still clickable) button, never a dialog-open crash.
function FarmManagerSettingsGui:refreshLabels()
    if self.fm25OverlayButton ~= nil and self.fm25OverlayButton.setText ~= nil then
        self.fm25OverlayButton:setText("Panel: " .. (FarmManager25.overlayOn and "ON" or "OFF"))
    end
    if self.fm25ScaleButton ~= nil and self.fm25ScaleButton.setText ~= nil then
        local pct = math.floor((FarmManager25.DESIGN.uiScale or 1) * 100 + 0.5)
        self.fm25ScaleButton:setText(string.format("Panel size: %d%%", pct))
    end
    if self.fm25LingerButton ~= nil and self.fm25LingerButton.setText ~= nil then
        local secs = math.floor(FarmManager25.MIN_TTL_MS / 1000 + 0.5)
        self.fm25LingerButton:setText(string.format("Off-mode linger: %ds", secs))
    end
end

function FarmManagerSettingsGui:onOpen()
    FarmManagerSettingsGui:superClass().onOpen(self)
    self:refreshLabels()
end

function FarmManagerSettingsGui:onClickToggleOverlay()
    FarmManager25:cfgToggleOverlay()
    self:refreshLabels()
end

function FarmManagerSettingsGui:onClickCycleScale()
    FarmManager25:cfgCycleScale()
    self:refreshLabels()
end

function FarmManagerSettingsGui:onClickCycleLinger()
    FarmManager25:cfgCycleLinger()
    self:refreshLabels()
end

function FarmManagerSettingsGui:onClickResetPosition()
    FarmManager25:cfgResetPosition()
end
