import { jsPDF } from 'jspdf';

// Refined palette — mostly neutral with teal as a quiet accent
const INK = [23, 23, 23];          // near-black for primary text
const DARK = [51, 65, 85];         // slate-700 for secondary text
const MUTED = [148, 163, 184];     // slate-400 for labels
const RULE = [203, 213, 225];      // slate-300 for lines
const FAINT = [241, 245, 249];     // slate-100 for subtle fills
const ACCENT = [15, 118, 110];     // teal-700 — dark, classy teal
const WHITE = [255, 255, 255];

function setColor(doc, rgb) { doc.setTextColor(...rgb); }
function setFill(doc, rgb) { doc.setFillColor(...rgb); }
function setDraw(doc, rgb) { doc.setDrawColor(...rgb); }

export function generateInvoicePdf({ invoiceData, settings, invoiceNumber, invoiceDate, dueDate }) {
  const doc = new jsPDF({ unit: 'mm', format: 'a4' });
  const pw = 210;
  const lm = 22;
  const re = pw - 22;
  const cw = re - lm;

  // ── Thin accent line at top ──
  setFill(doc, ACCENT);
  doc.rect(0, 0, pw, 1.5, 'F');

  // ================================================================
  //  HEADER
  // ================================================================
  let y = 20;

  // "FAKTURA" — large, dark, right-aligned
  doc.setFont('helvetica', 'bold');
  doc.setFontSize(26);
  setColor(doc, INK);
  doc.text('FAKTURA', re, y, { align: 'right' });

  // Recipient company — left
  const r = settings.recipient;
  doc.setFontSize(13);
  doc.setFont('helvetica', 'bold');
  setColor(doc, INK);
  doc.text(r.company || '', lm, y);

  // Recipient details
  doc.setFont('helvetica', 'normal');
  doc.setFontSize(9);
  setColor(doc, DARK);
  if (r.street) { y += 5.5; doc.text(r.street, lm, y); }
  if (r.postal_city) { y += 4.5; doc.text(r.postal_city, lm, y); }
  if (r.org_number) { y += 4.5; doc.text(`Org.nr ${r.org_number}`, lm, y); }

  // ── Invoice meta — right side, below FAKTURA ──
  y = 30;
  const metaValX = re;       // right-aligned values
  const metaLabelX = re - 58; // left-aligned labels

  doc.setFontSize(7.5);
  doc.setFont('helvetica', 'normal');
  setColor(doc, MUTED);
  doc.text('Fakturanummer', metaLabelX, y);
  doc.text('Fakturadatum', metaLabelX, y + 7);
  doc.text('F\u00F6rfallodatum', metaLabelX, y + 14);

  doc.setFontSize(9);
  doc.setFont('helvetica', 'normal');
  setColor(doc, INK);
  doc.text(String(invoiceNumber), metaValX, y, { align: 'right' });
  doc.text(invoiceDate, metaValX, y + 7, { align: 'right' });
  doc.text(dueDate, metaValX, y + 14, { align: 'right' });

  // Light underline below meta
  setDraw(doc, RULE);
  doc.setLineWidth(0.25);
  doc.line(metaLabelX, y + 18, re, y + 18);

  // ================================================================
  //  SENDER
  // ================================================================
  y = 56;
  doc.setFontSize(7);
  doc.setFont('helvetica', 'bold');
  setColor(doc, MUTED);
  doc.text('FR\u00C5N', lm, y);

  y += 5;
  const s = settings.sender;
  doc.setFontSize(9.5);
  doc.setFont('helvetica', 'normal');
  setColor(doc, INK);
  if (s.name) { doc.text(s.name, lm, y); y += 4.5; }
  doc.setFontSize(9);
  setColor(doc, DARK);
  if (s.street) { doc.text(s.street, lm, y); y += 4.5; }
  if (s.postal_city) { doc.text(s.postal_city, lm, y); y += 4.5; }
  setColor(doc, MUTED);
  doc.setFontSize(8.5);
  if (s.phone) { doc.text(s.phone, lm, y); y += 4; }
  if (s.email) { doc.text(s.email, lm, y); }

  // ================================================================
  //  LINE ITEMS
  // ================================================================
  y = 96;

  // Section title
  doc.setFontSize(11);
  doc.setFont('helvetica', 'bold');
  setColor(doc, INK);
  doc.text(`Elkostnad f\u00F6r ${invoiceData.area_name}`, lm, y);
  y += 10;

  // Column positions — right-aligned numeric columns
  const colPeriod = lm + 2;
  const colReading = lm + 80;
  const colConsumption = lm + 108;
  const colPrice = lm + 136;
  const colAmount = re - 2;

  // Table header — just text on a subtle background
  setFill(doc, FAINT);
  doc.rect(lm, y - 4.5, cw, 7, 'F');

  doc.setFontSize(7);
  doc.setFont('helvetica', 'bold');
  setColor(doc, MUTED);
  doc.text('PERIOD', colPeriod, y);
  doc.text('AVL\u00C4ST', colReading, y, { align: 'right' });
  doc.text('F\u00D6RBRUKNING', colConsumption, y, { align: 'right' });
  doc.text('KR/KWH', colPrice, y, { align: 'right' });
  doc.text('BELOPP', colAmount, y, { align: 'right' });

  // Header bottom line
  setDraw(doc, RULE);
  doc.setLineWidth(0.3);
  doc.line(lm, y + 3, re, y + 3);
  y += 9;

  // Rows
  let rowIndex = 0;
  for (const month of invoiceData.invoice_months) {
    if (month.consumption_kwh === null) continue;

    if (y > 250) {
      doc.addPage();
      setFill(doc, ACCENT);
      doc.rect(0, 0, pw, 1.5, 'F');
      y = 20;
    }

    // Subtle alternating background
    if (rowIndex % 2 === 1) {
      setFill(doc, [248, 250, 252]);
      doc.rect(lm, y - 4, cw, 8.5, 'F');
    }

    doc.setFontSize(8.5);
    doc.setFont('helvetica', 'normal');
    setColor(doc, DARK);
    doc.text(`${month.period_start}  \u2013  ${month.period_end}`, colPeriod, y);

    setColor(doc, INK);
    doc.text(formatNum(month.meter_reading_kwh, 1), colReading, y, { align: 'right' });
    doc.text(`${formatNum(month.consumption_kwh, 1)} kWh`, colConsumption, y, { align: 'right' });
    doc.text(formatNum(month.cost_per_kwh, 2), colPrice, y, { align: 'right' });

    doc.setFont('helvetica', 'bold');
    doc.text(`${formatCurrency(month.total_cost_sek)} kr`, colAmount, y, { align: 'right' });

    // Row separator
    setDraw(doc, [237, 242, 247]);
    doc.setLineWidth(0.15);
    doc.line(lm, y + 4.5, re, y + 4.5);

    y += 8.5;
    rowIndex++;
  }

  // ── Totals row ──
  y += 2;
  setDraw(doc, INK);
  doc.setLineWidth(0.4);
  doc.line(lm, y - 2, re, y - 2);

  y += 4;
  doc.setFontSize(8);
  doc.setFont('helvetica', 'bold');
  setColor(doc, MUTED);
  doc.text('TOTALT', colPeriod, y);

  doc.setFontSize(8.5);
  doc.setFont('helvetica', 'normal');
  setColor(doc, DARK);
  doc.text(`${formatNum(invoiceData.grand_total.total_consumption_kwh, 1)} kWh`, colConsumption, y, { align: 'right' });

  doc.setFontSize(11);
  doc.setFont('helvetica', 'bold');
  setColor(doc, INK);
  doc.text(`${formatCurrency(invoiceData.grand_total.total_cost_sek)} kr`, colAmount, y + 0.5, { align: 'right' });

  // ================================================================
  //  FOOTER
  // ================================================================
  const footerY = Math.max(y + 30, 258);

  setDraw(doc, RULE);
  doc.setLineWidth(0.25);
  doc.line(lm, footerY, re, footerY);

  // Left: payment info
  y = footerY + 6;
  doc.setFontSize(7);
  doc.setFont('helvetica', 'bold');
  setColor(doc, MUTED);
  doc.text('BETALNINGSINFORMATION', lm, y);

  y += 5;
  doc.setFontSize(8.5);
  doc.setFont('helvetica', 'normal');
  setColor(doc, DARK);
  if (settings.bank_account) {
    doc.text(`Bankkonto:  ${settings.bank_account}`, lm, y);
    y += 4.5;
  }
  doc.text(`F\u00F6rfallodatum:  ${dueDate}`, lm, y);

  // Right: amount due — subtle box
  const boxW = 52;
  const boxH = 18;
  const boxX = re - boxW;
  const boxY = footerY + 3;

  setFill(doc, ACCENT);
  doc.roundedRect(boxX, boxY, boxW, boxH, 2, 2, 'F');

  doc.setFontSize(7);
  doc.setFont('helvetica', 'normal');
  setColor(doc, [255, 255, 255]);
  doc.text('Att betala', boxX + 4, boxY + 5.5);

  doc.setFontSize(14);
  doc.setFont('helvetica', 'bold');
  doc.text(
    `${formatCurrency(invoiceData.grand_total.total_cost_sek)} kr`,
    boxX + boxW - 4, boxY + 13.5, { align: 'right' }
  );

  // ── Small footer note ──
  doc.setFontSize(6.5);
  doc.setFont('helvetica', 'normal');
  setColor(doc, MUTED);
  doc.text('Genererad av HomeAnalytics', pw / 2, 290, { align: 'center' });

  doc.save(`faktura-${invoiceNumber}.pdf`);
}

function formatNum(val, decimals) {
  if (val === null || val === undefined) return '-';
  return val.toLocaleString('sv-SE', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function formatCurrency(val) {
  if (val === null || val === undefined) return '-';
  return val.toLocaleString('sv-SE', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}
