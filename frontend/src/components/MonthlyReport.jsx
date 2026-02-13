import { useState, useEffect } from 'react';
import MonthPicker from './MonthPicker';
import './MonthlyReport.css';

const MONTHS = [
  'Januari', 'Februari', 'Mars', 'April', 'Maj', 'Juni',
  'Juli', 'Augusti', 'September', 'Oktober', 'November', 'December'
];

const DEFAULT_AREA_ORDER = ['gardshus', 'salong', 'billaddning', 'varmepump', 'ovrigt'];
const DEFAULT_AREA_NAMES = {
  gardshus: 'Gårdshus',
  salong: 'Salong',
  billaddning: 'Billaddning',
  varmepump: 'Värmepump',
  ovrigt: 'Övrigt',
};

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
        let errorMessage = 'Failed to fetch report';
        try {
          const errorData = await response.json();
          errorMessage = errorData.detail || errorMessage;
        } catch { /* server didn't return JSON */ }
        throw new Error(errorMessage);
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

  // Derive area order and names from the report data
  const areaOrder = report?.area_order || DEFAULT_AREA_ORDER;
  const areaNames = report?.area_names || DEFAULT_AREA_NAMES;
  const areaDataQuality = report?.area_data_quality || {};
  const colSpanAll = 2 + areaOrder.length; // label + total + areas

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
            {report.is_current_month && (
              <div className="current-month-banner">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10"/>
                  <polyline points="12 6 12 12 16 14"/>
                </svg>
                <span>Pågående månad — {(() => {
                  const now = new Date();
                  const daysElapsed = now.getDate();
                  const totalDays = new Date(report.period.year, report.period.month, 0).getDate();
                  const pct = Math.round((daysElapsed / totalDays) * 100);
                  return `${daysElapsed} av ${totalDays} dagar (${pct}%)`;
                })()}</span>
              </div>
            )}

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
                      {areaOrder.map(area => {
                        const quality = areaDataQuality[area];
                        const lowQuality = quality !== undefined && quality < 0.95;
                        return (
                          <th key={area} className={`col-${area}`}>
                            {areaNames[area]}
                            {lowQuality && (
                              <span className="quality-badge" title={`${Math.round(quality * 100)}% originaldata — resten interpolerad p.g.a. felaktiga mätvärden`}>~</span>
                            )}
                          </th>
                        );
                      })}
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
                      {areaOrder.map(area => (
                        <td key={area} className={`col-${area}`}>
                          {report.areas[area] ? (
                            <>{formatNumber(report.areas[area].consumption_kwh, 2)} <span className="cell-unit">kWh</span></>
                          ) : '-'}
                        </td>
                      ))}
                    </tr>

                    {/* TIBBER SECTION */}
                    <tr className="section-divider">
                      <td colSpan={colSpanAll}>
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
                      {areaOrder.map(area => (
                        <td key={area} className={`col-${area}`}>
                          {formatCurrency(report.total.areas_spot_markup?.[area]?.spot_ex_moms)}
                        </td>
                      ))}
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
                      {areaOrder.map(area => (
                        <td key={area} className={`col-${area}`}>
                          {formatCurrency(report.total.areas_spot_markup?.[area]?.markup_ex_moms)}
                        </td>
                      ))}
                    </tr>
                    <tr>
                      <td>
                        Abonnemang
                        <span className="row-detail">{formatCurrency(report.total.tibber.abonnemang_ex_moms)}/mån</span>
                      </td>
                      <td className="col-total">{formatCurrency(report.total.tibber.abonnemang_ex_moms)}</td>
                      {areaOrder.map(area => (
                        <td key={area} className={`col-${area} muted`}>-</td>
                      ))}
                    </tr>
                    <tr className="subtotal-row">
                      <td>Summa ex. moms</td>
                      <td className="col-total">{formatCurrency(report.total.tibber.subtotal_ex_moms)}</td>
                      {areaOrder.map(area => (
                        <td key={area} className={`col-${area}`}>
                          {report.areas[area] ? formatCurrency(report.areas[area].tibber.subtotal_ex_moms) : '-'}
                        </td>
                      ))}
                    </tr>
                    <tr>
                      <td>Moms 25%</td>
                      <td className="col-total">{formatCurrency(report.total.tibber.moms)}</td>
                      {areaOrder.map(area => (
                        <td key={area} className={`col-${area}`}>
                          {report.areas[area] ? formatCurrency(report.areas[area].tibber.moms) : '-'}
                        </td>
                      ))}
                    </tr>
                    <tr className="section-total">
                      <td><strong>Tibber inkl. moms</strong></td>
                      <td className="col-total"><strong>{formatCurrency(report.total.tibber.total_inkl_moms)}</strong></td>
                      {areaOrder.map(area => (
                        <td key={area} className={`col-${area}`}>
                          <strong>{report.areas[area] ? formatCurrency(report.areas[area].tibber.total_inkl_moms) : '-'}</strong>
                        </td>
                      ))}
                    </tr>

                    {/* E.ON SECTION */}
                    <tr className="section-divider">
                      <td colSpan={colSpanAll}>
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
                      {areaOrder.map(area => (
                        <td key={area} className={`col-${area}`}>
                          {report.areas[area] ? formatCurrency(report.areas[area].eon.overforingsavgift_ex_moms) : '-'}
                        </td>
                      ))}
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
                      {areaOrder.map(area => (
                        <td key={area} className={`col-${area}`}>
                          {report.areas[area] ? formatCurrency(report.areas[area].eon.energiskatt_ex_moms) : '-'}
                        </td>
                      ))}
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
                      {areaOrder.map(area => {
                        const areaData = report.areas[area];
                        if (!areaData) return <td key={area} className={`col-${area} muted`}>-</td>;
                        return (
                          <td key={area} className={`col-${area}`}>
                            {areaData.eon.abonnemang_bidrag_ex_moms > 0 ? (
                              <span className="contribution">
                                {formatCurrency(areaData.eon.abonnemang_bidrag_ex_moms)}
                                <span className="contribution-label">bidrag</span>
                              </span>
                            ) : (
                              <span className="muted">-</span>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                    <tr className="subtotal-row">
                      <td>Summa ex. moms</td>
                      <td className="col-total">{formatCurrency(report.total.eon.subtotal_ex_moms)}</td>
                      {areaOrder.map(area => (
                        <td key={area} className={`col-${area}`}>
                          {report.areas[area] ? formatCurrency(report.areas[area].eon.subtotal_ex_moms) : '-'}
                        </td>
                      ))}
                    </tr>
                    <tr>
                      <td>Moms 25%</td>
                      <td className="col-total">{formatCurrency(report.total.eon.moms)}</td>
                      {areaOrder.map(area => (
                        <td key={area} className={`col-${area}`}>
                          {report.areas[area] ? formatCurrency(report.areas[area].eon.moms) : '-'}
                        </td>
                      ))}
                    </tr>
                    <tr className="section-total">
                      <td><strong>E.ON inkl. moms</strong></td>
                      <td className="col-total"><strong>{formatCurrency(report.total.eon.total_inkl_moms)}</strong></td>
                      {areaOrder.map(area => (
                        <td key={area} className={`col-${area}`}>
                          <strong>{report.areas[area] ? formatCurrency(report.areas[area].eon.total_inkl_moms) : '-'}</strong>
                        </td>
                      ))}
                    </tr>
                  </tbody>
                  <tfoot>
                    <tr className="grand-total">
                      <td><strong>TOTALT INKL. MOMS</strong></td>
                      <td className="col-total"><strong>{formatCurrency((report.total.tibber.total_inkl_moms || 0) + (report.total.eon.total_inkl_moms || 0))}</strong></td>
                      {areaOrder.map(area => (
                        <td key={area} className={`col-${area}`}>
                          <strong>{report.areas[area] ? formatCurrency(report.areas[area].total_inkl_moms) : '-'}</strong>
                        </td>
                      ))}
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
                        {areaOrder.map(area => {
                          const quality = areaDataQuality[area];
                          const lowQuality = quality !== undefined && quality < 0.95;
                          return (
                            <th key={`${area}-kwh`} className={`col-${area}`}>
                              {areaNames[area]} (kWh)
                              {lowQuality && (
                                <span className="quality-badge" title={`${Math.round(quality * 100)}% originaldata — resten interpolerad p.g.a. felaktiga mätvärden`}>~</span>
                              )}
                            </th>
                          );
                        })}
                        <th className="col-price">Pris (SEK/kWh)</th>
                        {areaOrder.map(area => {
                          const quality = areaDataQuality[area];
                          const lowQuality = quality !== undefined && quality < 0.95;
                          return (
                            <th key={`${area}-cost`} className="col-cost">
                              {areaNames[area]} (SEK)
                              {lowQuality && (
                                <span className="quality-badge" title={`${Math.round(quality * 100)}% originaldata — resten interpolerad p.g.a. felaktiga mätvärden`}>~</span>
                              )}
                            </th>
                          );
                        })}
                      </tr>
                    </thead>
                    <tbody>
                      {report.hourly_data.map((row, index) => {
                        const estAreas = row.estimated_areas || [];
                        return (
                          <tr key={index}>
                            <td className="col-time">{formatTime(row.time)}</td>
                            {areaOrder.map(area => {
                              const isEst = estAreas.includes(area);
                              return (
                                <td key={`${area}-kwh`} className={`col-${area}${isEst ? ' estimated-cell' : ''}`}>
                                  {row[`${area}_kwh`] !== undefined && row[`${area}_kwh`] !== null
                                    ? <>{formatNumber(row[`${area}_kwh`], 2)} <span className="cell-unit">kWh</span>{isEst && <span className="estimated-badge">est</span>}</>
                                    : ''}
                                </td>
                              );
                            })}
                            <td className="col-price">{row.price_sek !== undefined && row.price_sek !== null ? `${formatNumber(row.price_sek, 2)} ` : ''}<span className="cell-unit">SEK/kWh</span></td>
                            {areaOrder.map(area => {
                              const isEst = estAreas.includes(area);
                              return (
                                <td key={`${area}-cost`} className={`col-cost${isEst ? ' estimated-cell' : ''}`}>{formatCurrency(row[`${area}_cost`])}</td>
                              );
                            })}
                          </tr>
                        );
                      })}
                    </tbody>
                    <tfoot>
                      <tr className="summary-row">
                        <td><strong>Totalt</strong></td>
                        {areaOrder.map(area => (
                          <td key={`${area}-kwh`} className={`col-${area}`}>
                            <strong>
                              {report.areas[area]
                                ? <>{formatNumber(report.areas[area].consumption_kwh, 2)} <span className="cell-unit">kWh</span></>
                                : '-'}
                            </strong>
                          </td>
                        ))}
                        <td className="col-price"><strong>{formatNumber(report.average_price_sek_kwh, 2)} <span className="cell-unit">SEK/kWh</span></strong></td>
                        {areaOrder.map(area => (
                          <td key={`${area}-cost`} className="col-cost">
                            <strong>{report.areas[area] ? formatCurrency(report.areas[area].el_cost_inkl_moms) : '-'}</strong>
                          </td>
                        ))}
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
