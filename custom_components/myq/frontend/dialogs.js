/** Customize and settings dialogs built on the native <dialog> element. */

import {
  DOOR_COLORS,
  DoorScene,
  GLASS,
  HARDWARE_STYLES,
  STYLE_WINDOWS,
  STYLES,
  TRIM_COLORS,
  WIDTHS,
  doorThumbnail,
  normalizeAppearance,
} from "./door-scene.js";
import { openWarningMinutes } from "./door-card.js";
import { formatDuration, h, icon, navigate, toast } from "./dom.js";
import { currentLocale, t } from "./i18n.js";

const INTEGRATION_URL = "/config/integrations/integration/myq";
/** Choices for highlighting doors left open, in minutes; 0 turns the warning off. */
const OPEN_WARNINGS = [0, 15, 30, 60, 120];

class Sheet {
  constructor(panel, className) {
    this.panel = panel;
    this.dialog = h("dialog", { class: `sheet ${className}` });
    // Clicks on the backdrop target the dialog itself; content fills the dialog box.
    this.dialog.addEventListener("click", (event) => {
      if (event.target === this.dialog) this.close();
    });
    // Escape closes the dialog natively; buttons close it through close(). Either way, tear down once.
    this.dialog.addEventListener("close", () => this._finish());
  }

  _finish() {
    if (this._finished) return;
    this._finished = true;
    this.dialog.remove();
    this.onClose?.();
  }

  header(title) {
    return h(
      "header",
      { class: "sheet-header" },
      h("h2", { text: title, tabindex: "-1", autofocus: true }),
      h(
        "button",
        {
          class: "icon-button",
          type: "button",
          "aria-label": t("customize.close"),
          title: t("customize.close"),
          onclick: () => this.close(),
        },
        icon("mdi:close"),
      ),
    );
  }

  open() {
    this.panel.shadowRoot.append(this.dialog);
    this.dialog.showModal();
  }

  close() {
    if (this.dialog.open) this.dialog.close();
    this._finish();
  }
}

function field(label, ...content) {
  return h("div", { class: "field" }, h("div", { class: "field-label", text: label }), ...content);
}

function segmented(options, selected, onSelect, key) {
  return h(
    "div",
    { class: "segmented", role: "group" },
    options.map(([value, label]) =>
      h("button", {
        class: "segment",
        type: "button",
        text: label,
        "aria-pressed": String(value === selected),
        dataset: { focus: `${key}:${value}` },
        onclick: () => onSelect(value),
      }),
    ),
  );
}

function swatch(color, label, selected, onSelect, key, wood = false) {
  return h("button", {
    class: `swatch${wood ? " wood" : ""}`,
    type: "button",
    title: label,
    "aria-label": label,
    "aria-pressed": String(selected),
    style: { "--swatch": color },
    dataset: { focus: `${key}:${color}` },
    onclick: onSelect,
  });
}

export class CustomizeDialog extends Sheet {
  constructor(panel, door, doors, appearance) {
    super(panel, "customize");
    this.door = door;
    this.doors = doors;
    this.draft = normalizeAppearance(appearance);
    this.applyAll = false;
    this.previewOpen = false;
    this.previewLight = false;
    this.scene = new DoorScene();
    this.controls = h("section", { class: "controls" });
    this.previewToggle = h("div", { class: "preview-controls" });
    this.saveButton = h("button", {
      class: "filled-button",
      type: "button",
      text: t("customize.save"),
      onclick: () => this._save(),
    });
    this.dialog.append(
      this.header(t("customize.title", { name: door.name })),
      h(
        "div",
        { class: "sheet-body customize-body" },
        h("section", { class: "preview" }, h("div", { class: "preview-frame" }, this.scene.el), this.previewToggle),
        this.controls,
      ),
      h(
        "footer",
        { class: "sheet-footer" },
        h("button", {
          class: "text-button",
          type: "button",
          text: t("customize.reset"),
          onclick: () => this._reset(),
        }),
        h("span", { class: "spacer" }),
        h("button", {
          class: "text-button",
          type: "button",
          text: t("customize.cancel"),
          onclick: () => this.close(),
        }),
        this.saveButton,
      ),
    );
    this.onClose = () => this.scene.destroy();
    this._render();
  }

  _set(changes) {
    this.draft = normalizeAppearance({ ...this.draft, ...changes });
    this._render();
  }

  _renderPreview() {
    this.scene.setAppearance(this.draft);
    this.scene.setState(this.previewOpen ? "open" : "closed");
    this.scene.setLight(this.previewLight);
  }

  _render() {
    const focused = this.panel.shadowRoot.activeElement?.dataset?.focus;
    const a = this.draft;
    this._renderPreview();
    this.previewToggle.replaceChildren(
      segmented(
        [
          ["closed", t("customize.preview_closed")],
          ["open", t("customize.preview_open")],
        ],
        this.previewOpen ? "open" : "closed",
        (value) => {
          this.previewOpen = value === "open";
          this._render();
        },
        "preview",
      ),
      h(
        "button",
        {
          class: "segment-toggle",
          type: "button",
          "aria-pressed": String(this.previewLight),
          dataset: { focus: "preview:light" },
          onclick: () => {
            this.previewLight = !this.previewLight;
            this._render();
          },
        },
        icon(this.previewLight ? "mdi:lightbulb-on" : "mdi:lightbulb-outline"),
        h("span", { text: t("customize.preview_light") }),
      ),
    );

    const sections = [
      field(
        t("customize.size"),
        segmented(
          WIDTHS.map((width) => [width, t(`width.${width}`)]),
          a.width,
          (width) => this._set({ width }),
          "width",
        ),
      ),
      field(
        t("customize.style"),
        h(
          "div",
          { class: "tiles" },
          STYLES.map((style) => {
            const tile = h(
              "button",
              {
                class: "tile",
                type: "button",
                "aria-pressed": String(style === a.style),
                dataset: { focus: `style:${style}` },
                onclick: () => this._set({ style }),
              },
              h(
                "span",
                { class: "tile-art" },
                h("img", { src: doorThumbnail({ ...a, style, width: "single" }), alt: "", draggable: "false" }),
              ),
              h("span", { class: "tile-label", text: t(`style.${style}`) }),
            );
            return tile;
          }),
        ),
      ),
      field(t("customize.color"), this._colorPicker()),
    ];
    const windows = STYLE_WINDOWS[a.style];
    if (windows.length) {
      sections.push(
        field(
          t("customize.windows"),
          segmented(
            windows.map((value) => [value, t(`windows.${value}`)]),
            a.windows,
            (value) => this._set({ windows: value }),
            "windows",
          ),
        ),
      );
    }
    if (a.style === "glass" || a.windows !== "none") {
      sections.push(
        field(
          t("customize.glass"),
          segmented(
            GLASS.map((value) => [value, t(`glass.${value}`)]),
            a.glass,
            (glass) => this._set({ glass }),
            "glass",
          ),
        ),
      );
    }
    if (HARDWARE_STYLES.includes(a.style)) {
      sections.push(this._switch(t("customize.hardware"), a.hardware, (hardware) => this._set({ hardware }), "hardware"));
    }
    sections.push(
      field(
        t("customize.trim"),
        h(
          "div",
          { class: "swatches" },
          TRIM_COLORS.map((color) =>
            swatch(color.hex, t(`color.${color.id}`), color.id === a.trim, () => this._set({ trim: color.id }), "trim"),
          ),
        ),
      ),
    );
    if (this.doors.length > 1) {
      sections.push(
        this._switch(
          t("customize.apply_all"),
          this.applyAll,
          (value) => {
            this.applyAll = value;
            this._render();
          },
          "apply_all",
          t("customize.apply_all_help"),
        ),
      );
    }
    this.controls.replaceChildren(...sections);
    if (focused) this.panel.shadowRoot.querySelector(`[data-focus="${CSS.escape(focused)}"]`)?.focus();
  }

  _colorPicker() {
    const a = this.draft;
    const group = (label, colors) =>
      h(
        "div",
        { class: "swatch-group" },
        h("div", { class: "swatch-group-label", text: label }),
        h(
          "div",
          { class: "swatches" },
          colors.map((color) =>
            swatch(
              color.hex,
              t(`color.${color.id}`),
              color.id === a.color,
              () => this._set({ color: color.id }),
              "color",
              color.finish === "wood",
            ),
          ),
        ),
      );
    const custom = a.color.startsWith("#");
    const input = h("input", {
      type: "color",
      value: custom ? a.color : "#7a8590",
      "aria-label": t("customize.custom_color"),
      dataset: { focus: "color:custom" },
    });
    // While the native picker is open, update only the preview: re-rendering would replace the
    // input and close the picker. The full controls refresh once a color is chosen.
    input.addEventListener("input", () => {
      this.draft = normalizeAppearance({ ...this.draft, color: input.value.toLowerCase() });
      customSwatch.classList.add("filled");
      customSwatch.style.setProperty("--swatch", this.draft.color);
      this._renderPreview();
    });
    input.addEventListener("change", () => this._set({ color: input.value.toLowerCase() }));
    const customSwatch = h(
      "label",
      {
        class: `swatch custom${custom ? " filled" : ""}`,
        title: t("customize.custom_color"),
        "aria-pressed": String(custom),
        style: custom ? { "--swatch": a.color } : {},
      },
      input,
      icon("mdi:eyedropper-variant"),
    );
    const painted = DOOR_COLORS.filter((color) => color.finish !== "wood");
    const wood = DOOR_COLORS.filter((color) => color.finish === "wood");
    return h(
      "div",
      { class: "color-picker" },
      group(t("customize.painted"), painted),
      h(
        "div",
        { class: "swatch-group" },
        h("div", { class: "swatch-group-label", text: t("customize.wood") }),
        h(
          "div",
          { class: "swatches" },
          wood.map((color) =>
            swatch(color.hex, t(`color.${color.id}`), color.id === a.color, () => this._set({ color: color.id }), "color", true),
          ),
          customSwatch,
        ),
      ),
    );
  }

  _switch(label, checked, onChange, key, help) {
    const input = h("input", {
      class: "switch",
      type: "checkbox",
      role: "switch",
      dataset: { focus: key },
    });
    input.checked = checked;
    input.addEventListener("change", () => onChange(input.checked));
    return h(
      "label",
      { class: "switch-row" },
      h("span", { class: "switch-text" }, h("span", { text: label }), help ? h("small", { text: help }) : null),
      input,
    );
  }

  async _save() {
    const targets = this.applyAll ? this.doors : [this.door];
    const appearance = {};
    for (const door of targets) {
      const width =
        door.device_id === this.door.device_id
          ? this.draft.width
          : normalizeAppearance(this.panel.appearanceFor(door.device_id)).width;
      appearance[door.device_id] = { ...this.draft, width };
    }
    await this._submit(appearance);
  }

  async _reset() {
    await this._submit({ [this.door.device_id]: null });
  }

  async _submit(appearance) {
    this.saveButton.disabled = true;
    try {
      await this.panel.hass.callWS({ type: "myq/panel/save_appearance", appearance });
      toast(this.panel, t("customize.saved"));
      this.close();
    } catch (error) {
      toast(this.panel, t("customize.save_failed", { error: error?.message ?? String(error) }));
      this.saveButton.disabled = false;
    }
  }
}

export class SettingsDialog extends Sheet {
  constructor(panel) {
    super(panel, "settings");
    this.body = h("div", { class: "sheet-body settings-body" });
    this.dialog.append(
      this.header(t("panel.settings")),
      this.body,
      h(
        "footer",
        { class: "sheet-footer" },
        h("span", { class: "spacer" }),
        h("button", { class: "filled-button", type: "button", text: t("settings.done"), onclick: () => this.close() }),
      ),
    );
    this.refresh();
  }

  refresh() {
    const focused = this.panel.shadowRoot.activeElement?.dataset?.focus;
    const settings = this.panel.settings;
    const doors = this.panel.orderedDoors();
    const confirm = h("input", { class: "switch", type: "checkbox", role: "switch", dataset: { focus: "confirm" } });
    confirm.checked = Boolean(settings.confirm);
    confirm.addEventListener("change", () => this._save({ confirm: confirm.checked }));
    const warning = openWarningMinutes(settings);
    const warnings = [...new Set([...OPEN_WARNINGS, warning])].sort((a, b) => a - b);
    const sections = [
      h(
        "label",
        { class: "switch-row" },
        h("span", { class: "switch-text" }, h("span", { text: t("settings.confirm") }), h("small", { text: t("settings.confirm_help") })),
        confirm,
      ),
      field(
        t("settings.open_warning"),
        segmented(
          warnings.map((minutes) => [
            minutes,
            minutes ? formatDuration(minutes * 60000, currentLocale()) : t("settings.off"),
          ]),
          warning,
          (minutes) => this._save({ open_warning: minutes }),
          "open_warning",
        ),
        h("p", { class: "field-help", text: t("settings.open_warning_help") }),
      ),
    ];
    if (doors.length > 1) {
      const ids = doors.map((door) => door.device_id);
      const move = (index, offset) => {
        const order = [...ids];
        const [item] = order.splice(index, 1);
        order.splice(index + offset, 0, item);
        this._save({ order });
      };
      sections.push(
        field(
          t("settings.order"),
          h(
            "ol",
            { class: "order-list" },
            doors.map((door, index) =>
              h(
                "li",
                { class: "order-row" },
                h("span", { class: "order-index", text: String(index + 1) }),
                h("span", { class: "order-name", text: door.name }),
                h(
                  "button",
                  {
                    class: "icon-button small",
                    type: "button",
                    disabled: index === 0,
                    title: t("settings.move_up", { name: door.name }),
                    "aria-label": t("settings.move_up", { name: door.name }),
                    dataset: { focus: `up:${door.device_id}` },
                    onclick: () => move(index, -1),
                  },
                  icon("mdi:arrow-up"),
                ),
                h(
                  "button",
                  {
                    class: "icon-button small",
                    type: "button",
                    disabled: index === doors.length - 1,
                    title: t("settings.move_down", { name: door.name }),
                    "aria-label": t("settings.move_down", { name: door.name }),
                    dataset: { focus: `down:${door.device_id}` },
                    onclick: () => move(index, 1),
                  },
                  icon("mdi:arrow-down"),
                ),
              ),
            ),
          ),
        ),
      );
    }
    sections.push(
      h(
        "div",
        { class: "note" },
        icon("mdi:information-outline"),
        h(
          "div",
          {},
          h("p", { text: t("settings.sidebar_help") }),
          h("button", {
            class: "text-button inline",
            type: "button",
            text: t("panel.open_settings"),
            onclick: () => {
              this.close();
              navigate(INTEGRATION_URL);
            },
          }),
        ),
      ),
    );
    this.body.replaceChildren(...sections);
    if (focused) this.panel.shadowRoot.querySelector(`[data-focus="${CSS.escape(focused)}"]`)?.focus();
  }

  async _save(settings) {
    try {
      await this.panel.hass.callWS({ type: "myq/panel/save_settings", settings });
    } catch (error) {
      toast(this.panel, t("customize.save_failed", { error: error?.message ?? String(error) }));
      this.refresh();
    }
  }
}
