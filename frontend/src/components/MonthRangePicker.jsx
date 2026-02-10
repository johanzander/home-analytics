import MonthPicker from './MonthPicker';
import './MonthRangePicker.css';

function MonthRangePicker({
  startYear, startMonth, onStartYearChange, onStartMonthChange,
  endYear, endMonth, onEndYearChange, onEndMonthChange,
}) {
  return (
    <div className="month-range-picker">
      <div className="range-field">
        <label className="range-label">Från</label>
        <MonthPicker
          year={startYear}
          month={startMonth}
          onYearChange={onStartYearChange}
          onMonthChange={onStartMonthChange}
        />
      </div>
      <span className="range-separator">—</span>
      <div className="range-field">
        <label className="range-label">Till</label>
        <MonthPicker
          year={endYear}
          month={endMonth}
          onYearChange={onEndYearChange}
          onMonthChange={onEndMonthChange}
        />
      </div>
    </div>
  );
}

export default MonthRangePicker;
