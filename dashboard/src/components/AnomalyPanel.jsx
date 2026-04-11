import { useState, useEffect } from 'react'
import { fetchAnomalyConfig, updateAnomalyConfig } from '../api'

function Toggle({ checked, onChange, disabled }) {
  return (
    <button
      onClick={() => !disabled && onChange(!checked)}
      className={`relative inline-flex h-5 w-9 flex-shrink-0 rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none ${
        checked ? 'bg-blue-600' : 'bg-gray-700'
      } ${disabled ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer'}`}
    >
      <span
        className={`pointer-events-none inline-block h-4 w-4 rounded-full bg-white shadow transform transition-transform duration-200 ${
          checked ? 'translate-x-4' : 'translate-x-0'
        }`}
      />
    </button>
  )
}

function NumberField({ label, value, onChange, min = 1, max, hint }) {
  return (
    <div className="flex items-center justify-between py-2">
      <div>
        <span className="text-sm text-gray-300">{label}</span>
        {hint && <p className="text-xs text-gray-600 mt-0.5">{hint}</p>}
      </div>
      <input
        type="number"
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-20 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-sm text-gray-100 mono text-right focus:outline-none focus:border-blue-500"
      />
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
      <div className="px-4 py-2.5 border-b border-gray-800 bg-gray-900">
        <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">{title}</span>
      </div>
      <div className="px-4 py-1 divide-y divide-gray-800">
        {children}
      </div>
    </div>
  )
}

function Row({ label, hint, children }) {
  return (
    <div className="flex items-center justify-between py-3">
      <div>
        <span className="text-sm text-gray-300">{label}</span>
        {hint && <p className="text-xs text-gray-600 mt-0.5">{hint}</p>}
      </div>
      {children}
    </div>
  )
}

export default function AnomalyPanel() {
  const [cfg, setCfg] = useState(null)
  const [draft, setDraft] = useState(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetchAnomalyConfig()
      .then((data) => { setCfg(data); setDraft(data) })
      .catch((e) => setError(e.message))
  }, [])

  const isDirty = draft && cfg && JSON.stringify(draft) !== JSON.stringify(cfg)

  const set = (path, value) => {
    setDraft((prev) => {
      const next = JSON.parse(JSON.stringify(prev))
      const keys = path.split('.')
      let obj = next
      for (let i = 0; i < keys.length - 1; i++) obj = obj[keys[i]]
      obj[keys[keys.length - 1]] = value
      return next
    })
  }

  const handleSave = async () => {
    setSaving(true)
    setError(null)
    try {
      const updated = await updateAnomalyConfig(draft)
      setCfg(updated)
      setDraft(updated)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  const handleReset = () => setDraft(JSON.parse(JSON.stringify(cfg)))

  if (error && !draft) return (
    <div className="flex items-center justify-center h-full text-red-500 text-sm">{error}</div>
  )
  if (!draft) return (
    <div className="flex items-center justify-center h-full text-gray-600 text-sm">Loading…</div>
  )

  const offHoursLabel = (() => {
    const { start_hour, end_hour } = draft.off_hours
    const fmt = (h) => `${String(h).padStart(2, '0')}:00`
    if (start_hour === end_hour) return 'disabled (start = end)'
    if (start_hour < end_hour) return `${fmt(start_hour)} – ${fmt(end_hour)}`
    return `${fmt(start_hour)} – ${fmt(end_hour)} (wraps midnight)`
  })()

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-6 py-4 bg-gray-900 border-b border-gray-800 flex-shrink-0">
        <div>
          <h2 className="text-sm font-semibold text-gray-200">Anomaly Detection</h2>
          <p className="text-xs text-gray-500 mt-0.5">Changes apply immediately — reset on proxy restart</p>
        </div>
        <div className="flex items-center gap-3">
          {error && (
            <span className="text-xs text-red-400">{error}</span>
          )}
          {saved && (
            <span className="text-xs text-green-400">Saved</span>
          )}
          <button
            onClick={handleReset}
            disabled={!isDirty || saving}
            className="text-xs text-gray-500 hover:text-gray-300 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Reset
          </button>
          <button
            onClick={handleSave}
            disabled={!isDirty || saving}
            className="px-3 py-1.5 text-xs font-medium rounded bg-blue-600 hover:bg-blue-500 text-white disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-5 space-y-4 max-w-2xl">
        {/* Master toggle */}
        <Section title="General">
          <Row label="Enabled" hint="Master switch for all anomaly detection">
            <Toggle checked={draft.enabled} onChange={(v) => set('enabled', v)} />
          </Row>
        </Section>

        {/* Frequency */}
        <Section title="Call Frequency">
          <Row label="Enabled" hint="Detects abnormally high tool call rates (global, session-independent)">
            <Toggle
              checked={draft.frequency.enabled}
              onChange={(v) => set('frequency.enabled', v)}
              disabled={!draft.enabled}
            />
          </Row>
          <NumberField
            label="Max calls / minute"
            value={draft.frequency.max_per_minute}
            onChange={(v) => set('frequency.max_per_minute', v)}
            min={1}
            hint="Triggers high_frequency flag when exceeded"
          />
          <NumberField
            label="Max calls / hour"
            value={draft.frequency.max_per_hour}
            onChange={(v) => set('frequency.max_per_hour', v)}
            min={1}
          />
        </Section>

        {/* Off-hours */}
        <Section title="Off-Hours Access">
          <Row label="Enabled" hint="Flags tool calls made during configured quiet hours">
            <Toggle
              checked={draft.off_hours.enabled}
              onChange={(v) => set('off_hours.enabled', v)}
              disabled={!draft.enabled}
            />
          </Row>
          <NumberField
            label="Start hour (0–23)"
            value={draft.off_hours.start_hour}
            onChange={(v) => set('off_hours.start_hour', Math.min(23, Math.max(0, v)))}
            min={0}
            max={23}
            hint="Inclusive, UTC"
          />
          <NumberField
            label="End hour (0–23)"
            value={draft.off_hours.end_hour}
            onChange={(v) => set('off_hours.end_hour', Math.min(23, Math.max(0, v)))}
            min={0}
            max={23}
            hint="Exclusive, UTC"
          />
          <div className="py-2">
            <p className="text-xs text-gray-500">
              Active window: <span className="mono text-gray-300">{offHoursLabel}</span>
            </p>
          </div>
        </Section>

        {/* Enforcement modes note */}
        <div className="bg-gray-900 border border-gray-800 rounded-lg px-4 py-3">
          <p className="text-xs text-gray-500 leading-relaxed">
            Enforcement modes for <span className="mono text-gray-400">high_frequency</span> and{' '}
            <span className="mono text-gray-400">off_hours_access</span> flags are managed in the{' '}
            <span className="text-blue-400 cursor-pointer">Rules</span> panel.
          </p>
        </div>
      </div>
    </div>
  )
}
