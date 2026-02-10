import { useState } from 'react';
import MonthlyReport from './components/MonthlyReport';
import Invoice from './components/Invoice';
import './App.css';

// Icon components
const BoltIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
    <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
  </svg>
);

function App() {
  const [view, setView] = useState('report');

  return (
    <div className="app-layout">
      {/* Top Navigation */}
      <header className="top-nav">
        <div className="nav-left">
          <div className="logo">
            <div className="logo-icon">
              <BoltIcon />
            </div>
            <div className="logo-text">
              <span className="logo-title">HomeAnalytics</span>
            </div>
          </div>
          <nav className="nav-links">
            <button
              className={`nav-link ${view === 'report' ? 'active' : ''}`}
              onClick={() => setView('report')}
            >
              Månadsrapport
            </button>
            <button
              className={`nav-link ${view === 'invoice' ? 'active' : ''}`}
              onClick={() => setView('invoice')}
            >
              Faktura
            </button>
          </nav>
        </div>
      </header>

      {/* Main Content */}
      <main className="main-content">
        {view === 'report' && <MonthlyReport />}
        {view === 'invoice' && <Invoice />}
      </main>
    </div>
  );
}

export default App;
