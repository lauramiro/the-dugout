// The 404 page for any address the static export does not have (Static Web Apps serves it
// through the responseOverrides rule in public/staticwebapp.config.json). The viewer's
// language is not known here, so it says it in both.
export default function NotFound() {
  return (
    <main className="not-found">
      <p className="eyebrow">404</p>
      <h1>No match on this page</h1>
      <p lang="es">Aquí no hay partido.</p>
      <nav aria-label="The Dugout">
        <a href="/">Broadcast view</a>
        <a href="/desk">Analyst desk</a>
        <a href="/fan">Fan view</a>
      </nav>
    </main>
  );
}
