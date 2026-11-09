/**
 * MyQ sidebar panel: every garage door and camera the integration discovered, with controls,
 * live status, and camera video. Door appearance is stored by the integration and shared by
 * everyone who opens the panel.
 */

import { CameraView } from "./camera-view.js";
import { CustomizeDialog, SettingsDialog } from "./dialogs.js";
import { DoorCard, openWarningMinutes, unavailableText } from "./door-card.js";
import { DoorScene } from "./door-scene.js";
import {
  fire,
  formatDuration,
  formatState,
  h,
  haptic,
  icon,
  navigate,
  readPreference,
  relativeTime,
  toast,
  writePreference,
} from "./dom.js";
import { currentLocale, loadTranslations, t, tp } from "./i18n.js";
import { styles } from "./styles.js";

const TICK_MS = 30000;
const CONFIRM_MS = 4000;
const INTEGRATION_URL = "/config/integrations/integration/myq";
const CLOSABLE = new Set(["open", "opening", "unknown"]);
/** With this many doors, narrow screens switch to compact cards unless the viewer chose a layout. */
const AUTO_COMPACT_DOORS = 3;
const ACCOUNT_TONES = {
  not_loaded: ["info", "account.connecting", "mdi:cloud-sync-outline"],
  setup_in_progress: ["info", "account.connecting", "mdi:cloud-sync-outline"],
  setup_retry: ["warning", "account.retrying", "mdi:cloud-alert-outline"],
  setup_error: ["error", "account.error", "mdi:alert-circle-outline"],
  migration_error: ["error", "account.error", "mdi:alert-circle-outline"],
  failed_unload: ["error", "account.error", "mdi:alert-circle-outline"],
};

/** Put nodes in order under parent, moving only the ones that are out of place. */
function syncChildren(parent, nodes) {
  nodes.forEach((node, index) => {
    if (parent.children[index] !== node) parent.insertBefore(node, parent.children[index] ?? null);
  });
  while (parent.children.length > nodes.length) parent.lastElementChild.remove();
}

class CameraCard {
  constructor(panel) {
    this.camera = new CameraView(panel);
    this.name = h("h2", { class: "name" });
    this.subtitle = h("div", { class: "subtitle" });
    this.media = h(
      "div",
      { class: "media" },
      this.camera.el,
      h("div", { class: "media-top" }, h("span", { class: "spacer" }), this.camera.controls),
    );
    this.el = h(
      "article",
      { class: "camera-card" },
      this.media,
      h("div", { class: "body" }, h("div", { class: "heading" }, this.name, this.subtitle)),
    );
  }

  setCamera(camera) {
    this.camera.setEntity(camera.entity_id);
    this.name.textContent = camera.name;
    this.subtitle.textContent = camera.model ?? "";
  }

  update(hass) {
    this.camera.update(hass);
  }

  setActive(active) {
    if (active) this.camera.activate();
    else this.camera.deactivate();
  }

  tick() {
    this.camera.tick();
  }

  destroy() {
    this.camera.destroy();
    this.el.remove();
  }
}

class MyQPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._doorCards = new Map();
    this._cameraCards = new Map();
    this._data = null;
    this._error = null;
    this._ready = false;
    this._language = null;
    this._unsubscribe = null;
    this._subscribing = false;
    this._closeAllConfirm = 0;
    this._buildShell();
  }

  set hass(hass) {
    const previous = this._hass;
    this._hass = hass;
    const language = hass.locale?.language ?? hass.language ?? "en";
    if (language !== this._language) {
      this._language = language;
      loadTranslations(language).then(() => {
        this._ready = true;
        this.setAttribute("lang", language);
        this._renderAll();
      });
    }
    this.toggleAttribute("dark", Boolean(hass.themes?.darkMode));
    if (!previous) this._subscribe();
    if (this._ready) this._update();
  }

  get hass() {
    return this._hass;
  }

  set narrow(narrow) {
    this._narrow = narrow;
    this._renderToolbar();
    this._applyLayout();
  }

  set panel(panel) {
    this._panel = panel;
    this._renderToolbar();
  }

  set route(route) {
    this._route = route;
  }

  connectedCallback() {
    this._subscribe();
    this._timer = setInterval(() => this._tick(), TICK_MS);
    for (const card of this._allCards()) card.setActive(true);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
    this._unsubscribe?.();
    this._unsubscribe = null;
    for (const card of this._allCards()) card.setActive(false);
    this._customize?.close();
    this._settings?.close();
  }

  /* ---------------------------------------------------------------- public helpers */

  get confirmCommands() {
    return Boolean(this._data?.settings?.confirm);
  }

  get settings() {
    return this._data?.settings ?? {};
  }

  /** Compact cards fit several doors on a phone; each browser remembers its own choice. */
  get compact() {
    const layout = readPreference("layout", "auto");
    if (layout === "compact") return true;
    if (layout === "full") return false;
    return Boolean(this._narrow) && this.orderedDoors().length >= AUTO_COMPACT_DOORS;
  }

  appearanceFor(deviceId) {
    return this._data?.appearance?.[deviceId];
  }

  orderedDoors() {
    const doors = this._data?.doors ?? [];
    const order = this._data?.settings?.order ?? [];
    const rank = (door) => {
      const index = order.indexOf(door.device_id);
      return index === -1 ? order.length : index;
    };
    return [...doors].sort((a, b) => rank(a) - rank(b));
  }

  openCustomize(deviceId) {
    const door = this._data?.doors.find((candidate) => candidate.device_id === deviceId);
    if (!door || !this._hass.user?.is_admin) return;
    this._customize?.close();
    this._customize = new CustomizeDialog(this, door, this.orderedDoors(), this.appearanceFor(deviceId));
    this._customize.onClose = () => {
      this._customize.scene.destroy();
      this._customize = null;
    };
    this._customize.open();
  }

  openSettings() {
    if (!this._hass.user?.is_admin) return;
    this._settings = new SettingsDialog(this);
    this._settings.onClose = () => {
      this._settings = null;
    };
    this._settings.open();
  }

  /* ---------------------------------------------------------------- data */

  async _subscribe() {
    if (!this._hass || !this.isConnected || this._unsubscribe || this._subscribing) return;
    this._subscribing = true;
    try {
      const unsubscribe = await this._hass.connection.subscribeMessage(
        (payload) => this._onPayload(payload),
        { type: "myq/panel/subscribe" },
      );
      if (this.isConnected) this._unsubscribe = unsubscribe;
      else unsubscribe();
    } catch (error) {
      this._error = error;
      this._renderContent();
    } finally {
      this._subscribing = false;
    }
  }

  _onPayload(payload) {
    this._data = payload;
    this._error = null;
    const doors = this.orderedDoors();
    const doorIds = new Set(doors.map((door) => door.device_id));
    for (const door of doors) {
      let card = this._doorCards.get(door.device_id);
      if (!card) {
        card = new DoorCard(this);
        this._doorCards.set(door.device_id, card);
      }
      card.setDoor(door, payload.appearance[door.device_id]);
    }
    for (const [id, card] of this._doorCards) {
      if (!doorIds.has(id)) {
        card.destroy();
        this._doorCards.delete(id);
      }
    }
    const cameraIds = new Set(payload.cameras.map((camera) => camera.device_id));
    for (const camera of payload.cameras) {
      let card = this._cameraCards.get(camera.device_id);
      if (!card) {
        card = new CameraCard(this);
        this._cameraCards.set(camera.device_id, card);
      }
      card.setCamera(camera);
    }
    for (const [id, card] of this._cameraCards) {
      if (!cameraIds.has(id)) {
        card.destroy();
        this._cameraCards.delete(id);
      }
    }
    this._applyLayout();
    this._renderContent();
    this._update(true);
    this._settings?.refresh();
  }

  /* ---------------------------------------------------------------- rendering */

  _buildShell() {
    this._menuButton = h(
      "button",
      { class: "icon-button menu", type: "button", onclick: () => fire(this, "hass-toggle-menu") },
      icon("mdi:menu"),
    );
    this._title = h("div", { class: "title" });
    this._settingsButton = h(
      "button",
      { class: "icon-button", type: "button", hidden: true, onclick: () => this.openSettings() },
      icon("mdi:cog-outline"),
    );
    this._layoutIcon = icon("mdi:view-list-outline");
    this._layoutButton = h(
      "button",
      { class: "icon-button", type: "button", hidden: true, onclick: () => this._toggleLayout() },
      this._layoutIcon,
    );
    this._content = h("main", { class: "content" });
    this._announcer = h("div", { class: "visually-hidden", role: "status", "aria-live": "polite" });
    // The populated layout is built once; its sections are updated in place so cards are not
    // re-parented, which would restart live camera streams.
    this._bannerArea = h("div", { class: "banners" });
    this._summary = h("section", { class: "summary" });
    this._doorsSection = h("section", { class: "doors" });
    this._camerasTitle = h("h2", { class: "section-title" });
    this._camerasSection = h("section", { class: "camera-grid" });
    this._layout = [this._bannerArea, this._summary, this._doorsSection, this._camerasTitle, this._camerasSection];
    this.shadowRoot.append(
      h("style", { text: styles }),
      h(
        "header",
        { class: "toolbar" },
        this._menuButton,
        this._title,
        h("span", { class: "spacer" }),
        this._layoutButton,
        this._settingsButton,
      ),
      h("div", { class: "scroller" }, this._content),
      this._announcer,
    );
  }

  _showOnly(...children) {
    this._layoutMounted = false;
    this._content.replaceChildren(...children);
  }

  _renderAll() {
    this._summaryKey = null;
    this._renderToolbar();
    this._renderContent();
    this._update(true);
  }

  _renderToolbar() {
    if (!this._hass) return;
    this._title.textContent = this._panel?.title || "MyQ";
    this._menuButton.hidden = !(this._narrow || this._hass.dockedSidebar === "always_hidden");
    this._menuButton.setAttribute("aria-label", this._ready ? t("panel.menu") : "");
    const label = this._ready ? t("panel.settings") : "";
    this._settingsButton.title = label;
    this._settingsButton.setAttribute("aria-label", label);
    this._settingsButton.hidden = !(this._hass.user?.is_admin && this._data);
    const compact = this.compact;
    const layoutLabel = this._ready ? t("panel.compact") : "";
    this._layoutButton.hidden = !this._data?.doors?.length;
    this._layoutButton.title = layoutLabel;
    this._layoutButton.setAttribute("aria-label", layoutLabel);
    this._layoutButton.setAttribute("aria-pressed", String(compact));
    // The icon shows the layout a tap switches to.
    this._layoutIcon.setAttribute("icon", compact ? "mdi:view-agenda-outline" : "mdi:view-list-outline");
  }

  _toggleLayout() {
    writePreference("layout", this.compact ? "full" : "compact");
    this._applyLayout();
  }

  _applyLayout() {
    const compact = this.compact;
    this._doorsSection.classList.toggle("compact", compact);
    for (const card of this._doorCards.values()) card.setCompact(compact);
    this._renderToolbar();
  }

  _renderContent() {
    if (!this._ready) return;
    this._renderToolbar();
    if (this._error) {
      this._showOnly(
        h(
          "div",
          { class: "empty" },
          h("div", { class: "empty-icon" }, icon("mdi:garage-alert-variant")),
          h("h2", { text: t("panel.error") }),
          h("p", { text: this._error?.message ?? String(this._error) }),
          h("button", {
            class: "filled-button",
            type: "button",
            text: t("panel.retry"),
            onclick: () => {
              this._error = null;
              this._renderContent();
              this._subscribe();
            },
          }),
        ),
      );
      return;
    }
    if (!this._data) {
      this._showOnly(
        h(
          "div",
          { class: "doors", "aria-busy": "true", "aria-label": t("panel.loading") },
          h("div", { class: "skeleton" }),
          h("div", { class: "skeleton" }),
        ),
      );
      return;
    }
    const doors = this.orderedDoors();
    const banners = this._banners();
    if (!doors.length && !this._data.cameras.length) {
      const scene = new DoorScene();
      scene.setAppearance({});
      scene.setState("closed");
      const illustration = h("div", { class: "media" }, scene.el);
      this._showOnly(
        ...banners,
        h(
          "div",
          { class: "empty" },
          illustration,
          h("h2", { text: t("panel.empty_title") }),
          h("p", { text: t("panel.empty_text") }),
          this._hass.user?.is_admin
            ? h("button", {
                class: "filled-button",
                type: "button",
                text: t("panel.open_settings"),
                onclick: () => navigate(INTEGRATION_URL),
              })
            : null,
        ),
      );
      return;
    }
    if (!this._layoutMounted) {
      this._content.replaceChildren(...this._layout);
      this._layoutMounted = true;
    }
    this._bannerArea.replaceChildren(...banners);
    this._summary.hidden = !doors.length;
    this._doorsSection.hidden = !doors.length;
    syncChildren(this._doorsSection, doors.map((door) => this._doorCards.get(door.device_id).el));
    const cameras = this._data.cameras;
    this._camerasTitle.textContent = t("panel.cameras");
    this._camerasTitle.hidden = !cameras.length;
    this._camerasSection.hidden = !cameras.length;
    syncChildren(this._camerasSection, cameras.map((camera) => this._cameraCards.get(camera.device_id).el));
    this._summaryKey = null;
    for (const card of this._allCards()) card.setActive(this.isConnected);
  }

  _banners() {
    const isAdmin = this._hass.user?.is_admin;
    return (this._data?.accounts ?? []).flatMap((account) => {
      const tone = ACCOUNT_TONES[account.state];
      if (!tone) return [];
      const [kind, key, iconName] = tone;
      return [
        h(
          "div",
          { class: "banner", role: kind === "error" ? "alert" : "status", dataset: { tone: kind } },
          icon(iconName),
          h("div", { class: "banner-text" }, account.title ? h("strong", { text: account.title }) : null, t(key)),
          isAdmin && kind === "error"
            ? h("button", {
                class: "text-button",
                type: "button",
                text: t("panel.open_settings"),
                onclick: () => navigate(INTEGRATION_URL),
              })
            : null,
        ),
      ];
    });
  }

  _update(force = false) {
    const hass = this._hass;
    if (!hass || !this._data || !this._ready) return;
    const announcements = [];
    for (const door of this.orderedDoors()) {
      const card = this._doorCards.get(door.device_id);
      const changed = card?.update(hass, force);
      if (changed) {
        const stateObj = hass.states[door.entities.cover];
        announcements.push(`${door.name}: ${stateObj ? formatState(hass, stateObj) : unavailableText(hass)}`);
      }
    }
    for (const card of this._cameraCards.values()) card.update(hass);
    if (announcements.length) this._announcer.textContent = announcements.join(". ");
    this._renderSummary();
    this._renderToolbar();
  }

  _renderSummary(force = false) {
    const summary = this._summary;
    const doors = this.orderedDoors();
    if (!this._layoutMounted || !doors.length) return;
    const states = doors.map((door) => this._hass.states[door.entities.cover]?.state ?? "unavailable");
    const count = (predicate) => states.filter(predicate).length;
    const moving = count((state) => state === "opening" || state === "closing");
    const unavailable = count((state) => state === "unavailable");
    const closed = count((state) => state === "closed");
    const notClosed = doors.length - closed - unavailable - moving;
    let tone;
    let iconName;
    let title;
    if (moving) {
      [tone, iconName, title] = ["moving", "mdi:swap-vertical-bold", tp("summary.moving", moving)];
    } else if (notClosed) {
      [tone, iconName, title] = ["open", "mdi:garage-open-variant", tp("summary.open", notClosed)];
    } else if (!unavailable) {
      [tone, iconName, title] = ["closed", "mdi:shield-check-outline", t("summary.all_closed")];
    } else {
      [tone, iconName, title] = ["unavailable", "mdi:cloud-off-outline", tp("summary.unavailable", unavailable)];
    }
    // Doors open longer than the panel's limit, longest first.
    const limit = openWarningMinutes(this.settings);
    const now = Date.now();
    const leftOpen = doors
      .map((door) => ({ door, stateObj: this._hass.states[door.entities.cover] }))
      .filter(({ stateObj }) => stateObj?.state === "open")
      .map((item) => ({ ...item, elapsed: now - Date.parse(item.stateObj.last_changed) }))
      .filter(({ elapsed }) => limit > 0 && elapsed >= limit * 60000)
      .sort((a, b) => b.elapsed - a.elapsed);
    if (tone === "open" && leftOpen.length) {
      [tone, iconName] = ["left_open", "mdi:garage-alert-variant"];
    }
    let alert = false;
    let sub = tone !== "unavailable" && unavailable ? tp("summary.unavailable", unavailable) : "";
    if (leftOpen.length) {
      alert = true;
      sub = t("summary.left_open", {
        name: leftOpen[0].door.name,
        duration: formatDuration(leftOpen[0].elapsed, currentLocale()),
      });
    }
    if (!sub) {
      const latest = doors
        .map((door) => ({ door, stateObj: this._hass.states[door.entities.cover] }))
        .filter(({ stateObj }) => stateObj?.last_changed)
        .sort((a, b) => Date.parse(b.stateObj.last_changed) - Date.parse(a.stateObj.last_changed))[0];
      if (latest && doors.length > 1) {
        sub = t("summary.last_change", {
          name: latest.door.name,
          state: formatState(this._hass, latest.stateObj),
          time: relativeTime(latest.stateObj.last_changed, currentLocale()),
        });
      }
    }
    const closable = doors.filter((door, index) => CLOSABLE.has(states[index]));
    const confirming = this._closeAllConfirm > Date.now();
    const showCloseAll = doors.length > 1 && closable.length > 0;
    const key = JSON.stringify([tone, iconName, title, sub, alert, showCloseAll, confirming]);
    if (!force && key === this._summaryKey) return;
    this._summaryKey = key;
    const children = [
      h("div", { class: "summary-icon", "aria-hidden": "true" }, icon(iconName)),
      h(
        "div",
        { class: "summary-text" },
        h("div", { class: "summary-title", text: title }),
        sub ? h("div", { class: `summary-sub${alert ? " alert" : ""}`, text: sub }) : null,
      ),
    ];
    if (showCloseAll) {
      children.push(
        h(
          "button",
          {
            class: `tonal-button${confirming ? " confirming" : ""}`,
            type: "button",
            onclick: () => this._closeAll(),
          },
          icon("mdi:arrow-down"),
          confirming ? t("summary.confirm_close_all") : t("summary.close_all"),
        ),
      );
    }
    summary.dataset.tone = tone;
    summary.replaceChildren(...children);
  }

  async _closeAll() {
    const doors = this.orderedDoors().filter((door) =>
      CLOSABLE.has(this._hass.states[door.entities.cover]?.state ?? "unavailable"),
    );
    if (!doors.length) return;
    if (this._closeAllConfirm <= Date.now()) {
      this._closeAllConfirm = Date.now() + CONFIRM_MS;
      this._renderSummary();
      setTimeout(() => this._renderSummary(), CONFIRM_MS + 50);
      haptic("warning");
      return;
    }
    this._closeAllConfirm = 0;
    this._renderSummary();
    try {
      await this._hass.callService("cover", "close_cover", {
        entity_id: doors.map((door) => door.entities.cover),
      });
      haptic("success");
    } catch (error) {
      haptic("failure");
      toast(this, error?.message ?? String(error));
    }
  }

  _tick() {
    for (const card of this._allCards()) card.tick?.();
    this._renderSummary(true);
  }

  _allCards() {
    return [...this._doorCards.values(), ...this._cameraCards.values()];
  }
}

if (!customElements.get("myq-panel")) customElements.define("myq-panel", MyQPanel);
