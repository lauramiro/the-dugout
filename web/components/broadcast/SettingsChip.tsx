import { useEffect, useRef, useState, type ReactNode } from "react";
import type { Locale, Mode, Roster, TeamCode } from "../../lib/contracts";
import { SPEEDS, type FeedState, type PlaybackControls } from "../../lib/datasource";
import { LOCALES, type Translate } from "../../lib/i18n";

export interface BroadcastPrefs {
  mode: Mode;
  locale: Locale;
  club: TeamCode | null;
  player: string | null;
}

export const DEFAULT_PREFS: BroadcastPrefs = { mode: "casual", locale: "en", club: null, player: null };

const PREFS_KEY = "dugout.broadcast";

// Per-viewer preference only; the page works the same without storage.
export function readPrefs(): Partial<BroadcastPrefs> {
  try {
    const raw = JSON.parse(localStorage.getItem(PREFS_KEY) ?? "{}") as Record<string, unknown>;
    const out: Partial<BroadcastPrefs> = {};
    if (raw.mode === "casual" || raw.mode === "analyst") out.mode = raw.mode;
    if (LOCALES.includes(raw.locale as Locale)) out.locale = raw.locale as Locale;
    if (typeof raw.club === "string" || raw.club === null) out.club = raw.club as TeamCode | null;
    if (typeof raw.player === "string" || raw.player === null) out.player = raw.player as string | null;
    return out;
  } catch {
    return {};
  }
}

export function writePrefs(prefs: BroadcastPrefs): void {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
  } catch {
    // storage blocked: keep the choice for this visit only
  }
}

interface Props {
  prefs: BroadcastPrefs;
  onChange: (prefs: BroadcastPrefs) => void;
  roster: Roster | null;
  controls: PlaybackControls | null;
  feed: FeedState;
  recordedTracking: boolean;
  extra?: ReactNode;
  t: Translate;
}

/** Top-right chip: closed it shows the viewer's mode and language; open, every setting. */
export function SettingsChip({ prefs, onChange, roster, controls, feed, recordedTracking, extra, t }: Props) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const chip = useRef<HTMLButtonElement>(null);
  // Open, it closes like any popover: Escape (focus back on the chip) or a press outside it.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      chip.current?.focus();
    };
    const onPress = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onPress);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onPress);
    };
  }, [open]);
  const set = (patch: Partial<BroadcastPrefs>) => onChange({ ...prefs, ...patch });
  const teams = roster ? [roster.home, roster.away] : [];
  return (
    <div ref={root} className={`bc-settings${open ? " open" : ""}`}>
      <button ref={chip} type="button" className="bc-chip" aria-expanded={open} onClick={() => setOpen(!open)}>
        {t("broadcastSettings")} · {prefs.locale.toUpperCase()} · {prefs.mode === "casual" ? t("casual") : t("analyst")}
      </button>
      {open && (
        <div className="bc-panel">
          <Row label={t("view")}>
            {(["casual", "analyst"] as const).map((m) => (
              <button key={m} type="button" aria-pressed={prefs.mode === m} onClick={() => set({ mode: m })}>
                {m === "casual" ? t("casual") : t("analyst")}
              </button>
            ))}
          </Row>
          <Row label={t("language")}>
            {LOCALES.map((l) => (
              <button key={l} type="button" aria-pressed={prefs.locale === l} onClick={() => set({ locale: l })}>
                {l.toUpperCase()}
              </button>
            ))}
          </Row>
          <Row label={t("favouriteClub")}>
            <select value={prefs.club ?? ""} onChange={(e) => set({ club: e.target.value || null })}>
              <option value="">{t("none")}</option>
              {teams.map((team) => (
                <option key={team} value={team}>{roster?.teams[team]?.name ?? team}</option>
              ))}
            </select>
          </Row>
          <Row label={t("playerFocus")}>
            <select value={prefs.player ?? ""} onChange={(e) => set({ player: e.target.value || null })}>
              <option value="">{t("none")}</option>
              {teams.map((team) => (
                <optgroup key={team} label={roster?.teams[team]?.name ?? team}>
                  {Object.entries(roster?.players ?? {})
                    .filter(([, p]) => p.team === team)
                    .map(([id, p]) => (
                      <option key={id} value={id}>{p.name} ({id})</option>
                    ))}
                </optgroup>
              ))}
            </select>
          </Row>
          {controls && (
            <Row label={t("replay")}>
              <button type="button" onClick={() => (feed.playing ? controls.pause() : controls.play())}>
                {feed.playing ? t("pause") : t("play")}
              </button>
              {SPEEDS.map((s) => (
                <button key={s} type="button" aria-pressed={feed.speed === s} onClick={() => controls.setSpeed(s)}>
                  {s}x
                </button>
              ))}
            </Row>
          )}
          {recordedTracking && <p className="bc-note">{t("recordedTracking")}</p>}
          {extra}
        </div>
      )}
    </div>
  );
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="bc-row">
      <span className="bc-row-label">{label}</span>
      <span className="bc-row-controls">{children}</span>
    </div>
  );
}
