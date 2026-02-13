import { useState, useEffect } from 'react';
import { generateInvoicePdf } from './generateInvoicePdf';
import './InvoicePdfForm.css';

function todayISO() {
  return new Date().toISOString().slice(0, 10);
}

function dueDateISO(days) {
  const d = new Date();
  d.setDate(d.getDate() + days);
  return d.toISOString().slice(0, 10);
}

function InvoicePdfForm({ invoiceData }) {
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [invoiceDate, setInvoiceDate] = useState(todayISO());
  const [dueDate, setDueDate] = useState(dueDateISO(15));
  const [generating, setGenerating] = useState(false);

  useEffect(() => {
    fetch('./api/invoice/settings')
      .then(r => r.json())
      .then(data => {
        setSettings(data);
        setDueDate(dueDateISO(data.due_days || 15));
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const updateField = (section, field, value) => {
    if (field === null) {
      // Top-level field
      setSettings(prev => ({ ...prev, [section]: value }));
    } else {
      setSettings(prev => ({
        ...prev,
        [section]: { ...prev[section], [field]: value },
      }));
    }
  };

  const handleSaveSettings = async () => {
    const res = await fetch('./api/invoice/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    });
    if (!res.ok) {
      alert('Kunde inte spara inställningar');
    }
  };

  const handleGeneratePdf = async () => {
    setGenerating(true);
    try {
      // Save current settings
      const saveRes = await fetch('./api/invoice/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings),
      });
      if (!saveRes.ok) {
        throw new Error('Kunde inte spara inställningar');
      }

      // Increment invoice number atomically
      const res = await fetch('./api/invoice/settings/increment-number', { method: 'POST' });
      if (!res.ok) {
        throw new Error('Kunde inte hämta fakturanummer');
      }
      const { used_number } = await res.json();

      // Generate PDF
      generateInvoicePdf({
        invoiceData,
        settings,
        invoiceNumber: used_number,
        invoiceDate,
        dueDate,
      });

      // Update local state
      setSettings(prev => ({
        ...prev,
        next_invoice_number: used_number + 1,
      }));
    } catch (error) {
      alert(`Fel vid PDF-generering: ${error.message}`);
    } finally {
      setGenerating(false);
    }
  };

  if (loading || !settings) return null;

  return (
    <div className="pdf-form-card">
      <h3 className="pdf-form-title">PDF-faktura</h3>

      <div className="pdf-form-grid">
        {/* Recipient */}
        <fieldset className="pdf-fieldset">
          <legend>Mottagare</legend>
          <label>
            <span>Företag</span>
            <input
              value={settings.recipient.company}
              onChange={e => updateField('recipient', 'company', e.target.value)}
              maxLength={100}
            />
          </label>
          <label>
            <span>Adress</span>
            <input
              value={settings.recipient.street}
              onChange={e => updateField('recipient', 'street', e.target.value)}
              maxLength={100}
            />
          </label>
          <label>
            <span>Postnr + Ort</span>
            <input
              value={settings.recipient.postal_city}
              onChange={e => updateField('recipient', 'postal_city', e.target.value)}
              maxLength={50}
            />
          </label>
          <label>
            <span>Org.nr</span>
            <input
              value={settings.recipient.org_number}
              onChange={e => updateField('recipient', 'org_number', e.target.value)}
              maxLength={20}
            />
          </label>
        </fieldset>

        {/* Sender */}
        <fieldset className="pdf-fieldset">
          <legend>Avsändare</legend>
          <label>
            <span>Namn</span>
            <input
              value={settings.sender.name}
              onChange={e => updateField('sender', 'name', e.target.value)}
              maxLength={100}
            />
          </label>
          <label>
            <span>Adress</span>
            <input
              value={settings.sender.street}
              onChange={e => updateField('sender', 'street', e.target.value)}
              maxLength={100}
            />
          </label>
          <label>
            <span>Postnr + Ort</span>
            <input
              value={settings.sender.postal_city}
              onChange={e => updateField('sender', 'postal_city', e.target.value)}
              maxLength={50}
            />
          </label>
          <label>
            <span>Telefon</span>
            <input
              value={settings.sender.phone}
              onChange={e => updateField('sender', 'phone', e.target.value)}
              maxLength={20}
            />
          </label>
          <label>
            <span>E-post</span>
            <input
              value={settings.sender.email}
              onChange={e => updateField('sender', 'email', e.target.value)}
              maxLength={100}
            />
          </label>
        </fieldset>

        {/* Invoice details */}
        <fieldset className="pdf-fieldset">
          <legend>Fakturadetaljer</legend>
          <label>
            <span>Nästa fakturanr</span>
            <input
              type="number"
              value={settings.next_invoice_number}
              onChange={e => updateField('next_invoice_number', null, Number(e.target.value))}
            />
          </label>
          <label>
            <span>Fakturadatum</span>
            <input
              type="date"
              value={invoiceDate}
              onChange={e => setInvoiceDate(e.target.value)}
            />
          </label>
          <label>
            <span>Förfallodatum</span>
            <input
              type="date"
              value={dueDate}
              onChange={e => setDueDate(e.target.value)}
            />
          </label>
          <label>
            <span>Bankkonto</span>
            <input
              value={settings.bank_account}
              onChange={e => updateField('bank_account', null, e.target.value)}
              maxLength={50}
            />
          </label>
        </fieldset>
      </div>

      <div className="pdf-form-actions">
        <button className="btn btn-secondary" onClick={handleSaveSettings}>
          Spara inställningar
        </button>
        <button
          className="btn btn-primary"
          onClick={handleGeneratePdf}
          disabled={generating}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
            <polyline points="7 10 12 15 17 10"/>
            <line x1="12" y1="15" x2="12" y2="3"/>
          </svg>
          {generating ? 'Genererar...' : 'Skapa PDF'}
        </button>
      </div>
    </div>
  );
}

export default InvoicePdfForm;
