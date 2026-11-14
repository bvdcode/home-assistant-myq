/** One garage door: its scene or camera, controls, status chips, activity, and entity details. */

import { CameraView } from "./camera-view.js";
import { DoorScene } from "./door-scene.js";
import {
  activationSource,
  entityLabel,
  formatDuration,
  formatEventTime,
  formatState,
  h,
  haptic,
  icon,
  moreInfo,
  readPreference,
  relativeTime,
  toast,
  writePreference,
} from "./dom.js";
import { currentLocale, t } from "./i18n.js";

const CONFIRM_MS = 4000;
/** "Check now" asks MyQ right away, then rests so repeated taps cannot flood the service. */
const CHECK_COOLDOWN_MS = 15000;
/** Wait for the camera to catch up after MyQ reports that a door stopped. */
const SETTLE_MS = 1500;
/** How long the snapshot taken after a move stays over the door picture. */
const PEEK_MS = 20000;
/** The recorder writes events about once a second; reload activity after that. */
const LOGBOOK_DELAY_MS = 2000;
const ACTIVITY_DAYS = 7;
const ACTIVITY_ROWS = 5;
/** A move is credited to the command that started it if the door stopped within this time. */
const MOVE_MS = 3 * 60000;
/** Minutes a door may stay open before it is highlighted, unless the panel settings say otherwise. */
export const DEFAULT_OPEN_WARNING = 30;

const OPEN_STATES = new Set(["open", "opening"]);
const MOVING = new Set(["opening", "closing"]);
const SETTLED = new Set(["open", "closed"]);

/** Entity roles listed under Details, in display order, with an icon for each state. */
const DETAILS = [
  ["cover", (s) => (OPEN_STATES.has(s?.state) ? "mdi:garage-open-variant" : "mdi:garage-variant")],
  ["work_light", (s) => (s?.state === "on" ? "mdi:lightbulb-on" : "mdi:lightbulb-outline")],
  ["vacation_mode", () => "mdi:beach"],
  ["active_fault", (s) => (s?.state === "on" ? "mdi:alert-circle" : "mdi:check-circle-outline")],
  ["battery_backup_state", () => "mdi:car-battery"],
  ["last_activation_source", () => "mdi:gesture-tap-button"],
  ["absolute_cycle_count", () => "mdi:counter"],
  ["service_cycle_count", () => "mdi:wrench-clock"],
  ["camera", () => "mdi:cctv"],
];

export function unavailableText(hass) {
  return hass?.localize?.("state.default.unavailable") || "Unavailable";
}

/** Minutes after which an open door is highlighted; 0 turns the warning off. */
export function openWarningMinutes(settings) {
  const value = settings?.open_warning;
  return Number.isInteger(value) ? value : DEFAULT_OPEN_WARNING;
}

function faultCodes(stateObj) {
  const codes = stateObj?.attributes?.fault_codes;
  return Array.isArray(codes) ? codes.join(", ") : "";
}

function eventTime(entry) {
  return typeof entry.when === "number" ? entry.when * 1000 : Date.parse(entry.when);
}

function hasCause(entry) {
  return Boolean(
    entry.context_user_id ||
      entry.context_event_type === "automation_triggered" ||
      entry.context_event_type === "script_started",
  );
}

/**
 * Turn logbook entries into the latest open and closed changes, newest first. A change that
 * finished a move is credited to whoever started the move, since MyQ reports the end later.
 */
function summarizeActivity(entries) {
  const sorted = entries
    .map((entry) => ({ ...entry, time: eventTime(entry) }))
    .filter((entry) => Number.isFinite(entry.time))
    .sort((a, b) => a.time - b.time);
  const changes = [];
  let started = null;
  for (const entry of sorted) {
    if (MOVING.has(entry.state)) {
      started = entry;
      continue;
    }
    if (SETTLED.has(entry.state)) {
      const startedRecently = started && entry.time - started.time < MOVE_MS && hasCause(started);
      changes.push({
        state: entry.state,
        time: entry.time,
        cause: hasCause(entry) ? entry : startedRecently ? started : null,
      });
    }
    started = null;
  }
  return changes.reverse().slice(0, ACTIVITY_ROWS);
}

/** The person, automation, or script behind a logbook entry, if Home Assistant knows it. */
function causeName(hass, cause) {
  if (cause.context_event_type === "automation_triggered" || cause.context_event_type === "script_started") {
    return (
      cause.context_name ||
      cause.context_entity_id_name ||
      hass.states[cause.context_entity_id]?.attributes?.friendly_name ||
      ""
    );
  }
  if (cause.context_user_id) {
    const person = Object.values(hass.states).find(
      (stateObj) =>
        stateObj.entity_id.startsWith("person.") && stateObj.attributes?.user_id === cause.context_user_id,
    );
    if (person) return person.attributes.friendly_name ?? "";
    if (hass.user?.id === cause.context_user_id) return hass.user.name ?? "";
  }
  return "";
}

export class DoorCard {
  /**
   * @param host the panel or dashboard card that shows this door. It provides `hass`, `settings`,
   *   `confirmCommands`, optionally `openCustomize`, and receives Home Assistant UI events.
   */
  constructor(host) {
    this.panel = host;
    this.scene = new DoorScene();
    this.camera = null;
    this.view = "door";
    this.compact = false;
    this.door = null;
    this.hass = null;
    this._states = {};
    this._confirm = null;
    this._busy = null;
    this._detailsOpen = false;
    this._checking = false;
    this._checkedUntil = 0;
    this._activity = null;
    this._activityToken = 0;
    this._build();
  }

  _build() {
    this.pillText = h("span");
    this.pill = h("span", { class: "pill" }, h("span", { class: "dot" }), this.pillText);
    this.cameraSlot = h("span", { class: "camera-slot" });
    this.cameraButton = h("button", {
      class: "glass-button",
      type: "button",
      hidden: true,
      onclick: () => this.setView(this.view === "camera" ? "door" : "camera"),
    });
    this.customizeButton = h(
      "button",
      {
        class: "glass-button",
        type: "button",
        hidden: true,
        onclick: () => this.panel.openCustomize?.(this.door.device_id),
      },
      icon("mdi:palette-outline"),
    );
    this.offlineText = h("span");
    this.offline = h("div", { class: "offline", hidden: true }, icon("mdi:cloud-off-outline"), this.offlineText);
    this.peekImage = h("img", { class: "peek-image", alt: "" });
    this.peek = h(
      "button",
      { class: "peek", type: "button", hidden: true, onclick: () => this._openPeek() },
      this.peekImage,
      h("span", { class: "peek-badge" }, icon("mdi:cctv")),
    );
    this.media = h(
      "div",
      { class: "media" },
      this.scene.el,
      this.peek,
      this.offline,
      h(
        "div",
        { class: "media-top" },
        this.pill,
        h("span", { class: "spacer" }),
        this.cameraSlot,
        this.cameraButton,
        this.customizeButton,
      ),
    );
    this.name = h("h2", { class: "name" });
    this.checkIcon = icon("mdi:refresh");
    this.checkButton = h(
      "button",
      { class: "icon-button small check", type: "button", onclick: () => this._check() },
      this.checkIcon,
    );
    this.cameraMoreButton = h(
      "button",
      {
        class: "icon-button small",
        type: "button",
        hidden: true,
        onclick: () => moreInfo(this.panel, this.door.entities.camera),
      },
      icon("mdi:cctv"),
    );
    this.statusText = h("span", { class: "status-text" });
    this.statusSeparator = h("span", { class: "separator", text: "·" });
    this.status = h("span", { class: "status", hidden: true }, h("span", { class: "dot" }), this.statusText, this.statusSeparator);
    this.alertIcon = icon("mdi:clock-alert-outline", "alert-icon");
    this.subtitleText = h("span");
    this.subtitle = h("div", { class: "subtitle" }, this.status, this.alertIcon, this.subtitleText);
    this.openButton = this._actionButton("open", "mdi:arrow-up");
    this.closeButton = this._actionButton("close", "mdi:arrow-down");
    this.chips = h("div", { class: "chips", hidden: true });
    this.detailsLabel = h("span");
    this.detailsToggle = h(
      "button",
      {
        class: "details-toggle",
        type: "button",
        "aria-expanded": "false",
        onclick: () => this._toggleDetails(),
      },
      this.detailsLabel,
      icon("mdi:chevron-down", "chevron"),
    );
    this.detailRows = h("div", { class: "detail-rows" });
    this.activity = h("section", { class: "activity", hidden: true });
    this.detailsCustomizeLabel = h("span");
    this.detailsCustomize = h(
      "button",
      {
        class: "text-button details-customize",
        type: "button",
        hidden: true,
        onclick: () => this.panel.openCustomize?.(this.door.device_id),
      },
      icon("mdi:palette-outline"),
      this.detailsCustomizeLabel,
    );
    this.details = h("div", { class: "details", hidden: true }, this.detailRows, this.activity, this.detailsCustomize);
    this.el = h(
      "article",
      { class: "door-card" },
      this.media,
      h(
        "div",
        { class: "body" },
        h(
          "div",
          { class: "heading" },
          h("div", { class: "heading-row" }, this.name, this.cameraMoreButton, this.checkButton),
          this.subtitle,
        ),
        h("div", { class: "actions" }, this.openButton, this.closeButton),
        this.chips,
        this.detailsToggle,
        this.details,
      ),
    );
  }

  _actionButton(action, iconName) {
    const label = h("span", { class: "label" });
    const button = h(
      "button",
      { class: `action ${action}`, type: "button", onclick: () => this._press(action) },
      h("span", { class: "spinner", "aria-hidden": "true" }),
      icon(iconName, "action-icon"),
      label,
      h("span", { class: "countdown", "aria-hidden": "true" }),
    );
    button.labelElement = label;
    return button;
  }

  /** Apply discovery data and appearance; returns nothing, rendering happens on update(). */
  setDoor(door, appearance) {
    this.door = door;
    this.scene.setAppearance(appearance);
    this.el.dataset.width = this.scene.appearance.width;
    this.name.textContent = door.name;
    const cameraId = door.entities.camera;
    if (cameraId) {
      this.camera ??= new CameraView(this.panel);
      this.camera.setEntity(cameraId);
      this.view = readPreference(`view:${door.device_id}`, "door") === "camera" ? "camera" : "door";
    } else {
      this.camera?.destroy();
      this.camera = null;
      this.view = "door";
      this._hidePeek();
    }
    this._applyView();
    this._states = {};
  }

  setView(view) {
    this.view = view;
    writePreference(`view:${this.door.device_id}`, view);
    this._hidePeek();
    this._applyView();
    if (this.hass) this.update(this.hass, true);
  }

  /** Switch between the full card and a short row with the door picture beside the controls. */
  setCompact(compact) {
    if (compact === this.compact) return;
    this.compact = compact;
    this.el.classList.toggle("compact", compact);
    this._applyView();
    if (this.hass) this._render();
  }

  /** Start or stop camera activity when the panel is shown or hidden. */
  setActive(active) {
    if (!this.camera) return;
    if (active && this._cameraShown()) this.camera.activate();
    else this.camera.deactivate();
  }

  _cameraShown() {
    return this.view === "camera" && Boolean(this.camera) && !this.compact;
  }

  _applyView() {
    const camera = this._cameraShown() ? this.camera : null;
    if (this.camera && !this.camera.el.isConnected) this.scene.el.after(this.camera.el);
    // Keep the hidden scene's space, since it sets the height of the media.
    this.scene.el.classList.toggle("covered", Boolean(camera));
    if (this.camera) {
      this.camera.el.hidden = !camera;
      if (camera && this.panel.isConnected) this.camera.activate();
      else this.camera.deactivate();
    }
    this.cameraSlot.replaceChildren(...(camera ? [camera.controls] : []));
    this.cameraButton.replaceChildren(icon(camera ? "mdi:garage-variant" : "mdi:cctv"));
    this.cameraButton.setAttribute("aria-pressed", String(Boolean(camera)));
    this.el.classList.toggle("camera-view", Boolean(camera));
  }

  /** Re-render if any of this door's entities changed. Returns the new cover state if it changed. */
  update(hass, force = false) {
    this.hass = hass;
    const states = {};
    let changed = force;
    for (const [role, entityId] of Object.entries(this.door.entities)) {
      states[role] = hass.states[entityId];
      if (states[role] !== this._states[role]) changed = true;
    }
    if (!changed) return null;
    const previous = this._states.cover?.state;
    this._states = states;
    this._render();
    this.camera?.update(hass);
    const current = states.cover?.state;
    if (previous === undefined || previous === current) return null;
    if (MOVING.has(current)) this._hidePeek();
    if (SETTLED.has(current) && (SETTLED.has(previous) || MOVING.has(previous))) this._afterMove();
    if (this._detailsOpen) this._scheduleActivity(LOGBOOK_DELAY_MS);
    return current;
  }

  tick() {
    this._renderTime();
    this.camera?.tick();
  }

  destroy() {
    this._clearConfirm();
    for (const timer of [this._settleTimer, this._peekTimer, this._activityTimer, this._checkTimer]) {
      clearTimeout(timer);
    }
    this.scene.destroy();
    this.camera?.destroy();
    this.el.remove();
  }

  _render() {
    const { hass } = this;
    const states = this._states;
    const cover = states.cover;
    const state = cover?.state ?? "unavailable";
    const available = Boolean(cover) && state !== "unavailable";
    const stateText = cover ? formatState(hass, cover) : unavailableText(hass);
    const isAdmin = Boolean(hass.user?.is_admin && this.panel.openCustomize);
    this.el.dataset.state = state;
    this.el.classList.toggle("unavailable", !available);
    this.pill.dataset.state = state;
    this.pillText.textContent = stateText;
    this.status.dataset.state = state;
    this.statusText.textContent = stateText;
    this.offline.hidden = available || this._cameraShown();
    this.offlineText.textContent = stateText;
    this.scene.setState(state);
    this.scene.setLight(states.work_light?.state === "on");
    this.scene.el.setAttribute("role", "img");
    this.scene.el.setAttribute("aria-label", `${this.door.name}: ${stateText}`);

    const camera = this._cameraShown();
    const cameraLabel = camera ? t("door.door_view") : t("door.camera");
    this.cameraButton.hidden = !this.camera;
    this.cameraButton.title = cameraLabel;
    this.cameraButton.setAttribute("aria-label", cameraLabel);
    this.customizeButton.hidden = !isAdmin || camera;
    this.customizeButton.title = t("door.customize");
    this.customizeButton.setAttribute("aria-label", `${t("door.customize")}: ${this.door.name}`);
    this.cameraMoreButton.hidden = !(this.compact && this.camera);
    this.cameraMoreButton.title = t("camera.expand");
    this.cameraMoreButton.setAttribute("aria-label", `${t("camera.expand")}: ${this.door.name}`);
    this.detailsCustomize.hidden = !(this.compact && isAdmin);
    this.detailsCustomizeLabel.textContent = t("door.customize");

    this._renderTime();
    this._renderCheck();
    this._renderButtons();
    this._renderChips();
    this.detailsLabel.textContent = t("door.details");
    if (this._detailsOpen) this._renderDetails();
  }

  /** "Open for 25 min" for open doors, highlighted once they pass the panel's limit. */
  _renderTime() {
    const cover = this._states.cover;
    const changed = cover?.last_changed ? Date.parse(cover.last_changed) : Number.NaN;
    const elapsed = Date.now() - changed;
    let text = this.door.model ?? "";
    let openFor = false;
    let alert = false;
    if (cover?.state === "open" && elapsed >= 60000) {
      text = t("door.open_for", { duration: formatDuration(elapsed, currentLocale()) });
      openFor = true;
      const limit = openWarningMinutes(this.panel.settings);
      alert = limit > 0 && elapsed >= limit * 60000;
    } else if (Number.isFinite(changed)) {
      // Compact cards name the state just before the time, so the time can stand alone.
      const time = relativeTime(changed, currentLocale());
      text = this.compact ? time : t("door.changed", { time });
    }
    this.subtitleText.textContent = text;
    this.subtitle.classList.toggle("alert", alert);
    this.alertIcon.hidden = !alert;
    // Compact cards have no picture overlay, so they show the state here; the alert icon replaces it.
    this.status.hidden = !this.compact || alert;
    this.statusText.hidden = openFor;
    this.statusSeparator.hidden = openFor || !text;
    this.el.classList.toggle("left-open", alert);
  }

  _renderCheck() {
    const checked = this._checkedUntil > Date.now();
    this.checkButton.disabled = this._checking || checked || !this._states.cover;
    this.checkButton.classList.toggle("busy", this._checking);
    this.checkIcon.setAttribute("icon", checked ? "mdi:check" : "mdi:refresh");
    const label = checked ? t("door.checked") : t("door.check");
    this.checkButton.title = label;
    this.checkButton.setAttribute("aria-label", `${label}: ${this.door.name}`);
  }

  _renderButtons() {
    const state = this._states.cover?.state ?? "unavailable";
    const available = Boolean(this._states.cover) && state !== "unavailable";
    let primary = null;
    if (state === "closed" || state === "closing") primary = "open";
    else if (OPEN_STATES.has(state)) primary = "close";
    this._renderButton(this.openButton, "open", available && !OPEN_STATES.has(state), primary === "open");
    this._renderButton(
      this.closeButton,
      "close",
      available && state !== "closed" && state !== "closing",
      primary === "close",
    );
    // Only one of the two applies at a time; compact cards show just that one, so its label fits.
    const single = this.compact && primary !== null;
    this.openButton.hidden = single && primary !== "open";
    this.closeButton.hidden = single && primary !== "close";
  }

  _renderButton(button, action, enabled, primary) {
    const confirming = this._confirm?.action === action;
    const busy = this._busy === action;
    button.disabled = !enabled || busy;
    button.classList.toggle("primary", primary && !confirming);
    button.classList.toggle("confirming", confirming && enabled);
    button.classList.toggle("busy", busy);
    const text = confirming && enabled ? t("door.confirm") : t(`door.${action}`);
    button.labelElement.textContent = text;
    button.setAttribute("aria-label", `${text}: ${this.door.name}`);
  }

  _renderChips() {
    const { hass } = this;
    const states = this._states;
    const chips = [];
    const chip = (iconName, text, tone, role, title) =>
      h(
        "button",
        {
          class: `chip ${tone}`,
          type: "button",
          title: title ?? text,
          onclick: () => moreInfo(this.panel, this.door.entities[role]),
        },
        icon(iconName),
        h("span", { text }),
      );
    if (states.work_light?.state === "on") {
      chips.push(chip("mdi:lightbulb-on", t("door.light_on"), "light", "work_light"));
    }
    if (states.vacation_mode?.state === "on") {
      chips.push(chip("mdi:beach", t("door.vacation"), "vacation", "vacation_mode"));
    }
    if (states.active_fault?.state === "on") {
      const text = t("door.fault", { codes: faultCodes(states.active_fault) }).trim();
      chips.push(chip("mdi:alert-circle", text, "fault", "active_fault"));
    }
    const battery = states.battery_backup_state;
    if (battery && !["unavailable", "unknown"].includes(battery.state)) {
      const warning = /low|discharg|fault|fail|replace|error/i.test(battery.state);
      chips.push(
        chip(
          warning ? "mdi:battery-alert-variant-outline" : "mdi:car-battery",
          `${t("door.battery")} · ${formatState(hass, battery)}`,
          warning ? "warning" : "neutral",
          "battery_backup_state",
          t("door.battery"),
        ),
      );
    }
    this.chips.replaceChildren(...chips);
    this.chips.hidden = chips.length === 0;
  }

  _toggleDetails() {
    this._detailsOpen = !this._detailsOpen;
    this.detailsToggle.setAttribute("aria-expanded", String(this._detailsOpen));
    this.details.hidden = !this._detailsOpen;
    if (this._detailsOpen) {
      this._renderDetails();
      this._scheduleActivity(0);
    }
  }

  _renderDetails() {
    const { hass } = this;
    const rows = [];
    for (const [role, iconFor] of DETAILS) {
      const entityId = this.door.entities[role];
      if (!entityId) continue;
      const stateObj = this._states[role];
      let value = stateObj ? formatState(hass, stateObj) : unavailableText(hass);
      if (role === "active_fault" && stateObj?.state === "on" && faultCodes(stateObj)) {
        value = `${value} · ${faultCodes(stateObj)}`;
      }
      rows.push(
        h(
          "button",
          { class: "detail-row", type: "button", onclick: () => moreInfo(this.panel, entityId) },
          icon(iconFor(stateObj), "detail-icon"),
          h("span", { class: "detail-label", text: stateObj ? entityLabel(stateObj, this.door.name) : entityId }),
          h("span", { class: "detail-value", text: value }),
          icon("mdi:chevron-right", "detail-chevron"),
        ),
      );
    }
    this.detailRows.replaceChildren(...rows);
    this._renderActivity();
  }

  /* -------------------------------------------------------------- recent activity */

  _scheduleActivity(delay) {
    clearTimeout(this._activityTimer);
    this._activityTimer = setTimeout(() => this._loadActivity(), delay);
  }

  async _loadActivity() {
    const { hass } = this;
    if (!this._detailsOpen || !hass) return;
    const token = ++this._activityToken;
    let activity = null;
    if (hass.config?.components?.includes("logbook")) {
      try {
        const entries = await hass.callWS({
          type: "logbook/get_events",
          start_time: new Date(Date.now() - ACTIVITY_DAYS * 86400000).toISOString(),
          entity_ids: [this.door.entities.cover],
        });
        activity = summarizeActivity(Array.isArray(entries) ? entries : []);
      } catch {
        // Without the logbook the section stays hidden.
      }
    }
    if (token !== this._activityToken) return;
    this._activity = activity;
    this._renderActivity();
  }

  _renderActivity() {
    const entries = this._activity;
    this.activity.hidden = !entries;
    if (!entries) return;
    const { hass } = this;
    const cover = this._states.cover;
    const locale = currentLocale();
    const timeFormat = hass.locale?.time_format;
    // MyQ only reports what triggered its latest activation, so it can explain the newest change.
    const source = activationSource(this._states.last_activation_source?.state);
    const rows = entries.map((entry, index) => {
      const name = entry.cause ? causeName(hass, entry.cause) : "";
      const by = name ? t("door.by", { name }) : index === 0 && source ? t("door.via", { source }) : "";
      return h(
        "li",
        { class: "activity-row" },
        icon(entry.state === "open" ? "mdi:garage-open-variant" : "mdi:garage-variant", "activity-icon"),
        h("span", { class: "activity-state", text: formatState(hass, cover, entry.state) }),
        h("time", {
          class: "activity-time",
          datetime: new Date(entry.time).toISOString(),
          text: formatEventTime(entry.time, locale, timeFormat),
        }),
        by ? h("span", { class: "activity-by", text: by }) : null,
      );
    });
    this.activity.replaceChildren(
      h("h3", { class: "activity-title", text: t("door.activity") }),
      rows.length
        ? h("ol", { class: "activity-list" }, rows)
        : h("p", { class: "activity-empty", text: t("door.no_activity") }),
    );
  }

  /* -------------------------------------------------------------- snapshot after a move */

  _afterMove() {
    if (!this.camera?.available) return;
    clearTimeout(this._settleTimer);
    this._settleTimer = setTimeout(() => this._showFreshSnapshot(), SETTLE_MS);
  }

  /** Show a new camera image once a door stops, so you can see where it ended up. */
  async _showFreshSnapshot() {
    if (!this.camera || !this.panel.isConnected || document.hidden) return;
    if (this._cameraShown()) {
      this.camera.refreshNow();
      return;
    }
    const image = await this.camera.snapshot();
    if (!image || !this.panel.isConnected || this._cameraShown()) return;
    image.className = "peek-image";
    this.peekImage.replaceWith(image);
    this.peekImage = image;
    const label = this.compact ? t("camera.expand") : t("door.camera");
    this.peek.title = label;
    this.peek.setAttribute("aria-label", `${label}: ${this.door.name}`);
    this.peek.hidden = false;
    clearTimeout(this._peekTimer);
    this._peekTimer = setTimeout(() => this._hidePeek(), PEEK_MS);
  }

  _hidePeek() {
    clearTimeout(this._peekTimer);
    this.peek.hidden = true;
  }

  _openPeek() {
    this._hidePeek();
    if (this.compact) moreInfo(this.panel, this.door.entities.camera);
    else this.setView("camera");
  }

  /* -------------------------------------------------------------- commands */

  async _check() {
    if (this._checking || this._checkedUntil > Date.now()) return;
    this._checking = true;
    this._renderCheck();
    let checked = false;
    try {
      await this.hass.callService("homeassistant", "update_entity", { entity_id: this.door.entities.cover });
      checked = true;
    } catch (error) {
      toast(this.panel, t("door.check_failed", { name: this.door.name, error: error?.message ?? String(error) }));
    }
    this._checking = false;
    if (checked) {
      this._checkedUntil = Date.now() + CHECK_COOLDOWN_MS;
      clearTimeout(this._checkTimer);
      this._checkTimer = setTimeout(() => this._renderCheck(), CHECK_COOLDOWN_MS + 50);
      if (this._cameraShown()) this.camera.refreshNow();
      haptic("light");
    }
    this._renderCheck();
  }

  _press(action) {
    if (this.panel.confirmCommands && this._confirm?.action !== action) {
      this._clearConfirm();
      this._confirm = {
        action,
        timer: setTimeout(() => {
          this._confirm = null;
          this._renderButtons();
        }, CONFIRM_MS),
      };
      this._renderButtons();
      haptic("warning");
      return;
    }
    this._clearConfirm();
    this._run(action);
  }

  _clearConfirm() {
    if (this._confirm) clearTimeout(this._confirm.timer);
    this._confirm = null;
  }

  async _run(action) {
    this._busy = action;
    this._renderButtons();
    try {
      await this.hass.callService("cover", action === "open" ? "open_cover" : "close_cover", {
        entity_id: this.door.entities.cover,
      });
      haptic("success");
    } catch (error) {
      haptic("failure");
      toast(this.panel, error?.message || t("door.command_failed", { name: this.door.name }));
    } finally {
      this._busy = null;
      this._renderButtons();
    }
  }
}
