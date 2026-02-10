import { useState, useEffect } from 'react';
import MonthRangePicker from './MonthRangePicker';
import './Invoice.css';

const MONTHS = [
  'Januari', 'Februari', 'Mars', 'April', 'Maj', 'Juni',
  'Juli', 'Augusti', 'September', 'Oktober', 'November', 'December'
];

function Invoice() {
  const currentDate = new Date();
  const currentYear = currentDate.getFullYear();
  const currentMonth = currentDate.getMonth() + 1;

  // Default range: 6 months back to previous month
  const defaultEndMonth = currentMonth === 1 ? 12 : currentMonth - 1;
  const defaultEndYear = currentMonth === 1 ? currentYear - 1 : currentYear;
  const sixMonthsBack = new Date(defaultEndYear, defaultEndMonth - 6, 1);
  const defaultStartMonth = sixMonthsBack.getMonth() + 1;
  const defaultStartYear = sixMonthsBack.getFullYear();

  const [startYear, setStartYear] = useState(defaultStartYear);
  const [startMonth, setStartMonth] = useState(defaultStartMonth);
  const [endYear, setEndYear] = useState(defaultEndYear);
  const [endMonth, setEndMonth] = useState(defaultEndMonth);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    // Validate range before fetching
    const startVal = startYear * 12 + startMonth;
    const endVal = endYear * 12 + endMonth;
    if (startVal > endVal) {
      setError('Startmånad måste vara före slutmånad');
      setData(null);
      return;
    }

    const controller = new AbortController();
    setLoading(true);
    setError(null);

    const params = new URLSearchParams({
      start_year: startYear,
      start_month: startMonth,
      end_year: endYear,
      end_month: endMonth,
    });
    fetch(`./api/report/invoice?${params}`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) {
          const errorData = await response.json();
          throw new Error(errorData.detail || 'Failed to fetch invoice data');
        }
        return response.json();
      })
      .then((result) => {
        setData(result);
        setLoading(false);
      })
      .catch((err) => {
        if (err.name === 'AbortError') return;
        setError(err.message);
        setData(null);
        setLoading(false);
      });

    return () => controller.abort();
  }, [startYear, startMonth, endYear, endMonth]);

  const formatCurrency = (value) => {
    if (value === null || value === undefined) return '-';
    return new Intl.NumberFormat('sv-SE', {
      style: 'currency',
      currency: 'SEK',
      minimumFractionDigits: 2,
    }).format(value);
  };

  const formatNumber = (value, decimals = 1) => {
    if (value === null || value === undefined) return '-';
    return new Intl.NumberFormat('sv-SE', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    }).format(value);
  };

  const periodLabel = () => {
    const start = `${MONTHS[startMonth - 1]} ${startYear}`;
    const end = `${MONTHS[endMonth - 1]} ${endYear}`;
    return start === end ? start : `${start} – ${end}`;
  };

  return (
    <div className="invoice-view">
      {/* Page Header */}
      <div className="page-header">
        <div className="page-header-left">
          <h1 className="page-title">Faktura</h1>
          <p className="page-subtitle">Elkostnad för salong Lene's Hår</p>
        </div>
        <div className="page-header-right">
          <MonthRangePicker
            startYear={startYear}
            startMonth={startMonth}
            onStartYearChange={setStartYear}
            onStartMonthChange={setStartMonth}
            endYear={endYear}
            endMonth={endMonth}
            onEndYearChange={setEndYear}
            onEndMonthChange={setEndMonth}
          />
          {loading && (
            <div className="loading-indicator">
              <div className="loading-spinner"></div>
            </div>
          )}
        </div>
      </div>

      {/* Invoice Content */}
      <div className={`report-content ${loading && data ? 'loading-overlay' : ''}`}>
        {error && (
          <div className="error-card">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"/>
              <line x1="12" y1="8" x2="12" y2="12"/>
              <line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            <span>{error}</span>
          </div>
        )}

        {data && (
          <div className="invoice-card">
            <div className="invoice-header">
              <div className="faktura-header-left">
                <h3>Faktura — Elkostnad</h3>
                <span className="faktura-tenant">Lene's Hår AB · Gustavsgatan 32</span>
              </div>
              <span className="invoice-period">{periodLabel()}</span>
            </div>

            <div className="invoice-body">
              <table className="faktura-table">
                <thead>
                  <tr>
                    <th>Period</th>
                    <th className="col-numeric">Avläst (kWh)</th>
                    <th className="col-numeric">Elförbrukning (kWh)</th>
                    <th className="col-numeric">Elkostnad (kr/kWh)</th>
                    <th className="col-numeric">Belopp (SEK)</th>
                  </tr>
                </thead>
                <tbody>
                  {data.invoice_months.map((row) => (
                    <tr key={`${row.year}-${row.month}`}>
                      <td className="col-period">{row.period_label}</td>
                      <td className="col-numeric">{formatNumber(row.meter_reading_kwh)}</td>
                      <td className="col-numeric">{formatNumber(row.consumption_kwh)}</td>
                      <td className="col-numeric">{formatNumber(row.cost_per_kwh, 2)}</td>
                      <td className="col-numeric col-amount">{formatCurrency(row.total_cost_sek)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="grand-total">
                    <td><strong>TOTALT</strong></td>
                    <td className="col-numeric"></td>
                    <td className="col-numeric"><strong>{formatNumber(data.grand_total.total_consumption_kwh)}</strong> <span className="cell-unit">kWh</span></td>
                    <td className="col-numeric"></td>
                    <td className="col-numeric col-amount"><strong>{formatCurrency(data.grand_total.total_cost_sek)}</strong></td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </div>
        )}

        {!data && !loading && !error && (
          <div className="empty-state">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <line x1="16" y1="13" x2="8" y2="13"/>
              <line x1="16" y1="17" x2="8" y2="17"/>
            </svg>
            <p>Välj en period för att generera faktura</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default Invoice;
