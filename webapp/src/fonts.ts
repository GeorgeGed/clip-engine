// The caption fonts a job can pick. Mirrors engine/caption_fonts.py, which
// owns the files and the rendering; tests/test_caption_fonts.py checks that
// the two lists match key for key.
export const CAPTION_FONTS: ReadonlyArray<{ key: string; label: string }> = [
  { key: "baloo", label: "Baloo 2 ExtraBold" },
  { key: "tiktok", label: "TikTok Sans Bold" },
  { key: "montserrat", label: "Montserrat Black" },
  { key: "poppins", label: "Poppins ExtraBold" },
  { key: "anton", label: "Anton" },
  { key: "bebas", label: "Bebas Neue" },
  { key: "bangers", label: "Bangers" },
  { key: "luckiest", label: "Luckiest Guy" },
];

export const DEFAULT_CAPTION_FONT = "baloo";

export function captionFontLabel(key: string | null | undefined): string {
  return CAPTION_FONTS.find((f) => f.key === (key ?? DEFAULT_CAPTION_FONT))?.label ?? key ?? "";
}
