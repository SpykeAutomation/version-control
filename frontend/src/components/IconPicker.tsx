// The repository icon picker — ten glyphs by three colour tones, reporting
// the encoded 1..30 code. Shared by the Settings Appearance card and the
// create-project page. The tone chips recolour the grid; switching tone with
// a glyph already chosen re-encodes the selection in place.
import { useState } from "react";
import {
  decodeRepoIcon,
  encodeRepoIcon,
  REPO_GLYPHS,
  REPO_TONES,
} from "../lib/repoIcons";

export function IconPicker({
  selected,
  onSelect,
  disabled,
}: {
  selected: number | null; // a 1..30 code, or null when nothing is chosen
  onSelect: (code: number) => void;
  disabled?: boolean;
}) {
  const decoded = decodeRepoIcon(selected);
  // The tone previewed before any glyph is chosen; a real selection's tone
  // always wins.
  const [previewTone, setPreviewTone] = useState(0);
  const toneIdx = decoded ? decoded.toneIndex : previewTone;

  return (
    <div className="icon-picker">
      <div className="tone-row" role="radiogroup" aria-label="Icon colour">
        {REPO_TONES.map((tone, ti) => (
          <button
            key={tone}
            type="button"
            className={`tone-chip tone-chip-${tone}${ti === toneIdx ? " selected" : ""}`}
            disabled={disabled}
            aria-label={`${tone} tone`}
            title={tone}
            onClick={() => {
              setPreviewTone(ti);
              if (decoded) onSelect(encodeRepoIcon(decoded.glyphIndex, ti));
            }}
          />
        ))}
      </div>
      <div className="icon-pick">
        {REPO_GLYPHS.map((g, gi) => (
          <button
            key={gi}
            type="button"
            className={`icon-swatch tone-${REPO_TONES[toneIdx]}${
              decoded?.glyphIndex === gi ? " selected" : ""
            }`}
            title={g.label}
            disabled={disabled}
            onClick={() => onSelect(encodeRepoIcon(gi, toneIdx))}
          >
            {g.glyph(28)}
          </button>
        ))}
      </div>
    </div>
  );
}
