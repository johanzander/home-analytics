import { useState } from 'react';
import './MonthPicker.css';

const MONTHS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'Maj', 'Jun',
  'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dec'
];

const MONTH_NAMES = [
  'Januari', 'Februari', 'Mars', 'April', 'Maj', 'Juni',
  'Juli', 'Augusti', 'September', 'Oktober', 'November', 'December'
];

function MonthPicker({ year, month, onYearChange, onMonthChange }) {
  const currentDate = new Date();
  const currentYear = currentDate.getFullYear();
  const currentMonth = currentDate.getMonth() + 1;

  const handlePrevYear = () => {
    onYearChange(year - 1);
  };

  const handleNextYear = () => {
    if (year < currentYear) {
      onYearChange(year + 1);
    }
  };

  const handleMonthClick = (monthIndex) => {
    // Don't allow selecting future months
    if (year === currentYear && monthIndex + 1 > currentMonth) {
      return;
    }
    onMonthChange(monthIndex + 1);
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
    <div className="month-picker">
      <div className="month-picker-header">
        <button
          className="year-nav-btn"
          onClick={handlePrevYear}
          aria-label="Previous year"
        >
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M12.5 15L7.5 10L12.5 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
        <span className="year-display">{year}</span>
        <button
          className="year-nav-btn"
          onClick={handleNextYear}
          disabled={year >= currentYear}
          aria-label="Next year"
        >
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path d="M7.5 15L12.5 10L7.5 5" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
      </div>

      <div className="month-grid">
        {MONTHS.map((monthName, index) => (
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

      <div className="selected-period">
        {MONTH_NAMES[month - 1]} {year}
      </div>
    </div>
  );
}

export default MonthPicker;
