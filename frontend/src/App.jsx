import { useState } from 'react';
import MonthlyReport from './components/MonthlyReport';
import './App.css';

// Icon components
const BoltIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
    <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
  </svg>
);

function App() {
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
        </div>
      </header>

      {/* Main Content */}
      <main className="main-content">
        <MonthlyReport />
      </main>
    </div>
  );
}

export default App;
