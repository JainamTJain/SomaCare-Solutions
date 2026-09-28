import { NavLink } from "react-router-dom";

export default function SiteChrome({ children }) {
  return (
    <div className="site">
      <header className="nav">
        <NavLink to="/" className="brand">SomaCare</NavLink>
        <nav>
          <NavLink to="/try">Try it live</NavLink>
          <NavLink to="/live">Watch live</NavLink>
        </nav>
      </header>
      <main>{children}</main>
    </div>
  );
}

export function CareFooter() {
  return (
    <footer className="care-footer">
      Fictional residents. Intervals are starting points a nurse must approve. Not a medical device.
    </footer>
  );
}
