/**
 * MyQ garage door card for Home Assistant dashboards:
 *
 *   type: custom:myq-door-card
 *   entity: cover.main_garage
 *   compact: false
 *
 * The integration loads this module on every frontend page, so no dashboard resource is needed. It
 * stays small: the door drawing, camera, dialogs, and styles load when the first card is shown.
 * All cards on a page share one subscription to the integration's door list and saved looks.
 */

import { h, icon } from "./dom.js";
import { loadTranslations, t, translationsLoaded } from "./i18n.js";

/**
 * The modules that draw and run a card, once loaded.
 * @type {{
 *   DoorCard: typeof import("./door-card.js").DoorCard,
 *   CustomizeDialog: typeof import("./dialogs.js").CustomizeDialog,
 *   cardStyles: string,
 * } | null}
 */
let parts = null;
/** @type {Promise<void> | null} */
let loadingParts = null;

/** Load the modules that draw and run a card; a failed load is tried again by the next card shown. */
function loadParts() {
  if (!loadingParts) {
    loadingParts = Promise.all([import("./door-card.js"), import("./dialogs.js"), import("./styles.js")]).then(
      ([doorCard, dialogs, styles]) => {
        parts = {
          DoorCard: doorCard.DoorCard,
          CustomizeDialog: dialogs.CustomizeDialog,
          cardStyles: styles.cardStyles,
        };
      },
      (error) => {
        loadingParts = null;
        throw error;
      },
    );
  }
  return loadingParts;
}

const TICK_MS = 30000;
/** Dashboards rebuild cards while being edited, so keep the subscription briefly after the last one. */
const RELEASE_MS = 5000;
/** How soon to try again after the subscription fails, as it does while MyQ is still starting. */
const RETRY_MS = 10000;

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
  /** @type {import("./types.js").PanelPayload | null} */
  payload: null,
  error: null,
  unsubscribe: null,
  connecting: false,
  releaseTimer: 0,
  retryTimer: 0,
  attempt: 0,
  connection: null,

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
    const attempt = ++this.attempt;
    clearTimeout(this.retryTimer);
    this.followReconnects(hass);
    try {
      const unsubscribe = await hass.connection.subscribeMessage(
        (payload) => {
          this.payload = payload;
          this.error = null;
          this.notify();
        },
        // Cards may show doors of accounts that hide the sidebar panel.
        { type: "myq/panel/subscribe", scope: "all" },
        { resubscribe: false },
      );
      if (attempt === this.attempt && this.listeners.size) this.unsubscribe = unsubscribe;
      else unsubscribe();
    } catch (error) {
      if (attempt !== this.attempt) return;
      this.error = error;
      this.notify();
      this.retryTimer = setTimeout(() => {
        if (this.listeners.size) this.connect(hass);
      }, RETRY_MS);
    } finally {
      if (attempt === this.attempt) this.connecting = false;
    }
  },

  /**
   * Subscribe again whenever the websocket reconnects. The library can do that itself, but it drops a
   * subscription that fails then, and right after Home Assistant restarts the websocket is back before
   * MyQ has registered its commands. A request still in flight when the connection dropped never
   * settles, so a reconnect starts a new attempt instead of waiting for it.
   */
  followReconnects(hass) {
    if (this.connection === hass.connection) return;
    this.connection = hass.connection;
    hass.connection.addEventListener("ready", () => {
      this.attempt += 1;
      this.connecting = false;
      this.unsubscribe = null;
      if (this.listeners.size) this.connect(hass);
    });
  },

  release() {
    if (this.listeners.size) return;
    clearTimeout(this.retryTimer);
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
    this._style = h("style");
    this.shadowRoot.append(this._style, this._content);
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
    // If strings failed to load, the next update after the card is shown again fetches them again.
    if (!translationsLoaded()) this._language = null;
    if (!this._style.textContent) {
      loadParts().then(
        () => {
          this._style.textContent = parts.cardStyles;
          this._render();
        },
        () => this._message("mdi:alert-circle-outline", text("card.error")),
      );
    }
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
    // Until the settings arrive, for example while the card is shown again, ask rather than assume.
    return doors.payload ? Boolean(this.settings.confirm) : true;
  }

  appearanceFor(deviceId) {
    return doors.payload?.appearance?.[deviceId];
  }

  openCustomize(deviceId) {
    const all = doors.payload?.doors ?? [];
    const door = all.find((candidate) => candidate.device_id === deviceId);
    if (!door || !this._hass?.user?.is_admin) return;
    this._customize?.close();
    this._customize = new parts.CustomizeDialog(this, door, all, this.appearanceFor(deviceId));
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
    if (!this._config || !this._ready || !this._style.textContent) return;
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
    // Another door gets a new DoorCard, so a pending confirmation, activity, or camera image cannot carry over.
    if (this._card && this._card.door?.device_id !== door.device_id) {
      this._card.destroy();
      this._card = null;
    }
    this._card ??= new parts.DoorCard(this);
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
  const page = /** @type {any} */ (window);
  page.customCards = page.customCards || [];
  page.customCards.push({
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
