/**
 * Garage door scenes rendered as layered SVG.
 *
 * Geometry is in inches: a single door is 9 ft × 7 ft and a double door 16 ft × 7 ft.
 * The trim, garage interior, work light, door, and opening shadows are separate SVG images.
 * The browser draws each image's textures once and reuses the result, so moving the door or
 * fading the light only recomposites finished images, even on slow wall tablets.
 */

const DOOR_HEIGHT = 84;
const DOOR_WIDTH = { single: 108, double: 192 };
/** Width of the casing around the opening. */
const TRIM = 6;
/** Width of the weatherstrip stop molding that covers the edges of the opening. */
const STOP = 1.2;
/** Plain space beside and above the trim. */
const MARGIN = 8;
const TOP_MARGIN = 5;
const SECTIONS = 4;
const SECTION = DOOR_HEIGHT / SECTIONS;
const TRAVEL_MS = 12000;
const FINISH_MS = 2600;
const HOLD_OPENING = 0.88;
const HOLD_CLOSING = 0.12;

/** Fraction of the door that stays visible below the header when fully open. */
const OPEN_REVEAL = 0.055;

export const STYLES = [
  "traditional",
  "long_panel",
  "shaker",
  "carriage",
  "farmhouse",
  "modern",
  "plank",
  "glass",
];
const PANEL_WINDOWS = ["none", "plain", "grid", "arched"];
const MODERN_WINDOWS = ["none", "plain", "side"];
export const STYLE_WINDOWS = {
  traditional: PANEL_WINDOWS,
  long_panel: PANEL_WINDOWS,
  shaker: PANEL_WINDOWS,
  carriage: PANEL_WINDOWS,
  farmhouse: PANEL_WINDOWS,
  modern: MODERN_WINDOWS,
  plank: MODERN_WINDOWS,
  glass: [],
};
export const HARDWARE_STYLES = ["carriage", "farmhouse"];
export const GLASS = ["tinted", "clear", "frosted"];
export const WIDTHS = ["single", "double"];

export const DOOR_COLORS = [
  { id: "white", hex: "#f1f0eb" },
  { id: "almond", hex: "#e2d5bb" },
  { id: "sandstone", hex: "#cbbd9f" },
  { id: "clay", hex: "#9f8f7c" },
  { id: "gray", hex: "#8d9297" },
  { id: "charcoal", hex: "#45484c" },
  { id: "black", hex: "#212224" },
  { id: "brown", hex: "#5b4535" },
  { id: "bronze", hex: "#463a30" },
  { id: "green", hex: "#35453a" },
  { id: "navy", hex: "#2e3a4a" },
  { id: "red", hex: "#6e2e27" },
  { id: "aluminum", hex: "#b9bdc1", finish: "metal" },
  { id: "light_oak", hex: "#c79f6e", finish: "wood" },
  { id: "cedar", hex: "#a96a40", finish: "wood" },
  { id: "walnut", hex: "#6c4a32", finish: "wood" },
  { id: "mahogany", hex: "#6a3426", finish: "wood" },
  { id: "espresso", hex: "#3a2a20", finish: "wood" },
  { id: "driftwood", hex: "#908779", finish: "wood" },
];

/** Trim is painted, so it offers the painted door colors under the same names. */
export const TRIM_COLORS = DOOR_COLORS.filter((color) => !color.finish);

const DEFAULT_APPEARANCE = Object.freeze({
  width: "single",
  style: "traditional",
  color: "white",
  windows: "none",
  glass: "tinted",
  hardware: true,
  trim: "white",
});

const HEX = /^#[0-9a-f]{6}$/;

/** Return a complete appearance, replacing unknown or inapplicable values with defaults. */
export function normalizeAppearance(raw) {
  const a = { ...DEFAULT_APPEARANCE };
  if (raw && typeof raw === "object") {
    if (WIDTHS.includes(raw.width)) a.width = raw.width;
    if (STYLES.includes(raw.style)) a.style = raw.style;
    if (typeof raw.color === "string" && (HEX.test(raw.color) || findColor(raw.color))) {
      a.color = raw.color;
    }
    if (typeof raw.windows === "string") a.windows = raw.windows;
    if (GLASS.includes(raw.glass)) a.glass = raw.glass;
    if (typeof raw.hardware === "boolean") a.hardware = raw.hardware;
    if (typeof raw.trim === "string" && (HEX.test(raw.trim) || findTrim(raw.trim))) a.trim = raw.trim;
  }
  if (!STYLE_WINDOWS[a.style].includes(a.windows)) a.windows = "none";
  return a;
}

function doorColor(id) {
  if (HEX.test(id)) return { id, hex: id, finish: "paint" };
  return findColor(id) ?? DOOR_COLORS[0];
}

function findColor(id) {
  const color = DOOR_COLORS.find((candidate) => candidate.id === id);
  return color ? { finish: "paint", ...color } : undefined;
}

function findTrim(id) {
  return TRIM_COLORS.find((color) => color.id === id);
}

function trimColor(id) {
  return HEX.test(id) ? id : (findTrim(id) ?? TRIM_COLORS[0]).hex;
}

/** Size of a door with its trim and the space around it, in inches. */
function sceneSize(width) {
  const doorWidth = DOOR_WIDTH[width] ?? DOOR_WIDTH.single;
  return { width: doorWidth + 2 * (MARGIN + TRIM), height: TOP_MARGIN + TRIM + DOOR_HEIGHT, doorWidth };
}

/* ------------------------------------------------------------------ color helpers */

function rgb(hex) {
  const value = Number.parseInt(hex.slice(1), 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

function toHex([r, g, b]) {
  return `#${[r, g, b]
    .map((channel) => Math.round(Math.min(255, Math.max(0, channel))).toString(16).padStart(2, "0"))
    .join("")}`;
}

/** Lighten (amount > 0) or darken (amount < 0) a color. */
function shade(hex, amount) {
  const target = amount < 0 ? 0 : 255;
  const t = Math.abs(amount);
  return toHex(rgb(hex).map((channel) => channel + (target - channel) * t));
}

function luminance(hex) {
  const [r, g, b] = rgb(hex).map((channel) => {
    const c = channel / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

/** Deterministic pseudo-random numbers so textures look identical on every render. */
function random(seed) {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/* ------------------------------------------------------------------ svg helpers */

const n = (value) => Math.round(value * 100) / 100;
const rect = (x, y, w, h, fill, extra = "") =>
  `<rect x="${n(x)}" y="${n(y)}" width="${n(w)}" height="${n(h)}" fill="${fill}"${extra}/>`;
const poly = (points, fill) =>
  `<polygon points="${points.map(([x, y]) => `${n(x)},${n(y)}`).join(" ")}" fill="${fill}"/>`;
const stops = (list) =>
  list
    .map(([offset, color, opacity = 1]) => `<stop offset="${offset}" stop-color="${color}" stop-opacity="${n(opacity)}"/>`)
    .join("");

/* ------------------------------------------------------------------ door */

/** Highlight and shadow strengths that make light and dark finishes look equally lit. */
function shading(hex) {
  const lum = luminance(hex);
  return { hi: 0.55 + 0.85 * (1 - lum), lo: 0.5 + 0.75 * Math.sqrt(lum) };
}

function doorContext(a, id, W, lit) {
  const color = doorColor(a.color);
  return {
    a,
    id,
    W,
    lit,
    H: DOOR_HEIGHT,
    color,
    ...shading(color.hex),
    defs: [],
    body: [],
    top: [],
    shadows: [],
    holes: [],
  };
}

const light = (ctx, alpha) => `rgba(255,255,255,${n(Math.min(0.9, alpha * ctx.hi))})`;
const dark = (ctx, alpha) => `rgba(0,0,0,${n(Math.min(0.9, alpha * ctx.lo))})`;

/** Door markup; the lit version adds the glow of the work light behind frosted glass. */
function doorMarkup(appearance, id, lit = false) {
  const a = normalizeAppearance(appearance);
  const ctx = doorContext(a, id, DOOR_WIDTH[a.width], lit);
  const { W, H, color } = ctx;
  ctx.defs.push(
    `<linearGradient id="${id}-field" x1="0" y1="0" x2="0" y2="1">${stops([
      [0, "#fff", 0.07 * ctx.hi],
      [0.5, "#fff", 0],
      [1, "#000", 0.05 * ctx.lo],
    ])}</linearGradient>`,
    `<linearGradient id="${id}-reflect" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="${n(W * 0.55)}" y2="${H}">${stops([
      [0, "#fff", 0.2],
      [0.3, "#fff", 0.03],
      [0.46, "#fff", 0.13],
      [0.6, "#fff", 0.02],
      [1, "#fff", 0],
    ])}</linearGradient>`,
    `<linearGradient id="${id}-sheen" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="${W}" y2="${H}">${stops([
      [0, "#fff", 0.07],
      [0.5, "#fff", 0],
      [1, "#000", 0.07],
    ])}</linearGradient>`,
    `<filter id="${id}-soft" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="0.55"/></filter>`,
    `<radialGradient id="${id}-frost" gradientUnits="userSpaceOnUse" cx="${n(W / 2)}" cy="6" r="${n(Math.max(W * 0.75, H))}">${stops([
      [0, "#fff3dd"],
      [0.45, "#ffe2b5"],
      [1, "#f3cf9a"],
    ])}</radialGradient>`,
  );
  ctx.body.push(rect(0, 0, W, H, color.hex));

  switch (a.style) {
    case "traditional":
    case "long_panel":
    case "shaker":
      panelDoor(ctx);
      break;
    case "carriage":
    case "farmhouse":
      carriageDoor(ctx, a.style === "farmhouse");
      break;
    case "plank":
      plankDoor(ctx);
      break;
    case "glass":
      glassDoor(ctx);
      break;
    default:
      modernDoor(ctx);
  }

  const vertical = a.style === "carriage" || a.style === "farmhouse";
  const texture = textureFilter(ctx, vertical);
  const shadowLayer = ctx.shadows.length
    ? `<g filter="url(#${id}-soft)">${ctx.shadows.join("")}</g>`
    : "";
  // Cut the door body away behind glass so the garage interior shows through.
  const holes = ctx.holes
    .map(({ x, y, w, h, clip }) =>
      clip ? `<g clip-path="url(#${clip})">${rect(x, y, w, h, "#000")}</g>` : rect(x, y, w, h, "#000"),
    )
    .join("");
  if (holes) {
    ctx.defs.push(
      `<mask id="${id}-holes" maskUnits="userSpaceOnUse" x="0" y="0" width="${W}" height="${H}">${rect(0, 0, W, H, "#fff")}${holes}</mask>`,
    );
  }
  const finish = [
    // Section joints between the four sections.
    ...[1, 2, 3].flatMap((s) => [
      rect(0, s * SECTION - 0.5, W, 0.55, dark(ctx, 0.4)),
      rect(0, s * SECTION + 0.05, W, 0.4, light(ctx, 0.2)),
    ]),
    rect(0, 0, 0.7, H, dark(ctx, 0.14)),
    rect(W - 0.7, 0, 0.7, H, dark(ctx, 0.2)),
    rect(0, 0, W, H, `url(#${id}-sheen)`),
    // Bottom weather seal.
    rect(0, H - 1, W, 1, "rgba(20,20,20,0.82)"),
    rect(0, H - 1.05, W, 0.2, light(ctx, 0.12)),
  ];
  const mask = holes ? ` mask="url(#${id}-holes)"` : "";
  return `<defs>${ctx.defs.join("")}</defs><g${mask}>${ctx.body[0]}${shadowLayer}${ctx.body
    .slice(1)
    .join("")}${texture}</g>${ctx.top.join("")}${finish.join("")}`;
}

/** Alpha row of a color matrix that maps noise to coverage scaled by strength. */
const alphaRow = (slope, offset, strength) => `${n(slope * strength)} 0 0 0 ${n(offset * strength)}`;

function textureFilter(ctx, vertical) {
  const { id, W, H, color } = ctx;
  // The same dark grain is far more visible on light finishes, so scale it by luminance.
  const strength = 1 - 0.55 * Math.min(1, luminance(color.hex) * 2.4);
  const [r, g, b] = rgb(shade(color.hex, -0.6)).map((channel) => n(channel / 255));
  let frequency;
  let matrix;
  const opacity = 1;
  if (color.finish === "wood") {
    frequency = vertical ? "1.3 0.02" : "0.02 1.3";
    matrix = `0 0 0 0 ${r}  0 0 0 0 ${g}  0 0 0 0 ${b}  ${alphaRow(0.75, -0.3, strength)}`;
  } else if (color.finish === "metal") {
    frequency = "0.004 1.6";
    matrix = `0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  ${alphaRow(0.3, -0.1, 1)}`;
  } else {
    frequency = vertical ? "1.6 0.03" : "0.03 1.6";
    matrix = `0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  ${alphaRow(0.13, -0.06, strength)}`;
  }
  ctx.defs.push(
    `<filter id="${id}-tex" x="0" y="0" width="1" height="1" color-interpolation-filters="sRGB">` +
      `<feTurbulence type="fractalNoise" baseFrequency="${frequency}" numOctaves="3" seed="11" result="noise"/>` +
      `<feColorMatrix in="noise" type="matrix" values="${matrix}"/></filter>`,
  );
  const grain = `<rect width="${W}" height="${H}" filter="url(#${id}-tex)" opacity="${opacity}"/>`;
  if (color.finish !== "wood") return grain;
  // Broad figure gives wood the irregular darker bands of real boards.
  ctx.defs.push(
    `<filter id="${id}-figure" x="0" y="0" width="1" height="1" color-interpolation-filters="sRGB">` +
      `<feTurbulence type="fractalNoise" baseFrequency="${vertical ? "0.32 0.008" : "0.008 0.32"}" numOctaves="3" seed="5" result="noise"/>` +
      `<feColorMatrix in="noise" type="matrix" values="0 0 0 0 ${r}  0 0 0 0 ${g}  0 0 0 0 ${b}  ${alphaRow(0.55, -0.23, strength)}"/></filter>`,
  );
  return `<rect width="${W}" height="${H}" filter="url(#${id}-figure)"/>${grain}`;
}

function bevelPanel(ctx, x, y, w, h, recessed) {
  const b = recessed ? Math.min(1.1, h * 0.09) : Math.min(2.5, w * 0.12, h * 0.17);
  const top = [[x, y], [x + w, y], [x + w - b, y + b], [x + b, y + b]];
  const bottom = [[x, y + h], [x + w, y + h], [x + w - b, y + h - b], [x + b, y + h - b]];
  const left = [[x, y], [x + b, y + b], [x + b, y + h - b], [x, y + h]];
  const right = [[x + w, y], [x + w - b, y + b], [x + w - b, y + h - b], [x + w, y + h]];
  if (recessed) {
    ctx.body.push(
      rect(x + b, y + b, w - 2 * b, h - 2 * b, dark(ctx, 0.035)),
      rect(x + b, y + b, w - 2 * b, 1.6, `url(#${ctx.id}-inner)`),
      poly(top, dark(ctx, 0.3)),
      poly(left, dark(ctx, 0.18)),
      poly(bottom, light(ctx, 0.34)),
      poly(right, light(ctx, 0.12)),
    );
    return;
  }
  ctx.body.push(
    rect(x - 0.3, y - 0.3, w + 0.6, h + 0.6, dark(ctx, 0.1)),
    poly(top, light(ctx, 0.36)),
    poly(left, light(ctx, 0.17)),
    poly(bottom, dark(ctx, 0.27)),
    poly(right, dark(ctx, 0.15)),
    rect(x + b, y + b, w - 2 * b, h - 2 * b, `url(#${ctx.id}-field)`),
    rect(x + b, y + b, w - 2 * b, 0.25, light(ctx, 0.22)),
    rect(x + b, y + h - b - 0.25, w - 2 * b, 0.25, dark(ctx, 0.12)),
  );
}

function panelDoor(ctx) {
  const { a, W, id } = ctx;
  const count = a.style === "traditional" ? (W > 150 ? 8 : 4) : W > 150 ? 4 : 2;
  const edge = W > 150 ? 4.5 : 4;
  const gap = 3.2;
  const rail = 3.3;
  const pw = (W - 2 * edge - (count - 1) * gap) / count;
  const recessed = a.style === "shaker";
  ctx.defs.push(
    `<linearGradient id="${id}-inner" x1="0" y1="0" x2="0" y2="1">${stops([
      [0, "#000", 0.16 * ctx.lo],
      [1, "#000", 0],
    ])}</linearGradient>`,
  );
  const windowCells = [];
  for (let s = 0; s < SECTIONS; s++) {
    for (let i = 0; i < count; i++) {
      const cell = { x: edge + i * (pw + gap), y: s * SECTION + rail, w: pw, h: SECTION - 2 * rail };
      if (s === 0 && a.windows !== "none") windowCells.push(cell);
      else bevelPanel(ctx, cell.x, cell.y, cell.w, cell.h, recessed);
    }
  }
  if (windowCells.length) {
    const first = windowCells[0];
    const band = { x: edge, y: first.y, w: W - 2 * edge, h: first.h };
    const clip = a.windows === "arched" ? archClip(ctx, [band], "arch") : null;
    for (const cell of windowCells) {
      const grid = a.windows === "grid" ? (cell.w > 30 ? [4, 2] : [2, 2]) : null;
      windowUnit(ctx, cell.x, cell.y, cell.w, cell.h, { grid, clip });
    }
    if (clip) archTrim(ctx, [band]);
  }
}

/** Clip region below an arch spanning each band; returns the clip id. */
function archClip(ctx, bands, name) {
  const id = `${ctx.id}-${name}`;
  const paths = bands
    .map(({ x, y, w, h }) => {
      const edgeY = y + h * 0.58;
      const controlY = 2 * y - edgeY;
      return `<path d="M${n(x)} ${n(y + h + 1)}L${n(x)} ${n(edgeY)}Q${n(x + w / 2)} ${n(controlY)} ${n(x + w)} ${n(edgeY)}L${n(x + w)} ${n(y + h + 1)}Z"/>`;
    })
    .join("");
  ctx.defs.push(`<clipPath id="${id}">${paths}</clipPath>`);
  return id;
}

function archTrim(ctx, bands) {
  for (const { x, y, w, h } of bands) {
    const edgeY = y + h * 0.58;
    const controlY = 2 * y - edgeY;
    const d = `M${n(x)} ${n(edgeY)}Q${n(x + w / 2)} ${n(controlY)} ${n(x + w)} ${n(edgeY)}`;
    ctx.top.push(
      `<path d="${d}" fill="none" stroke="${dark(ctx, 0.3)}" stroke-width="0.5" transform="translate(0 -0.35)"/>`,
      `<path d="${d}" fill="none" stroke="${light(ctx, 0.25)}" stroke-width="0.35" transform="translate(0 0.2)"/>`,
    );
  }
}

function glassFill(type) {
  switch (type) {
    case "clear":
      return "rgba(150,172,186,0.2)";
    case "frosted":
      return "rgba(222,228,231,0.88)";
    default:
      return "rgba(22,30,38,0.72)";
  }
}

function glass(ctx, x, y, w, h, clip = null) {
  const type = ctx.a.glass;
  ctx.holes.push({ x, y, w, h, clip });
  const glow = type === "frosted" && ctx.lit ? rect(x, y, w, h, `url(#${ctx.id}-frost)`, ' opacity="0.92"') : "";
  return (
    rect(x, y, w, h, glassFill(type)) +
    glow +
    rect(x, y, w, h, `url(#${ctx.id}-reflect)`) +
    rect(x, y, w, 0.35, "rgba(0,0,0,0.35)") +
    rect(x, y, 0.3, h, "rgba(0,0,0,0.22)")
  );
}

/** A window insert: shadowed recess, frame in the door color, glass, and optional muntins. */
function windowUnit(ctx, x, y, w, h, { grid = null, clip = null, frame = null } = {}) {
  const inset = frame ? 0.9 : 1.35;
  const gx = x + inset;
  const gy = y + inset;
  const gw = w - 2 * inset;
  const gh = h - 2 * inset;
  const under = [];
  const over = [];
  if (frame) {
    under.push(rect(x, y, w, h, frame), rect(x, y, w, 0.3, "rgba(255,255,255,0.12)"));
  } else {
    under.push(
      rect(x - 0.35, y - 0.35, w + 0.7, h + 0.7, dark(ctx, 0.26)),
      rect(x, y, w, h, ctx.color.hex),
      rect(x, y, w, 0.35, light(ctx, 0.3)),
      rect(x, y + h - 0.35, w, 0.35, dark(ctx, 0.2)),
    );
  }
  over.push(glass(ctx, gx, gy, gw, gh, clip));
  if (grid) {
    const [cols, rows] = grid;
    const bar = 0.85;
    const muntin = frame ?? shade(ctx.color.hex, 0.02);
    for (let c = 1; c < cols; c++) {
      const mx = gx + (gw * c) / cols - bar / 2;
      over.push(rect(mx, gy, bar, gh, muntin), rect(mx + bar, gy, 0.2, gh, "rgba(0,0,0,0.25)"));
    }
    for (let r = 1; r < rows; r++) {
      const my = gy + (gh * r) / rows - bar / 2;
      over.push(rect(gx, my, gw, bar, muntin), rect(gx, my + bar, gw, 0.2, "rgba(0,0,0,0.25)"));
    }
  }
  const wrap = (items) => (clip ? `<g clip-path="url(#${clip})">${items.join("")}</g>` : items.join(""));
  ctx.body.push(wrap(under));
  ctx.top.push(wrap(over));
}

function overlayBoard(ctx, x, y, w, h) {
  ctx.shadows.push(rect(x + 0.5, y + 0.75, w + 0.3, h + 0.3, "rgba(0,0,0,0.5)"));
  ctx.body.push(
    rect(x, y, w, h, ctx.color.hex),
    rect(x, y, w, 0.3, light(ctx, 0.3)),
    rect(x, y, 0.3, h, light(ctx, 0.18)),
    rect(x, y + h - 0.3, w, 0.3, dark(ctx, 0.22)),
    rect(x + w - 0.3, y, 0.3, h, dark(ctx, 0.14)),
  );
}

function carriageDoor(ctx, crossbuck) {
  const { a, W, H, id } = ctx;
  // Vertical tongue-and-groove boards behind the overlay frame.
  const board = 6;
  for (let x = board; x < W; x += board) {
    ctx.body.push(rect(x - 0.35, 0, 0.35, H, dark(ctx, 0.32)), rect(x, 0, 0.3, H, light(ctx, 0.16)));
  }
  const leafWidth = W / 2;
  const stile = W > 150 ? 6 : 5;
  const rail = 4.6;
  const midTop = SECTION - 2.4;
  const midHeight = 4.8;
  const bottomTop = H - 7;
  const lowerTop = midTop + midHeight;
  const windowBands = [];
  for (let leaf = 0; leaf < 2; leaf++) {
    const x0 = leaf * leafWidth;
    const x1 = x0 + leafWidth;
    const innerX = x0 + stile;
    const innerW = leafWidth - 2 * stile;
    overlayBoard(ctx, x0 + 0.4, 0, stile - 0.4, H - 1);
    overlayBoard(ctx, x1 - stile, 0, stile - 0.4, H - 1);
    overlayBoard(ctx, innerX, 0, innerW, rail);
    overlayBoard(ctx, innerX, midTop, innerW, midHeight);
    overlayBoard(ctx, innerX, bottomTop, innerW, 6);
    if (crossbuck) {
      crossBrace(ctx, innerX, lowerTop, innerW, bottomTop - lowerTop);
    } else {
      overlayBoard(ctx, innerX, lowerTop + (bottomTop - lowerTop) / 2 - 2.2, innerW, 4.4);
    }
    windowBands.push({ x: innerX, y: rail, w: innerW, h: midTop - rail });
  }
  if (a.windows !== "none") {
    const clip = a.windows === "arched" ? archClip(ctx, windowBands, "arch") : null;
    const lites = W > 150 ? 4 : 2;
    const mullion = 2.6;
    for (const band of windowBands) {
      const pad = 1.1;
      const lw = (band.w - 2 * pad - (lites - 1) * mullion) / lites;
      for (let i = 0; i < lites; i++) {
        const grid = a.windows === "grid" ? [lw > 20 ? 3 : 2, 2] : null;
        windowUnit(ctx, band.x + pad + i * (lw + mullion), band.y + pad, lw, band.h - 2 * pad, { grid, clip });
      }
    }
    if (clip) archTrim(ctx, windowBands.map((band) => ({ ...band, x: band.x + 1, w: band.w - 2 })));
  } else {
    for (const band of windowBands) {
      ctx.body.push(rect(band.x, band.y, band.w, band.h, dark(ctx, 0.03)));
    }
  }
  // Meeting line between the two leaves.
  ctx.top.push(rect(W / 2 - 0.3, 0, 0.6, H - 1, dark(ctx, 0.45)));
  if (a.hardware) carriageHardware(ctx);
  ctx.defs.push(`<linearGradient id="${id}-iron" x1="0" y1="0" x2="0" y2="1">${stops([
    [0, "#3a3b3d"],
    [0.45, "#1d1e20"],
    [1, "#111213"],
  ])}</linearGradient>`);
}

function crossBrace(ctx, x, y, w, h) {
  const t = 4.4;
  const angle = Math.atan2(h, w);
  const dx = t / 2 / Math.sin(angle);
  const shadowOffset = (points) => points.map(([px, py]) => [px + 0.5, py + 0.75]);
  const braceA = [[x, y], [x + 2 * dx, y], [x + w, y + h], [x + w - 2 * dx, y + h]];
  const braceB = [[x + w - 2 * dx, y], [x + w, y], [x + 2 * dx, y + h], [x, y + h]];
  ctx.shadows.push(poly(shadowOffset(braceA), "rgba(0,0,0,0.5)"), poly(shadowOffset(braceB), "rgba(0,0,0,0.5)"));
  ctx.body.push(
    poly(braceA, ctx.color.hex),
    poly(braceA.slice(0, 2).concat([[x + 2 * dx, y + 0.3], [x, y + 0.3]]), light(ctx, 0.25)),
    poly(braceB, ctx.color.hex),
    // The second brace casts a shadow where it crosses the first.
    `<polyline points="${braceB.slice(2).concat(braceB.slice(0, 1)).map(([px, py]) => `${n(px)},${n(py)}`).join(" ")}" fill="none" stroke="${dark(ctx, 0.25)}" stroke-width="0.35"/>`,
    `<line x1="${n(x + w - 2 * dx)}" y1="${n(y)}" x2="${n(x)}" y2="${n(y + h)}" stroke="${light(ctx, 0.22)}" stroke-width="0.3"/>`,
  );
}

function carriageHardware(ctx) {
  const { W, id } = ctx;
  const iron = `url(#${id}-iron)`;
  for (const dx of [-7.2, 7.2]) {
    const x = W / 2 + dx;
    const y = 40;
    ctx.shadows.push(rect(x - 0.4, y + 0.6, 1.4, 9.2, "rgba(0,0,0,0.7)"));
    ctx.top.push(
      `<circle cx="${n(x)}" cy="${n(y + 0.8)}" r="1.15" fill="${iron}"/>`,
      `<circle cx="${n(x)}" cy="${n(y + 8.4)}" r="1.15" fill="${iron}"/>`,
      `<rect x="${n(x - 0.45)}" y="${n(y + 0.8)}" width="0.9" height="7.6" rx="0.45" fill="${iron}"/>`,
      `<rect x="${n(x - 0.2)}" y="${n(y + 1.2)}" width="0.18" height="6.6" fill="rgba(255,255,255,0.18)"/>`,
    );
  }
  const length = W > 150 ? 24 : 16;
  for (const y of [31, 66]) {
    hinge(ctx, 1.2, y, 1, length, iron);
    hinge(ctx, W - 1.2, y, -1, length, iron);
  }
}

function hinge(ctx, x0, y, dir, length, iron) {
  const neck = x0 + dir * length * 0.82;
  const tip = x0 + dir * length;
  const points = [
    [x0, y - 1.15],
    [neck, y - 0.6],
    [neck, y - 1.55],
    [tip, y],
    [neck, y + 1.55],
    [neck, y + 0.6],
    [x0, y + 1.15],
  ];
  ctx.shadows.push(poly(points.map(([px, py]) => [px + 0.4, py + 0.7]), "rgba(0,0,0,0.75)"));
  ctx.top.push(
    poly(points, iron),
    `<polyline points="${n(x0)},${n(y - 1.0)} ${n(neck)},${n(y - 0.48)}" fill="none" stroke="rgba(255,255,255,0.2)" stroke-width="0.22"/>`,
  );
  for (const t of [0.12, 0.42, 0.7]) {
    const cx = x0 + dir * length * t;
    ctx.top.push(
      `<circle cx="${n(cx)}" cy="${n(y)}" r="0.42" fill="#0d0d0e"/>`,
      `<circle cx="${n(cx - 0.12)}" cy="${n(y - 0.14)}" r="0.16" fill="rgba(255,255,255,0.35)"/>`,
    );
  }
}

function modernWindows(ctx, frame) {
  const { a, W } = ctx;
  if (a.windows === "plain") {
    const lites = W > 150 ? 6 : 4;
    const margin = W > 150 ? 8 : 6;
    const gap = 2.4;
    const lw = (W - 2 * margin - (lites - 1) * gap) / lites;
    for (let i = 0; i < lites; i++) {
      windowUnit(ctx, margin + i * (lw + gap), 6, lw, 9, { frame });
    }
  } else if (a.windows === "side") {
    const lw = W > 150 ? 15 : 12;
    for (let s = 0; s < SECTIONS; s++) {
      windowUnit(ctx, W - lw - (W > 150 ? 9 : 6), s * SECTION + 3.2, lw, SECTION - 6.4, { frame });
    }
  }
}

function modernDoor(ctx) {
  const { W } = ctx;
  // A faint reveal line near each section edge gives flush steel some depth.
  for (let s = 0; s < SECTIONS; s++) {
    ctx.body.push(rect(0, s * SECTION + 1.4, W, 0.2, light(ctx, 0.1)));
  }
  modernWindows(ctx, "#17191b");
}

function plankDoor(ctx) {
  const { W, H } = ctx;
  const count = 16;
  const ph = H / count;
  const next = random(W * 7 + 3);
  for (let i = 0; i < count; i++) {
    const y = i * ph;
    const v = next() - 0.5;
    ctx.body.push(rect(0, y, W, ph, v > 0 ? light(ctx, v * 0.12) : dark(ctx, -v * 0.12)));
    if (i > 0) ctx.body.push(rect(0, y - 0.3, W, 0.32, dark(ctx, 0.55)), rect(0, y + 0.02, W, 0.18, light(ctx, 0.12)));
  }
  modernWindows(ctx, "#17191b");
}

function glassDoor(ctx) {
  const { W, H } = ctx;
  const cols = W > 150 ? 5 : 3;
  const stile = 3.3;
  const rail = 2.4;
  const mullion = 2.3;
  const lw = (W - 2 * stile - (cols - 1) * mullion) / cols;
  for (let s = 0; s < SECTIONS; s++) {
    for (let i = 0; i < cols; i++) {
      const x = stile + i * (lw + mullion);
      const y = s * SECTION + rail;
      const h = SECTION - 2 * rail;
      ctx.body.push(
        rect(x - 0.4, y - 0.4, lw + 0.8, h + 0.8, dark(ctx, 0.28)),
        rect(x - 0.4, y + h, lw + 0.8, 0.4, light(ctx, 0.24)),
      );
      ctx.top.push(glass(ctx, x, y, lw, h));
    }
  }
  ctx.body.push(rect(0, 0, W, H, `url(#${ctx.id}-sheen)`));
}

/* ------------------------------------------------------------------ trim, interior, shading */

/** Mitered casing around the opening; the layers above it draw everything inside. */
function trimMarkup(a, id, W) {
  const { width: SW, height: SH } = sceneSize(a.width);
  const x0 = MARGIN;
  const x1 = MARGIN + TRIM;
  const x2 = x1 + W;
  const x3 = x2 + TRIM;
  const y0 = TOP_MARGIN;
  const y1 = TOP_MARGIN + TRIM;
  const hex = trimColor(a.trim);
  const ctx = shading(hex);
  const header = [[x0, y0], [x3, y0], [x2, y1], [x1, y1]];
  const legs = [
    [[x0, y0], [x1, y1], [x1, SH], [x0, SH]],
    [[x3, y0], [x3, SH], [x2, SH], [x2, y1]],
  ];
  const outline = (dx, dy) =>
    `<path d="M${n(x0 + dx)} ${SH}V${n(y0 + dy)}H${n(x3 + dx)}V${SH}H${n(x2 + dx)}V${n(y1 + dy)}H${n(x1 + dx)}V${SH}Z"/>`;
  const defs =
    `<linearGradient id="${id}-leg" x1="0" y1="0" x2="1" y2="0">${stops([
      [0, "#fff", 0.16 * ctx.hi],
      [0.45, "#fff", 0.03 * ctx.hi],
      [1, "#000", 0.1 * ctx.lo],
    ])}</linearGradient>` +
    `<linearGradient id="${id}-header" x1="0" y1="0" x2="0" y2="1">${stops([
      [0, "#fff", 0.2 * ctx.hi],
      [0.5, "#fff", 0.04 * ctx.hi],
      [1, "#000", 0.12 * ctx.lo],
    ])}</linearGradient>` +
    `<linearGradient id="${id}-daylight" gradientUnits="userSpaceOnUse" x1="${x0}" y1="${y0}" x2="${x3}" y2="${SH}">${stops([
      [0, "#fff", 0.06 * ctx.hi],
      [0.6, "#fff", 0],
      [1, "#000", 0.08 * ctx.lo],
    ])}</linearGradient>` +
    `<filter id="${id}-ambient" x="-10%" y="-10%" width="120%" height="120%"><feGaussianBlur stdDeviation="2.4"/></filter>` +
    `<filter id="${id}-contact" x="-10%" y="-10%" width="120%" height="120%"><feGaussianBlur stdDeviation="0.7"/></filter>`;
  // Each board is shaded on its own, so the miter joints read like real mitered trim.
  const boards = [[header, "header"], ...legs.map((points) => [points, "leg"])]
    .map(([points, profile]) => poly(points, hex) + poly(points, `url(#${id}-${profile})`) + poly(points, `url(#${id}-daylight)`))
    .join("");
  return (
    `<defs>${defs}</defs>` +
    // Soft shadows lift the trim off the plain background around it.
    `<g filter="url(#${id}-ambient)" fill="rgba(0,0,0,0.16)">${outline(0.6, 1.6)}</g>` +
    `<g filter="url(#${id}-contact)" fill="rgba(0,0,0,0.22)">${outline(0.3, 0.6)}</g>` +
    // Dark behind the opening, so any subpixel seam reads as shadow.
    rect(x1, y1, W, DOOR_HEIGHT, "#1b1c1d") +
    boards +
    // Eased edges: outer edges catch light from above and the left; inner edges turn into the opening.
    rect(x0, y0, x3 - x0, 0.35, light(ctx, 0.5)) +
    rect(x0, y0, 0.35, SH - y0, light(ctx, 0.3)) +
    rect(x3 - 0.35, y0, 0.35, SH - y0, dark(ctx, 0.18)) +
    rect(x1, y1 - 0.35, W, 0.35, dark(ctx, 0.22)) +
    rect(x1 - 0.35, y1, 0.35, DOOR_HEIGHT, dark(ctx, 0.16)) +
    rect(x2, y1, 0.35, DOOR_HEIGHT, light(ctx, 0.3)) +
    `<path d="M${x0} ${y0}L${x1} ${y1}M${x3} ${y0}L${x2} ${y1}" stroke="${dark(ctx, 0.16)}" stroke-width="0.2"/>`
  );
}

/** The garage seen through the opening, and its work light as a separate overlay. */
function interiorLayers(id, W) {
  const H = DOOR_HEIGHT;
  // One-point perspective of a garage about 22 ft deep with a 98 in ceiling, seen from the driveway.
  const vx = W / 2;
  const vy = H - 60;
  const viewer = 240;
  const depth = 264;
  const left = -18;
  const right = W + 18;
  const ceiling = -14;
  const project = (x, y, z) => {
    const s = viewer / (viewer + z);
    return [vx + (x - vx) * s, vy + (y - vy) * s];
  };
  const bl = project(left, H, depth);
  const br = project(right, H, depth);
  const tl = project(left, ceiling, depth);
  const tr = project(right, ceiling, depth);
  const [ox, oy] = project(vx, -3, 120);
  const line = (a, b, stroke, width) =>
    `<line x1="${n(a[0])}" y1="${n(a[1])}" x2="${n(b[0])}" y2="${n(b[1])}" stroke="${stroke}" stroke-width="${width}"/>`;
  const wallW = br[0] - bl[0];
  const wallH = bl[1] - tl[1];
  const base =
    `<defs>` +
    `<linearGradient id="${id}-back" x1="0" y1="0" x2="0" y2="1">${stops([[0, "#1f2123"], [0.7, "#2c2d2f"], [1, "#272829"]])}</linearGradient>` +
    `<linearGradient id="${id}-floor" x1="0" y1="0" x2="0" y2="1">${stops([[0, "#262524"], [0.55, "#3b3936"], [1, "#5b5751"]])}</linearGradient>` +
    `<linearGradient id="${id}-side" x1="0" y1="0" x2="1" y2="0">${stops([[0, "#3f4042"], [1, "#242527"]])}</linearGradient>` +
    `<linearGradient id="${id}-side-r" x1="1" y1="0" x2="0" y2="0">${stops([[0, "#38393b"], [1, "#222325"]])}</linearGradient>` +
    `</defs>` +
    rect(0, 0, W, H, "#1b1c1d") +
    poly([[left, ceiling], [right, ceiling], tr, tl], "#161718") +
    poly([[left, ceiling], tl, bl, [left, H]], `url(#${id}-side)`) +
    poly([[right, ceiling], tr, br, [right, H]], `url(#${id}-side-r)`) +
    poly([tl, tr, br, bl], `url(#${id}-back)`) +
    poly([[left, H], [right, H], br, bl], `url(#${id}-floor)`) +
    // Storage shelves and a bench along the back wall, kept low contrast.
    rect(bl[0] + wallW * 0.06, bl[1] - wallH * 0.36, wallW * 0.22, wallH * 0.36, "rgba(255,255,255,0.035)") +
    rect(bl[0] + wallW * 0.06, bl[1] - wallH * 0.37, wallW * 0.22, 0.45, "rgba(255,255,255,0.07)") +
    [0.62, 0.42, 0.22].map((t) => rect(br[0] - wallW * 0.3, bl[1] - wallH * t, wallW * 0.24, 0.5, "rgba(255,255,255,0.055)")).join("") +
    rect(br[0] - wallW * 0.3, bl[1] - wallH * 0.62, 0.5, wallH * 0.62, "rgba(255,255,255,0.04)") +
    rect(br[0] - wallW * 0.06 - 0.5, bl[1] - wallH * 0.62, 0.5, wallH * 0.62, "rgba(255,255,255,0.04)") +
    // Soft shading where the floor meets the walls.
    line([left, H], bl, "rgba(0,0,0,0.4)", 0.8) +
    line([right, H], br, "rgba(0,0,0,0.4)", 0.8) +
    line(bl, br, "rgba(0,0,0,0.35)", 0.7) +
    line(tl, tr, "rgba(0,0,0,0.3)", 0.5) +
    // Door tracks along the jambs.
    rect(0, 0, 1.7, H, "#2f3133") +
    rect(1.7, 0, 0.3, H, "rgba(255,255,255,0.08)") +
    rect(W - 1.7, 0, 1.7, H, "#2c2e30") +
    rect(W - 2, 0, 0.3, H, "rgba(255,255,255,0.05)") +
    // Opener head on its rail.
    rect(ox - 0.35, 0, 0.7, oy, "rgba(255,255,255,0.06)") +
    `<rect x="${n(ox - 6.5)}" y="${n(oy)}" width="13" height="4.8" rx="0.8" fill="#26282a"/>` +
    `<rect x="${n(ox - 3.2)}" y="${n(oy + 4.8)}" width="6.4" height="0.9" rx="0.45" fill="#3b3b39"/>`;
  const light =
    `<defs>` +
    `<radialGradient id="${id}-glow" gradientUnits="userSpaceOnUse" cx="${n(ox)}" cy="${n(oy + 6)}" r="${n(W * 0.62)}">${stops([
      [0, "#ffe3b4", 0.62],
      [0.22, "#ffd598", 0.3],
      [0.6, "#ffc982", 0.09],
      [1, "#ffc982", 0],
    ])}</radialGradient>` +
    `<radialGradient id="${id}-pool" gradientUnits="userSpaceOnUse" cx="${n(vx)}" cy="${n(H - 4)}" r="${n(W * 0.48)}">${stops([
      [0, "#ffdcaa", 0.22],
      [1, "#ffdcaa", 0],
    ])}</radialGradient>` +
    `<radialGradient id="${id}-lens" gradientUnits="userSpaceOnUse" cx="${n(ox)}" cy="${n(oy + 5.6)}" r="7">${stops([
      [0, "#fff6e2", 0.95],
      [0.3, "#ffe7bd", 0.5],
      [1, "#ffe0aa", 0],
    ])}</radialGradient>` +
    `</defs>` +
    rect(0, 0, W, H, "rgba(255,214,160,0.07)") +
    rect(0, 0, W, H, `url(#${id}-glow)`) +
    rect(0, 0, W, H, `url(#${id}-pool)`) +
    rect(ox - 8, oy - 2, 16, 14, `url(#${id}-lens)`) +
    `<rect x="${n(ox - 3.2)}" y="${n(oy + 4.8)}" width="6.4" height="0.9" rx="0.45" fill="#fff8ea"/>`;
  return { base, light };
}

function shadeMarkup(a, id, W) {
  const H = DOOR_HEIGHT;
  // The stop molding matches the trim but sits back in the opening, so it is a little darker.
  const hex = shade(trimColor(a.trim), -0.04);
  const ctx = shading(hex);
  const seal = W - 2 * STOP + 0.6;
  return (
    `<defs>` +
    `<linearGradient id="${id}-head-shadow" x1="0" y1="0" x2="0" y2="1">${stops([[0, "#000", 0.42], [0.35, "#000", 0.14], [1, "#000", 0]])}</linearGradient>` +
    `<linearGradient id="${id}-jamb-left" x1="0" y1="0" x2="1" y2="0">${stops([[0, "#000", 0.3], [1, "#000", 0]])}</linearGradient>` +
    `<linearGradient id="${id}-jamb-right" x1="1" y1="0" x2="0" y2="0">${stops([[0, "#000", 0.14], [1, "#000", 0]])}</linearGradient>` +
    `</defs>` +
    // Shadows the trim casts on the recessed door and into the garage.
    rect(0, STOP, W, 9, `url(#${id}-head-shadow)`) +
    rect(STOP, 0, 4, H, `url(#${id}-jamb-left)`) +
    rect(W - STOP - 2.5, 0, 2.5, H, `url(#${id}-jamb-right)`) +
    // Weatherstrip stop molding along the jambs and header.
    rect(0, 0, STOP, H, hex) +
    rect(W - STOP, 0, STOP, H, hex) +
    rect(0, 0, W, STOP, hex) +
    rect(0, 0, STOP, H, dark(ctx, 0.1)) +
    rect(W - STOP, 0, STOP, H, light(ctx, 0.08)) +
    rect(0, 0, W, STOP, dark(ctx, 0.14)) +
    // Its rubber seal against the door, and the joint where it meets the casing.
    rect(STOP - 0.3, STOP - 0.3, 0.3, H - STOP + 0.3, "rgba(0,0,0,0.42)") +
    rect(W - STOP, STOP - 0.3, 0.3, H - STOP + 0.3, "rgba(0,0,0,0.3)") +
    rect(STOP - 0.3, STOP - 0.3, seal, 0.3, "rgba(0,0,0,0.45)") +
    rect(0, 0, 0.2, H, "rgba(0,0,0,0.25)") +
    rect(W - 0.2, 0, 0.2, H, "rgba(0,0,0,0.2)") +
    rect(0, 0, W, 0.2, "rgba(0,0,0,0.3)")
  );
}

/* ------------------------------------------------------------------ live scene */

const SVG_NS = "http://www.w3.org/2000/svg";
/** Element ids only need to be unique within one image, so every image uses the same prefix. */
const ID = "m";

/** A standalone SVG document as a data URL; identical markup reuses the browser's decoded image. */
function svgUrl(width, height, body, fit = "none") {
  const svg = `<svg xmlns="${SVG_NS}" viewBox="0 0 ${n(width)} ${n(height)}" preserveAspectRatio="${fit}">${body}</svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

function layer(className) {
  const image = document.createElement("img");
  image.className = className;
  image.alt = "";
  image.draggable = false;
  image.decoding = "async";
  image.hidden = true;
  return image;
}

/** Whether the work light shows through frosted glass, which needs a lit version of the door. */
function hasGlow(a) {
  return a.glass === "frosted" && (a.style === "glass" || a.windows !== "none");
}

const easeInOut = (t) => 0.5 - Math.cos(Math.PI * t) / 2;

/** A garage door in its trim that animates between positions as the door state changes. */
export class DoorScene {
  constructor() {
    this.el = document.createElement("div");
    this.el.className = "scene";
    this._layers = {
      trim: layer("trim"),
      interior: layer("interior"),
      light: layer("light"),
      door: layer("door"),
      doorLit: layer("door-lit"),
      shade: layer("shade"),
    };
    const { trim, interior, light, door, doorLit, shade } = this._layers;
    this._opening = document.createElement("div");
    this._opening.className = "opening";
    this._doorLayer = document.createElement("div");
    this._doorLayer.className = "door-layer";
    this._doorLayer.append(door, doorLit);
    this._opening.append(interior, light, this._doorLayer, shade);
    this.el.append(trim, this._opening);
    this._key = "";
    this._generation = 0;
    this._position = 0;
    this._state = undefined;
    this._frame = 0;
  }

  get appearance() {
    return this._appearance;
  }

  setAppearance(appearance) {
    const a = normalizeAppearance(appearance);
    const key = JSON.stringify(a);
    if (key === this._key) return;
    this._key = key;
    this._appearance = a;
    const { width: SW, height: SH, doorWidth: W } = sceneSize(a.width);
    this.el.style.aspectRatio = `${SW} / ${SH}`;
    this.el.dataset.width = a.width;
    Object.assign(this._opening.style, {
      left: `${((MARGIN + TRIM) / SW) * 100}%`,
      top: `${((TOP_MARGIN + TRIM) / SH) * 100}%`,
      width: `${(W / SW) * 100}%`,
      height: `${(DOOR_HEIGHT / SH) * 100}%`,
    });
    const interior = interiorLayers(ID, W);
    this._show({
      trim: svgUrl(SW, SH, trimMarkup(a, ID, W), "xMidYMid slice"),
      interior: svgUrl(W, DOOR_HEIGHT, interior.base),
      light: svgUrl(W, DOOR_HEIGHT, interior.light),
      door: svgUrl(W, DOOR_HEIGHT, doorMarkup(a, ID)),
      doorLit: hasGlow(a) ? svgUrl(W, DOOR_HEIGHT, doorMarkup(a, ID, true)) : null,
      shade: svgUrl(W, DOOR_HEIGHT, shadeMarkup(a, ID, W)),
    });
  }

  /** Decode every new layer before showing any, so a new look never flashes or mixes with the old. */
  async _show(urls) {
    const generation = ++this._generation;
    await Promise.all(
      Object.values(urls)
        .filter(Boolean)
        .map((url) => {
          const image = new Image();
          image.src = url;
          return image.decode().catch(() => {});
        }),
    );
    if (generation !== this._generation) return;
    for (const [name, url] of Object.entries(urls)) {
      const image = this._layers[name];
      if (url && image.getAttribute("src") !== url) image.src = url;
      image.hidden = !url;
    }
  }

  setLight(on) {
    this.el.classList.toggle("lit", Boolean(on));
  }

  /** Move the door to reflect a cover state; the first call places it without animation. */
  setState(state) {
    const previous = this._state;
    this._state = state;
    this.el.dataset.state = state;
    const reduceMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (previous === undefined || reduceMotion) {
      this._stop();
      this._place(restingPosition(state, this._position));
      return;
    }
    if (state === previous) return;
    const p = this._position;
    switch (state) {
      case "opening":
        this._animate(Math.max(p, HOLD_OPENING), Math.max(0, HOLD_OPENING - p) * TRAVEL_MS);
        break;
      case "closing":
        this._animate(Math.min(p, HOLD_CLOSING), Math.max(0, p - HOLD_CLOSING) * TRAVEL_MS);
        break;
      case "open":
        this._animate(1, Math.min(FINISH_MS, Math.max(450, (1 - p) * FINISH_MS)));
        break;
      case "closed":
        this._animate(0, Math.min(FINISH_MS, Math.max(450, p * FINISH_MS)));
        break;
      default:
        this._stop();
    }
  }

  destroy() {
    this._stop();
  }

  _place(position) {
    this._position = position;
    this._doorLayer.style.transform = `translate3d(0, ${n(-position * (1 - OPEN_REVEAL) * 100)}%, 0)`;
  }

  _animate(target, duration) {
    this._stop();
    const from = this._position;
    if (duration <= 0 || from === target) {
      this._place(target);
      return;
    }
    const start = performance.now();
    const step = (now) => {
      const t = Math.min(1, (now - start) / duration);
      this._place(from + (target - from) * easeInOut(t));
      this._frame = t < 1 ? requestAnimationFrame(step) : 0;
    };
    this._frame = requestAnimationFrame(step);
  }

  _stop() {
    if (this._frame) cancelAnimationFrame(this._frame);
    this._frame = 0;
  }
}

function restingPosition(state, current) {
  switch (state) {
    case "open":
      return 1;
    case "opening":
      return 0.45;
    case "closing":
      return 0.55;
    case "closed":
      return 0;
    default:
      return current;
  }
}

/** Image URL of a door on its own for style pickers, with a dark backdrop behind any glass. */
export function doorThumbnail(appearance) {
  const a = normalizeAppearance(appearance);
  const W = DOOR_WIDTH[a.width];
  return svgUrl(W, DOOR_HEIGHT, rect(0, 0, W, DOOR_HEIGHT, "#232528") + doorMarkup(a, ID), "xMidYMid meet");
}
