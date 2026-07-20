// The tab strip used by the review pages (merge request, commit, create-MR).
// Generic over the page's tab-key union so each page keeps its own typing.
export interface TabDef<K extends string> {
  key: K;
  label: string;
  count?: number;
}

export function TabStrip<K extends string>({
  tabs,
  active,
  onSelect,
  className,
}: {
  tabs: TabDef<K>[];
  active: K;
  onSelect: (k: K) => void;
  className?: string;
}) {
  return (
    <nav className={`pr-tabs${className ? ` ${className}` : ""}`}>
      {tabs.map((t) => (
        <button
          key={t.key}
          className={`pr-tab${t.key === active ? " active" : ""}`}
          type="button"
          onClick={() => onSelect(t.key)}
        >
          {t.label}
          {t.count != null && <span className="pr-tab-count">{t.count}</span>}
        </button>
      ))}
    </nav>
  );
}
