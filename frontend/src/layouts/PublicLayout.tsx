import { Link, Outlet } from 'react-router-dom';
import './PublicLayout.css';

export function PublicLayout() {
  return (
    <div className="public-layout">
      <header className="public-layout__header">
        <div className="public-layout__header-inner">
          <Link to="/" className="public-layout__logo">
            <span className="public-layout__logo-mark">PC</span>
            <span>Payroll Copilot</span>
          </Link>
          <nav className="public-layout__nav">
            <Link to="/login" className="btn btn--ghost">
              Log in
            </Link>
            <Link to="/signup" className="btn btn--primary">
              Sign up
            </Link>
          </nav>
        </div>
      </header>
      <main className="public-layout__main">
        <Outlet />
      </main>
      <footer className="public-layout__footer">
        <p>Payroll Copilot — Deterministic compliance validation for Israeli payroll.</p>
      </footer>
    </div>
  );
}
