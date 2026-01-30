import { useState, useRef, useEffect } from 'react';
import './MonthPicker.css';

const MONTHS_SHORT = [
  'Jan', 'Feb', 'Mar', 'Apr', 'Maj', 'Jun',
  'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dec'
];

const MONTH_NAMES = [
  'Januari', 'Februari', 'Mars', 'April', 'Maj', 'Juni',
  'Juli', 'Augusti', 'September', 'Oktober', 'November', 'December'
];

function MonthPicker({ year, month, onYearChange, onMonthChange }) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);

  const currentDate = new Date();
  const currentYear = currentDate.getFullYear();
  const currentMonth = currentDate.getMonth() + 1;

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handlePrevYear = (e) => {
    e.stopPropagation();
    onYearChange(year - 1);
  };

  const handleNextYear = (e) => {
    e.stopPropagation();
    if (year < currentYear) {
      onYearChange(year + 1);
    }
  };

  const handleMonthClick = (monthIndex) => {
    if (year === currentYear && monthIndex + 1 > currentMonth) {
      return;
    }
    onMonthChange(monthIndex + 1);
    setIsOpen(false);
  };

  const isMonthDisabled = (monthIndex) => {
    return year === currentYear && monthIndex + 1 > currentMonth;
  };

  const isMonthSelected = (monthIndex) => {
    return monthIndex + 1 === month;
  };

  const isCurrentMonth = (monthIndex) => {
    return year === currentYear && monthIndex + 1 === currentMonth;
  };

  return (
    <div className="month-picker-compact" ref={dropdownRef}>
      <button
        className={`month-picker-trigger ${isOpen ? 'open' : ''}`}
        onClick={() => setIsOpen(!isOpen)}
        aria-expanded={isOpen}
        aria-haspopup="true"
      >
        <svg className="calendar-icon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/>
          <line x1="16" y1="2" x2="16" y2="6"/>
          <line x1="8" y1="2" x2="8" y2="6"/>
          <line x1="3" y1="10" x2="21" y2="10"/>
        </svg>
        <span className="trigger-text">
          <span className="trigger-month">{MONTH_NAMES[month - 1]}</span>
          <span className="trigger-year">{year}</span>
        </span>
        <svg className="chevron-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="6 9 12 15 18 9"/>
        </svg>
      </button>

      {isOpen && (
        <div className="month-picker-dropdown">
          <div className="dropdown-header">
            <button
              className="year-nav-btn"
              onClick={handlePrevYear}
              aria-label="Föregående år"
            >
              <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
                <path d="M12.5 15L7.5 10L12.5 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
            <span className="year-display">{year}</span>
            <button
              className="year-nav-btn"
              onClick={handleNextYear}
              disabled={year >= currentYear}
              aria-label="Nästa år"
            >
              <svg width="18" height="18" viewBox="0 0 20 20" fill="none">
                <path d="M7.5 15L12.5 10L7.5 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </button>
          </div>

          <div className="month-grid">
            {MONTHS_SHORT.map((monthName, index) => (
              <button
                key={index}
                className={`month-btn ${isMonthSelected(index) ? 'selected' : ''} ${isCurrentMonth(index) ? 'current' : ''} ${isMonthDisabled(index) ? 'disabled' : ''}`}
                onClick={() => handleMonthClick(index)}
                disabled={isMonthDisabled(index)}
              >
                {monthName}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

export default MonthPicker;
