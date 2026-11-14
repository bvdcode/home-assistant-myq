/** Camera snapshots with on-demand live video through Home Assistant's own camera player. */

import { h, icon, moreInfo, relativeTime, supportsFeature } from "./dom.js";
import { currentLocale, t } from "./i18n.js";

/** Matches the integration's shared 30-second snapshot cache, so polling never adds cloud requests. */
const REFRESH_MS = 30000;
const STREAM_FEATURE = 2;
let playerReady;

/** Load Home Assistant's camera player element if no other page has loaded it yet. */
function ensureCameraPlayer() {
  if (customElements.get("ha-camera-stream")) return Promise.resolve(true);
  playerReady ??= (async () => {
    try {
      const helpers = await window.loadCardHelpers?.();
      await helpers?.importMoreInfoControl?.("camera");
    } catch {
      // The timeout below decides whether the player became available.
    }
    const defined = await Promise.race([
      customElements.whenDefined("ha-camera-stream").then(() => true),
      new Promise((resolve) => setTimeout(() => resolve(false), 8000)),
    ]);
    if (!defined) playerReady = undefined;
    return defined;
  })();
  return playerReady;
}

export class CameraView {
  constructor(host) {
    this.host = host;
    this.entityId = null;
    this.stateObj = null;
    this.hass = null;
    this.active = false;
    this.live = false;
    this._visible = true;
    this._timer = 0;
    this._capturedAt = 0;
    this._attemptedAt = 0;
    this._loading = false;
    this._image = h("img", { class: "camera-image", alt: "" });
    this._message = h("div", { class: "camera-message" });
    this._updated = h("span", { class: "camera-updated" });
    this.el = h("div", { class: "camera" }, this._image, this._message, this._updated);
    this._liveLabel = h("span");
    this._liveIcon = icon("mdi:play");
    this.liveButton = h(
      "button",
      { class: "glass-button wide", type: "button", onclick: () => this.toggleLive() },
      this._liveIcon,
      this._liveLabel,
    );
    this.expandButton = h(
      "button",
      { class: "glass-button", type: "button", onclick: () => moreInfo(this.host, this.entityId) },
      icon("mdi:arrow-expand"),
    );
    /** Buttons for the host to place in its own toolbar. */
    this.controls = h("span", { class: "camera-controls" }, this.liveButton, this.expandButton);
    this._observer = new IntersectionObserver((entries) => {
      this._visible = entries.some((entry) => entry.isIntersecting);
      this._schedule();
    });
    this._onVisibility = () => this._schedule();
  }

  setEntity(entityId) {
    if (entityId === this.entityId) return;
    this.entityId = entityId;
    this.stateObj = null;
    this._capturedAt = 0;
    this._attemptedAt = 0;
    this.el.classList.remove("has-image");
    this._stopLive();
  }

  update(hass) {
    this.hass = hass;
    const stateObj = hass.states[this.entityId];
    const changed = stateObj !== this.stateObj;
    this.stateObj = stateObj;
    if (this._player) {
      this._player.hass = hass;
      if (changed) this._player.stateObj = stateObj;
    }
    if (changed) {
      if (!this.available && this.live) this._stopLive();
      this._render();
      // A fresh access token arrives with the state; use it for the first image.
      if (this.active && !this._timer) this._schedule();
    }
  }

  get available() {
    return Boolean(this.stateObj) && this.stateObj.state !== "unavailable";
  }

  get canStream() {
    return this.available && supportsFeature(this.stateObj, STREAM_FEATURE);
  }

  activate() {
    if (this.active) return;
    this.active = true;
    this._observer.observe(this.el);
    document.addEventListener("visibilitychange", this._onVisibility);
    this._render();
    this._schedule();
  }

  deactivate() {
    if (!this.active) return;
    this.active = false;
    this._observer.disconnect();
    document.removeEventListener("visibilitychange", this._onVisibility);
    clearTimeout(this._timer);
    this._stopLive();
  }

  destroy() {
    this.deactivate();
    this.el.remove();
  }

  tick() {
    this._renderTime();
  }

  /** Fetch a new snapshot now instead of waiting for the next scheduled one. */
  refreshNow() {
    this._attemptedAt = 0;
    this._schedule();
  }

  /** Load one snapshot outside the schedule; resolves to a decoded image, or null if none came. */
  async snapshot() {
    if (!this.available) return null;
    const image = this._newImage();
    if (!image) return null;
    try {
      await image.decode();
      return image;
    } catch {
      return null;
    }
  }

  _newImage() {
    const picture = this.stateObj?.attributes?.entity_picture;
    if (!picture) return null;
    const path = `${picture}${picture.includes("?") ? "&" : "?"}_=${Date.now()}`;
    const image = new Image();
    image.alt = "";
    image.src = typeof this.hass?.hassUrl === "function" ? this.hass.hassUrl(path) : path;
    return image;
  }

  async toggleLive() {
    if (this.live) {
      this._stopLive();
      this._schedule();
      return;
    }
    if (!this.canStream) return;
    if (!(await ensureCameraPlayer())) {
      moreInfo(this.host, this.entityId);
      return;
    }
    if (!this.active || this.live) return;
    const player = document.createElement("ha-camera-stream");
    player.className = "camera-player";
    // Older frontends read hass directly; newer ones use context from the page.
    player.hass = this.hass;
    player.stateObj = this.stateObj;
    player.muted = true;
    player.controls = true;
    player.allowExoPlayer = true;
    player.fitMode = "contain";
    player.setAttribute("muted", "");
    player.setAttribute("controls", "");
    player.setAttribute("allow-exoplayer", "");
    this._player = player;
    this.live = true;
    clearTimeout(this._timer);
    this.el.append(player);
    this._render();
  }

  _stopLive() {
    this._player?.remove();
    this._player = null;
    if (!this.live) return;
    this.live = false;
    this._render();
  }

  _schedule() {
    clearTimeout(this._timer);
    this._timer = 0;
    if (!this.active || this.live || document.hidden || !this._visible || !this.available) return;
    const due = Math.max(0, this._attemptedAt + REFRESH_MS - Date.now());
    this._timer = setTimeout(() => {
      this._timer = 0;
      this._refresh();
    }, due);
  }

  async _refresh() {
    if (this._loading) return;
    const image = this._newImage();
    if (!image) return;
    this._loading = true;
    this._attemptedAt = Date.now();
    image.className = "camera-image";
    try {
      await image.decode();
      if (this.active && !this.live) {
        this._image.replaceWith(image);
        this._image = image;
        this.el.classList.add("has-image");
        this._capturedAt = Date.now();
      }
    } catch {
      // Keep the previous image and try again on the normal schedule.
    } finally {
      this._loading = false;
      this._render();
      this._schedule();
    }
  }

  _render() {
    const hasImage = this.el.classList.contains("has-image");
    this.el.classList.toggle("live", this.live);
    this._message.textContent = !this.available
      ? t("camera.unavailable")
      : hasImage || this.live
        ? ""
        : t("camera.loading");
    this.liveButton.hidden = !this.canStream;
    this._liveLabel.textContent = this.live ? t("camera.stop_live") : t("camera.live");
    this._liveIcon.setAttribute("icon", this.live ? "mdi:image-outline" : "mdi:play");
    this.liveButton.setAttribute("aria-pressed", String(this.live));
    this.expandButton.title = t("camera.expand");
    this.expandButton.setAttribute("aria-label", t("camera.expand"));
    this.expandButton.disabled = !this.stateObj;
    this._renderTime();
  }

  _renderTime() {
    const show = this._capturedAt && !this.live && this.el.classList.contains("has-image");
    this._updated.hidden = !show;
    if (show) {
      this._updated.textContent = t("camera.updated", { time: relativeTime(this._capturedAt, currentLocale()) });
    }
  }
}
