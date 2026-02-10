import { useState, useEffect } from 'react';
import MonthPicker from './MonthPicker';
import './MonthlyReport.css';

const MONTHS = [
  'Januari', 'Februari', 'Mars', 'April', 'Maj', 'Juni',
  'Juli', 'Augusti', 'September', 'Oktober', 'November', 'December'
];

function MonthlyReport() {
  const currentDate = new Date();
  const [year, setYear] = useState(currentDate.getFullYear());
  const [month, setMonth] = useState(currentDate.getMonth() + 1);
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Fetch report automatically when month/year changes
  useEffect(() => {
    fetchReport();
  }, [year, month]);

  const fetchReport = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`./api/report/monthly?year=${year}&month=${month}`);

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Failed to fetch report');
      }

      const data = await response.json();
      setReport(data);
    } catch (err) {
      setError(err.message);
      setReport(null);
    } finally {
      setLoading(false);
    }
  };

  const formatCurrency = (value) => {
    if (value === null || value === undefined) return '-';
    return new Intl.NumberFormat('sv-SE', {
      style: 'currency',
      currency: 'SEK',
      minimumFractionDigits: 2,
    }).format(value);
  };

  const formatNumber = (value, decimals = 2) => {
    if (value === null || value === undefined) return '-';
    return new Intl.NumberFormat('sv-SE', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    }).format(value);
  };

  const formatTime = (isoString) => {
    const date = new Date(isoString);
    return date.toLocaleString('sv-SE', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <div className="monthly-report">
      {/* Page Header with Title and Month Picker */}
      <div className="page-header">
        <div className="page-header-left">
          <h1 className="page-title">Månadsrapport</h1>
          <p className="page-subtitle">Förbrukning och kostnadsöversikt</p>
        </div>
        <div className="page-header-right">
          <MonthPicker
            year={year}
            month={month}
            onYearChange={setYear}
            onMonthChange={setMonth}
          />
          {loading && (
            <div className="loading-indicator">
              <div className="loading-spinner"></div>
            </div>
          )}
        </div>
      </div>

      {/* Main Report Content */}
      <div className={`report-content ${loading && report ? 'loading-overlay' : ''}`}>
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

        {report && (
          <>
            {/* Invoice Card */}
            <div className="invoice-card">
              <div className="invoice-header">
                <h3>Kostnadsöversikt</h3>
                <span className="invoice-period">
                  {MONTHS[report.period.month - 1]} {report.period.year}
                </span>
              </div>

              <div className="invoice-body">
                <table className="invoice-table">
                  <thead>
                    <tr>
                      <th></th>
                      <th className="col-total">Totalt</th>
                      <th className="col-gardshus">Gårdshus</th>
                      <th className="col-salong">Salong</th>
                    </tr>
                  </thead>
                  <tbody>
                    {/* Consumption Row */}
                    <tr className="consumption-row">
                      <td>
                        <span className="row-label">Förbrukning</span>
                        <span className="row-unit">kWh</span>
                      </td>
                      <td className="col-total">{formatNumber(report.total.consumption_kwh, 2)} <span className="cell-unit">kWh</span></td>
                      <td className="col-gardshus">{formatNumber(report.areas.gardshus.consumption_kwh, 2)} <span className="cell-unit">kWh</span></td>
                      <td className="col-salong">{formatNumber(report.areas.salong.consumption_kwh, 2)} <span className="cell-unit">kWh</span></td>
                    </tr>

                    {/* TIBBER SECTION */}
                    <tr className="section-divider">
                      <td colSpan="4">
                        <div className="section-label">
                          <span className="provider-badge tibber">Tibber</span>
                          <span className="provider-type">El-leverantör</span>
                        </div>
                      </td>
                    </tr>
                    <tr>
                      <td>
                        Spotpris
                        {report.average_spot_ore_per_kwh && (
                          <span className="row-detail">
                            {report.average_spot_ore_per_kwh.toLocaleString('sv-SE', { minimumFractionDigits: 1, maximumFractionDigits: 1 })} öre/kWh i {MONTHS[month-1].toLowerCase()}
                          </span>
                        )}
                      </td>
                      <td className="col-total">{formatCurrency(report.total.tibber.spot_ex_moms)}</td>
                      <td className="col-gardshus">{formatCurrency(report.total.areas_spot_markup?.gardshus?.spot_ex_moms)}</td>
                      <td className="col-salong">{formatCurrency(report.total.areas_spot_markup?.salong?.spot_ex_moms)}</td>
                    </tr>
                    <tr>
                      <td>
                        Påslag Tibber
                        {report.tibber_markup_per_kwh_ex_moms && (
                          <span className="row-detail">
                            {Math.round(report.tibber_markup_per_kwh_ex_moms * 1000) / 10} öre/kWh
                          </span>
                        )}
                      </td>
                      <td className="col-total">{formatCurrency(report.total.tibber.markup_ex_moms)}</td>
                      <td className="col-gardshus">{formatCurrency(report.total.areas_spot_markup?.gardshus?.markup_ex_moms)}</td>
                      <td className="col-salong">{formatCurrency(report.total.areas_spot_markup?.salong?.markup_ex_moms)}</td>
                    </tr>
                    <tr>
                      <td>
                        Abonnemang
                        <span className="row-detail">{formatCurrency(report.total.tibber.abonnemang_ex_moms)}/mån</span>
                      </td>
                      <td className="col-total">{formatCurrency(report.total.tibber.abonnemang_ex_moms)}</td>
                      <td className="col-gardshus muted">-</td>
                      <td className="col-salong muted">-</td>
                    </tr>
                    <tr className="subtotal-row">
                      <td>Summa ex. moms</td>
                      <td className="col-total">{formatCurrency(report.total.tibber.subtotal_ex_moms)}</td>
                      <td className="col-gardshus">{formatCurrency(report.areas.gardshus.tibber.subtotal_ex_moms)}</td>
                      <td className="col-salong">{formatCurrency(report.areas.salong.tibber.subtotal_ex_moms)}</td>
                    </tr>
                    <tr>
                      <td>Moms 25%</td>
                      <td className="col-total">{formatCurrency(report.total.tibber.moms)}</td>
                      <td className="col-gardshus">{formatCurrency(report.areas.gardshus.tibber.moms)}</td>
                      <td className="col-salong">{formatCurrency(report.areas.salong.tibber.moms)}</td>
                    </tr>
                    <tr className="section-total">
                      <td><strong>Tibber inkl. moms</strong></td>
                      <td className="col-total"><strong>{formatCurrency(report.total.tibber.total_inkl_moms)}</strong></td>
                      <td className="col-gardshus"><strong>{formatCurrency(report.areas.gardshus.tibber.total_inkl_moms)}</strong></td>
                      <td className="col-salong"><strong>{formatCurrency(report.areas.salong.tibber.total_inkl_moms)}</strong></td>
                    </tr>

                    {/* E.ON SECTION */}
                    <tr className="section-divider">
                      <td colSpan="4">
                        <div className="section-label">
                          <span className="provider-badge eon">E.ON</span>
                          <span className="provider-type">Nätägare</span>
                        </div>
                      </td>
                    </tr>
                    <tr>
                      <td>
                        Överföringsavgift
                        <span className="row-unit">kWh</span>
                        {report.eon_rates?.overforingsavgift_per_kwh && (
                          <span className="row-detail">
                            {(report.eon_rates.overforingsavgift_per_kwh * 100).toLocaleString('sv-SE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} öre/kWh
                          </span>
                        )}
                      </td>
                      <td className="col-total">{formatCurrency(report.total.eon.overforingsavgift_ex_moms)}</td>
                      <td className="col-gardshus">{formatCurrency(report.areas.gardshus.eon.overforingsavgift_ex_moms)}</td>
                      <td className="col-salong">{formatCurrency(report.areas.salong.eon.overforingsavgift_ex_moms)}</td>
                    </tr>
                    <tr>
                      <td>
                        Energiskatt
                        <span className="row-unit">kWh</span>
                        {report.eon_rates?.energiskatt_per_kwh && (
                          <span className="row-detail">
                            {(report.eon_rates.energiskatt_per_kwh * 100).toLocaleString('sv-SE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} öre/kWh
                          </span>
                        )}
                      </td>
                      <td className="col-total">{formatCurrency(report.total.eon.energiskatt_ex_moms)}</td>
                      <td className="col-gardshus">{formatCurrency(report.areas.gardshus.eon.energiskatt_ex_moms)}</td>
                      <td className="col-salong">{formatCurrency(report.areas.salong.eon.energiskatt_ex_moms)}</td>
                    </tr>
                    <tr>
                      <td>
                        Elnätsabonnemang
                        {report.eon_rates?.abonnemang_ex_moms && (
                          <span className="row-detail">
                            {formatCurrency(report.eon_rates.abonnemang_ex_moms)} kr/mån
                          </span>
                        )}
                      </td>
                      <td className="col-total">{formatCurrency(report.total.eon.abonnemang_ex_moms)}</td>
                      <td className="col-gardshus">
                        {report.areas.gardshus.eon.abonnemang_bidrag_ex_moms > 0 ? (
                          <span className="contribution">
                            {formatCurrency(report.areas.gardshus.eon.abonnemang_bidrag_ex_moms)}
                            <span className="contribution-label">bidrag</span>
                          </span>
                        ) : (
                          <span className="muted">-</span>
                        )}
                      </td>
                      <td className="col-salong muted">-</td>
                    </tr>
                    <tr className="subtotal-row">
                      <td>Summa ex. moms</td>
                      <td className="col-total">{formatCurrency(report.total.eon.subtotal_ex_moms)}</td>
                      <td className="col-gardshus">{formatCurrency(report.areas.gardshus.eon.subtotal_ex_moms)}</td>
                      <td className="col-salong">{formatCurrency(report.areas.salong.eon.subtotal_ex_moms)}</td>
                    </tr>
                    <tr>
                      <td>Moms 25%</td>
                      <td className="col-total">{formatCurrency(report.total.eon.moms)}</td>
                      <td className="col-gardshus">{formatCurrency(report.areas.gardshus.eon.moms)}</td>
                      <td className="col-salong">{formatCurrency(report.areas.salong.eon.moms)}</td>
                    </tr>
                    <tr className="section-total">
                      <td><strong>E.ON inkl. moms</strong></td>
                      <td className="col-total"><strong>{formatCurrency(report.total.eon.total_inkl_moms)}</strong></td>
                      <td className="col-gardshus"><strong>{formatCurrency(report.areas.gardshus.eon.total_inkl_moms)}</strong></td>
                      <td className="col-salong"><strong>{formatCurrency(report.areas.salong.eon.total_inkl_moms)}</strong></td>
                    </tr>
                  </tbody>
                  <tfoot>
                    <tr className="grand-total">
                      <td><strong>TOTALT INKL. MOMS</strong></td>
                      <td className="col-total"><strong>{formatCurrency((report.total.tibber.total_inkl_moms || 0) + (report.total.eon.total_inkl_moms || 0))}</strong></td>
                      <td className="col-gardshus"><strong>{formatCurrency(report.areas.gardshus.total_inkl_moms)}</strong></td>
                      <td className="col-salong"><strong>{formatCurrency(report.areas.salong.total_inkl_moms)}</strong></td>
                    </tr>
                  </tfoot>
                </table>
              </div>

              {report.average_price_sek_kwh && (
                <div className="invoice-footer">
                  <span className="avg-price-label">Genomsnittligt elpris:</span>
                  <span className="avg-price-value">{formatNumber(report.average_price_sek_kwh, 2)} SEK/kWh</span>
                </div>
              )}
            </div>

            {/* Hourly Data Card */}
            {report.hourly_data && report.hourly_data.length > 0 && (
              <div className="hourly-card">
                <div className="hourly-header">
                  <h4>Timvis förbrukning</h4>
                  <span className="record-count">{report.hourly_data.length} timmar</span>
                </div>

                <div className="hourly-table-wrapper">
                  <table className="hourly-table">
                    <thead>
                      <tr>
                        <th className="col-time">Tid</th>
                        <th className="col-gardshus">Gårdshus (kWh)</th>
                        <th className="col-salong">Salong (kWh)</th>
                        <th className="col-price">Pris (SEK/kWh)</th>
                        <th className="col-cost">Gårdshus (SEK)</th>
                        <th className="col-cost">Salong (SEK)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {report.hourly_data.map((row, index) => (
                        <tr key={index} className={row.estimated ? 'estimated-row' : ''}>
                          <td className="col-time">{formatTime(row.time)}{row.estimated && <span className="estimated-badge">est</span>}</td>
                          <td className="col-gardshus">{row.gardshus_kwh !== undefined && row.gardshus_kwh !== null ? `${formatNumber(row.gardshus_kwh, 2)} ` : ''}<span className="cell-unit">kWh</span></td>
                          <td className="col-salong">{row.salong_kwh !== undefined && row.salong_kwh !== null ? `${formatNumber(row.salong_kwh, 2)} ` : ''}<span className="cell-unit">kWh</span></td>
                          <td className="col-price">{row.price_sek !== undefined && row.price_sek !== null ? `${formatNumber(row.price_sek, 2)} ` : ''}<span className="cell-unit">SEK/kWh</span></td>
                          <td className="col-cost">{formatCurrency(row.gardshus_cost)}</td>
                          <td className="col-cost">{formatCurrency(row.salong_cost)}</td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr className="summary-row">
                        <td><strong>Totalt</strong></td>
                        <td className="col-gardshus"><strong>{formatNumber(report.areas.gardshus.consumption_kwh, 2)} <span className="cell-unit">kWh</span></strong></td>
                        <td className="col-salong"><strong>{formatNumber(report.areas.salong.consumption_kwh, 2)} <span className="cell-unit">kWh</span></strong></td>
                        <td className="col-price"><strong>{formatNumber(report.average_price_sek_kwh, 2)} <span className="cell-unit">SEK/kWh</span></strong></td>
                        <td className="col-cost"><strong>{formatCurrency(report.areas.gardshus.el_cost_inkl_moms)}</strong></td>
                        <td className="col-cost"><strong>{formatCurrency(report.areas.salong.el_cost_inkl_moms)}</strong></td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              </div>
            )}
          </>
        )}

        {!report && !loading && !error && (
          <div className="empty-state">
            <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
              <polyline points="14 2 14 8 20 8"/>
              <line x1="16" y1="13" x2="8" y2="13"/>
              <line x1="16" y1="17" x2="8" y2="17"/>
            </svg>
            <p>Välj en månad för att visa rapporten</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default MonthlyReport;
