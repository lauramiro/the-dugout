import type { Locale, Mode, Roster, TeamCode } from "../lib/contracts";
import type { Translate } from "../lib/i18n";

export interface Settings {
  mode: Mode;
  focus: TeamCode;
  locale: Locale;
}

interface Props {
  settings: Settings;
  roster: Roster | null;
  onChange: (next: Settings) => void;
  t: Translate;
}

function Segmented<T extends string>({ label, value, options, onPick }: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onPick: (v: T) => void;
}) {
  return (
    <div className="switch">
      <span className="switch-label">{label}</span>
      <div className="segmented" role="group" aria-label={label}>
        {options.map((o) => (
          <button key={o.value} aria-pressed={o.value === value} onClick={() => onPick(o.value)}>
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function ModeSwitcher({ settings, roster, onChange, t }: Props) {
  const teams = roster ? [roster.home, roster.away] : [settings.focus];
  return (
    <div className="mode-switcher">
      <Segmented
        label={t("view")}
        value={settings.mode}
        options={[
          { value: "casual", label: t("casual") },
          { value: "analyst", label: t("analyst") },
        ]}
        onPick={(mode) => onChange({ ...settings, mode })}
      />
      <Segmented
        label={t("club")}
        value={settings.focus}
        options={teams.map((code) => ({ value: code, label: roster?.teams[code]?.name.split(" ")[0] ?? code }))}
        onPick={(focus) => onChange({ ...settings, focus })}
      />
    </div>
  );
}
