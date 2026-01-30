import { useState } from 'react';
import MonthlyReport from './components/MonthlyReport';
import './App.css';

// Icon components
const ReportIcon = () => (
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
    <polyline points="14 2 14 8 20 8"/>
    <line x1="16" y1="13" x2="8" y2="13"/>
    <line x1="16" y1="17" x2="8" y2="17"/>
    <polyline points="10 9 9 9 8 9"/>
  </svg>
);

const BoltIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
    <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
  </svg>
);

function App() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const navItems = [
    { id: 'MonthlyReport', label: 'Månadsrapport', icon: ReportIcon },
  ];

  return (
    <div className="app-layout">
      {/* Sidebar */}
      <aside className={`sidebar ${sidebarCollapsed ? 'collapsed' : ''}`}>
        <div className="sidebar-header">
          <div className="logo">
            <div className="logo-icon">
              <BoltIcon />
            </div>
            {!sidebarCollapsed && (
              <div className="logo-text">
                <span className="logo-title">HomeAnalytics</span>
                <span className="logo-subtitle">Energiövervakning</span>
              </div>
            )}
          </div>
        </div>

        <nav className="sidebar-nav">
          {navItems.map(item => (
            <button
              key={item.id}
              className="nav-item active"
              title={sidebarCollapsed ? item.label : undefined}
            >
              <span className="nav-icon">
                <item.icon />
              </span>
              {!sidebarCollapsed && <span className="nav-label">{item.label}</span>}
              <span className="nav-indicator" />
            </button>
          ))}
        </nav>

        <div className="sidebar-footer">
          <button
            className="collapse-btn"
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            title={sidebarCollapsed ? 'Expandera' : 'Minimera'}
          >
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              style={{ transform: sidebarCollapsed ? 'rotate(180deg)' : 'none' }}
            >
              <polyline points="15 18 9 12 15 6"/>
            </svg>
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="main-content">
        <header className="content-header">
          <div className="header-title">
            <h1>Månadsrapport</h1>
            <p className="header-subtitle">
              Förbrukning och kostnadsöversikt per månad
            </p>
          </div>
        </header>

        <div className="content-body">
          <MonthlyReport />
        </div>
      </main>
    </div>
  );
}

export default App;
