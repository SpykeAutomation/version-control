// Placeholder for nav sections that aren't built yet, so the shell is navigable.
export function ComingSoon({ title }: { title: string }) {
  return (
      <div className="app-scroll">
        <div className="page-pad">
          <div className="page-header">
            <h1>{title}</h1>
          </div>
          <div className="empty-state">
            <h3>{title} is coming soon</h3>
            <p>This section isn't built yet.</p>
          </div>
        </div>
      </div>
  );
}
