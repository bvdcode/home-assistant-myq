/** Runs the panel's browser modules under Node: a jsdom page, a stand-in Home Assistant, and a test clock. */

import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import { JSDOM } from "jsdom";

const FRONTEND = new URL("../../custom_components/myq/frontend/", import.meta.url);

/** Source URLs of the images the page decoded, in order. */
export const decoded = [];

const observers = new Set();

/** Create the page and expose its globals the way a browser would. Call before importing a module. */
export function installPage() {
  const { window } = new JSDOM("<!doctype html><html lang='en'><body></body></html>", {
    pretendToBeVisual: true,
    url: "http://localhost:8123/",
  });
  const names = [
    "window", "document", "customElements", "HTMLElement", "Node", "Element", "Text", "CustomEvent", "Event",
    "MouseEvent", "PointerEvent",
    "HTMLImageElement", "DocumentFragment", "ShadowRoot", "MutationObserver", "getComputedStyle",
    "requestAnimationFrame", "cancelAnimationFrame", "localStorage", "CSS",
  ];
  for (const name of names) {
    if (window[name] !== undefined) {
      Object.defineProperty(globalThis, name, { value: window[name], configurable: true, writable: true });
    }
  }
  globalThis.IntersectionObserver = class {
    constructor(callback) {
      this.callback = callback;
      this.targets = new Set();
      observers.add(this);
    }
    observe(target) {
      this.targets.add(target);
    }
    unobserve(target) {
      this.targets.delete(target);
    }
    disconnect() {
      this.targets.clear();
    }
    takeRecords() {
      return [];
    }
  };
  window.HTMLImageElement.prototype.decode = function decode() {
    decoded.push(this.getAttribute("src") ?? "");
    return Promise.resolve();
  };
  globalThis.Image = function Image() {
    return window.document.createElement("img");
  };
  // Modules load their translations relative to their own file URL.
  globalThis.fetch = async (input) => {
    try {
      return new Response(await readFile(fileURLToPath(new URL(String(input))), "utf8"));
    } catch {
      return new Response("", { status: 404 });
    }
  };
  return window;
}

/** Import a panel module, optionally as a fresh copy with its own module state. */
export function importFrontend(file, fresh = "") {
  return import(new URL(fresh ? `${file}?${fresh}` : file, FRONTEND).href);
}

/** Tell the observers watching an element that it moved on or off screen. */
export function setOnScreen(element, isIntersecting) {
  for (const observer of observers) {
    if (observer.targets.has(element)) observer.callback([{ target: element, isIntersecting }]);
  }
}

/** Let pending promises, file reads, and DOM work settle. */
export async function flush(turns = 5) {
  for (let i = 0; i < turns; i += 1) await new Promise((resolve) => setImmediate(resolve));
}

export async function until(condition, description, turns = 200) {
  for (let i = 0; i < turns; i += 1) {
    if (condition()) return;
    await flush(1);
  }
  throw new Error(`Timed out waiting for ${description}`);
}

/**
 * Replace setTimeout, setInterval, and Date.now with a clock that moves only when told to. Install it
 * before importing the module under test.
 */
export function installClock(start = Date.UTC(2026, 10, 15, 12)) {
  let now = start;
  let nextId = 1;
  const timers = new Map();
  const schedule = (callback, delay, repeat, args) => {
    const id = nextId++;
    timers.set(id, { at: now + Math.max(0, Number(delay) || 0), every: repeat ? Math.max(1, Number(delay) || 0) : 0, callback, args });
    return id;
  };
  globalThis.setTimeout = (callback, delay, ...args) => schedule(callback, delay, false, args);
  globalThis.setInterval = (callback, delay, ...args) => schedule(callback, delay, true, args);
  globalThis.clearTimeout = (id) => timers.delete(id);
  globalThis.clearInterval = (id) => timers.delete(id);
  Date.now = () => now;
  return {
    get now() {
      return now;
    },
    /** Move time forward, running each timer that falls due and letting its promises settle. */
    async advance(ms) {
      const end = now + ms;
      for (;;) {
        let due = null;
        for (const [id, timer] of timers) if (timer.at <= end && (!due || timer.at < due[1].at)) due = [id, timer];
        if (!due) break;
        const [id, timer] = due;
        now = timer.at;
        if (timer.every) timer.at += timer.every;
        else timers.delete(id);
        timer.callback(...timer.args);
        await flush(3);
      }
      now = end;
      await flush(3);
    },
  };
}

/** A cover entity state. */
export function cover(entityId, state, lastChanged = new Date(Date.now()).toISOString()) {
  return { entity_id: entityId, state, attributes: { friendly_name: entityId }, last_changed: lastChanged, last_updated: lastChanged };
}

/**
 * A websocket connection that behaves like home-assistant-js-websocket's. `subscribe` answers each
 * subscription. `reconnect()` does what the library does after the socket comes back: it subscribes
 * again to everything not made with `resubscribe: false`, silently dropping any that fail, and then
 * fires "ready".
 */
export function fakeConnection(subscribe) {
  const ready = new Set();
  let kept = [];
  return {
    async subscribeMessage(callback, message, options) {
      const unsubscribe = await subscribe(callback, message, options);
      const entry = { callback, message, options };
      if (options?.resubscribe !== false) kept.push(entry);
      return () => {
        kept = kept.filter((item) => item !== entry);
        return unsubscribe?.();
      };
    },
    addEventListener(type, callback) {
      if (type === "ready") ready.add(callback);
    },
    removeEventListener(type, callback) {
      if (type === "ready") ready.delete(callback);
    },
    reconnect() {
      const again = kept;
      kept = [];
      for (const { callback, message, options } of again) this.subscribeMessage(callback, message, options).catch(() => {});
      for (const callback of ready) callback();
    },
  };
}

/**
 * A stand-in for the `hass` object Home Assistant gives panels and cards. `subscribe` answers the
 * panel's subscription, or `connection` replaces the whole connection; service calls are recorded in
 * `calls`.
 */
export function makeHass({ states, subscribe, connection, callWS, components = [], calls = [] }) {
  return {
    states,
    entities: {},
    user: { id: "user-1", name: "Admin", is_admin: true },
    locale: { language: "en", time_format: "language" },
    language: "en",
    themes: { darkMode: false },
    config: { components },
    connection: connection ?? fakeConnection(subscribe),
    async callService(domain, service, data) {
      calls.push(`${domain}.${service} ${data.entity_id}`);
    },
    callWS: callWS ?? (async () => []),
    localize: () => "",
  };
}

/** A subscription that answers every subscriber at once with `payload()`. */
export function answering(payload) {
  return async (callback) => {
    callback(payload());
    return () => {};
  };
}
