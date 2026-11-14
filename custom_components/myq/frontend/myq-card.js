/**
 * MyQ garage door card for Home Assistant dashboards:
 *
 *   type: custom:myq-door-card
 *   entity: cover.main_garage
 *   compact: false
 *
 * The integration loads this module on every frontend page, so no dashboard resource is needed.
 * All cards on a page share one subscription to the integration's door list and saved looks.
 */

import { CustomizeDialog } from "./dialogs.js";
import { DoorCard } from "./door-card.js";
import { h, icon } from "./dom.js";
import { loadTranslations, t } from "./i18n.js";
import { cardStyles } from "./styles.js";

const TICK_MS = 30000;
/** Dashboards rebuild cards while being edited, so keep the subscription briefly after the last one. */
const RELEASE_MS = 5000;

/** Text the card picker and editor can show before translations finish loading. */
const ENGLISH = {
  "card.name": "MyQ garage door",
  "card.description": "A garage door with its controls, status, and camera.",
  "card.entity": "Garage door",
  "card.compact": "Compact layout",
  "card.choose": "Choose a MyQ garage door.",
};

function text(key, params) {
  const value = t(key, params);
  return value === key ? (ENGLISH[key] ?? key) : value;
}

/** One subscription to the integration for every card on the page. */
const doors = {
  listeners: new Set(),
  payload: null,
  error: null,
  unsubscribe: null,
  connecting: false,
  releaseTimer: 0,

  watch(hass, listener) {
    clearTimeout(this.releaseTimer);
    this.listeners.add(listener);
    if (this.payload || this.error) listener();
    this.connect(hass);
    return () => {
      this.listeners.delete(listener);
      if (!this.listeners.size) this.releaseTimer = setTimeout(() => this.release(), RELEASE_MS);
    };
  },

  async connect(hass) {
    if (this.unsubscribe || this.connecting) return;
    this.connecting = true;
    try {
      const unsubscribe = await hass.connection.subscribeMessage(
        (payload) => {
          this.payload = payload;
          this.error = null;
          this.notify();
        },
        // Cards may show doors of accounts that hide the sidebar panel.
        { type: "myq/panel/subscribe", scope: "all" },
      );
      if (this.listeners.size) this.unsubscribe = unsubscribe;
      else unsubscribe();
    } catch (error) {
      this.error = error;
      this.notify();
    } finally {
      this.connecting = false;
    }
  },

  release() {
    if (this.listeners.size) return;
    this.unsubscribe?.();
    this.unsubscribe = null;
    this.payload = null;
    this.error = null;
  },

  notify() {
    for (const listener of this.listeners) listener();
  },
};

class MyQDoorCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = null;
    this._hass = null;
    this._card = null;
    this._ready = false;
    this._language = null;
    this._unwatch = null;
    this._content = h("div", { class: "card-root" });
    this.shadowRoot.append(h("style", { text: cardStyles }), this._content);
  }

  /** Lets the dashboard editor build a form instead of showing YAML. */
  static getConfigForm() {
    return {
      schema: [
        {
          name: "entity",
          required: true,
          selector: { entity: { filter: [{ domain: "cover", integration: "myq" }] } },
        },
        { name: "compact", selector: { boolean: {} } },
      ],
      computeLabel: (schema) => text(`card.${schema.name}`),
    };
  }

  static getStubConfig(hass) {
    const entry = Object.values(hass?.entities ?? {}).find(
      (item) => item.platform === "myq" && item.entity_id.startsWith("cover."),
    );
    return { entity: entry?.entity_id ?? "" };
  }

  setConfig(config) {
    // A new card has no door yet when the account has none; it asks for one instead of failing.
    const entity = config?.entity ?? "";
    if (typeof entity !== "string" || (entity && !entity.startsWith("cover."))) {
      throw new Error(text("card.choose"));
    }
    this._config = { ...config, entity };
    this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    const language = hass.locale?.language ?? hass.language ?? "en";
    if (language !== this._language) {
      this._language = language;
      loadTranslations(language).then(() => {
        this._ready = true;
        this._render();
      });
    }
    this.toggleAttribute("dark", Boolean(hass.themes?.darkMode));
    if (first) this._watch();
    if (this._ready) this._update();
  }

  get hass() {
    return this._hass;
  }

  connectedCallback() {
    this._watch();
    clearInterval(this._timer);
    this._timer = setInterval(() => this._card?.tick(), TICK_MS);
    this._card?.setActive(true);
  }

  disconnectedCallback() {
    clearInterval(this._timer);
    this._unwatch?.();
    this._unwatch = null;
    this._card?.setActive(false);
    this._customize?.close();
  }

  getCardSize() {
    return this._config?.compact ? 3 : 8;
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6 };
  }

  /* -------------------------------------------------------------- host interface for DoorCard */

  get settings() {
    return doors.payload?.settings ?? {};
  }

  get confirmCommands() {
    return Boolean(this.settings.confirm);
  }

  appearanceFor(deviceId) {
    return doors.payload?.appearance?.[deviceId];
  }

  openCustomize(deviceId) {
    const all = doors.payload?.doors ?? [];
    const door = all.find((candidate) => candidate.device_id === deviceId);
    if (!door || !this._hass?.user?.is_admin) return;
    this._customize?.close();
    this._customize = new CustomizeDialog(this, door, all, this.appearanceFor(deviceId));
    this._customize.onClose = () => {
      this._customize.scene.destroy();
      this._customize = null;
    };
    this._customize.open();
  }

  /* -------------------------------------------------------------- rendering */

  _watch() {
    if (this._unwatch || !this._hass || !this.isConnected) return;
    this._unwatch = doors.watch(this._hass, () => this._render());
  }

  _render() {
    if (!this._config || !this._ready) return;
    if (!this._config.entity) {
      this._message("mdi:garage-variant", text("card.choose"));
      return;
    }
    if (doors.error) {
      this._message("mdi:alert-circle-outline", t("card.error"));
      return;
    }
    const payload = doors.payload;
    if (!payload) {
      if (!this._card) this._message("mdi:garage-variant", t("panel.loading"));
      return;
    }
    const door = payload.doors.find((candidate) => candidate.entities.cover === this._config.entity);
    if (!door) {
      this._message("mdi:garage-alert-variant", t("card.not_found", { entity: this._config.entity }));
      return;
    }
    this._card ??= new DoorCard(this);
    this._card.setDoor(door, payload.appearance[door.device_id]);
    this._card.setCompact(Boolean(this._config.compact));
    if (this._content.firstChild !== this._card.el) this._content.replaceChildren(this._card.el);
    this._card.setActive(this.isConnected);
    this._update(true);
  }

  _update(force = false) {
    if (this._card?.door && this._hass) this._card.update(this._hass, force);
  }

  _message(iconName, message) {
    this._card?.destroy();
    this._card = null;
    this._content.replaceChildren(h("div", { class: "card-message" }, icon(iconName), h("span", { text: message })));
  }
}

if (!customElements.get("myq-door-card")) {
  customElements.define("myq-door-card", MyQDoorCard);
  // The card picker lists cards from here; load the page's language so it can show translated text.
  loadTranslations(document.documentElement.lang || "en");
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "myq-door-card",
    get name() {
      return text("card.name");
    },
    get description() {
      return text("card.description");
    },
    preview: true,
    documentationURL: "https://github.com/bvdcode/home-assistant-myq#dashboard-card",
  });
}
