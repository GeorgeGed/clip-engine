// The caption colours a job can pick. Mirrors PALETTE in
// engine/caption_colour.py, where every entry is measured to stay legible
// against the caption's black stroke; tests/test_caption_colours.py checks
// that the two lists match key for key and hex for hex.
export const CAPTION_COLOURS: ReadonlyArray<{ key: string; label: string; hex: string }> = [
  { key: "white", label: "White", hex: "#FFFFFF" },
  { key: "cream", label: "Cream", hex: "#FFF0A1" },
  { key: "yellow", label: "Yellow", hex: "#FFE94E" },
  { key: "gold", label: "Gold", hex: "#FFCE00" },
  { key: "orange", label: "Orange", hex: "#FF8A3D" },
  { key: "vermilion", label: "Vermilion", hex: "#F4512A" },
  { key: "red", label: "Red", hex: "#FF4655" },
  { key: "pink", label: "Pink", hex: "#FF5CA8" },
  { key: "violet", label: "Violet", hex: "#A855F7" },
  { key: "blue", label: "Blue", hex: "#5C80FF" },
  { key: "cyan", label: "Cyan", hex: "#22D3EE" },
  { key: "aqua", label: "Aqua", hex: "#94FFFE" },
  { key: "green", label: "Green", hex: "#2BD96B" },
  { key: "lime", label: "Lime", hex: "#DEFF9D" },
];

export const DEFAULT_CAPTION_FILL = "cream";
export const DEFAULT_CAPTION_EMPH = "lime";

export const isCaptionColour = (key: unknown): key is string =>
  typeof key === "string" && CAPTION_COLOURS.some((c) => c.key === key);

export function captionColourLabel(key: string | null | undefined, fallback: string): string {
  return CAPTION_COLOURS.find((c) => c.key === (key ?? fallback))?.label ?? key ?? "";
}
