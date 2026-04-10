import { useState, useEffect, useCallback } from 'react'
import { fetchRules, createRule, updateRule, deleteRule } from '../api'

const MODE_STYLES = {
  block: 'bg-red-900 text-red-300 border border-red-700',
  alert: 'bg-yellow-900 text-yellow-300 border border-yellow-700',
  log:   'bg-blue-900 text-blue-300 border border-blue-800',
}

const FLAG_OPTIONS = [
  'path_traversal',
  'sql_injection',
  'injection_detected',
  'credential_leak',
]

const DEFAULT_NEW_RULE = {
  flag: 'path_traversal',
  mode: 'block',
  redact: false,
  enabled: true,
  name: '',
}

function RuleRow({ rule, onToggle, onDelete }) {
  const modeStyle = MODE_STYLES[rule.mode] ?? 'bg-gray-800 text-gray-400'
  return (
    <div className={`flex items-center gap-3 px-4 py-3 border-b border-gray-800 transition-opacity ${!rule.enabled ? 'opacity-40' : ''}`}>
      {/* Toggle */}
      <button
        onClick={() => onToggle(rule)}
        title={rule.enabled ? 'Disable rule' : 'Enable rule'}
        className={`w-9 h-5 rounded-full transition-colors flex-shrink-0 ${rule.enabled ? 'bg-blue-600' : 'bg-gray-700'}`}
      >
        <span
          className={`block w-3.5 h-3.5 bg-white rounded-full shadow transition-transform mx-0.5 mt-0.5 ${rule.enabled ? 'translate-x-4' : 'translate-x-0'}`}
        />
      </button>

      {/* Flag */}
      <span className="mono text-sm text-gray-300 flex-1">{rule.flag}</span>

      {/* Name */}
      {rule.name && (
        <span className="text-xs text-gray-500 flex-1 truncate">{rule.name}</span>
      )}

      {/* Mode */}
      <span className={`text-xs px-2 py-0.5 rounded font-medium ${modeStyle}`}>
        {rule.mode?.toUpperCase()}
      </span>

      {/* Redact */}
      {rule.redact && (
        <span className="text-xs bg-purple-900 text-purple-300 border border-purple-700 px-2 py-0.5 rounded">
          REDACT
        </span>
      )}

      {/* Delete */}
      <button
        onClick={() => onDelete(rule.id)}
        className="text-gray-600 hover:text-red-400 transition-colors ml-2"
        title="Delete rule"
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" className="w-4 h-4">
          <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
        </svg>
      </button>
    </div>
  )
}

function AddRuleForm({ onAdd, onCancel }) {
  const [form, setForm] = useState(DEFAULT_NEW_RULE)

  const set = (key, val) => setForm((f) => ({ ...f, [key]: val }))

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!form.flag) return
    onAdd(form)
  }

  return (
    <form onSubmit={handleSubmit} className="bg-gray-900 border border-gray-700 rounded-lg p-4 space-y-3">
      <p className="text-sm font-medium text-gray-200">New Rule</p>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-gray-500 mb-1 block">Flag</label>
          <select
            value={form.flag}
            onChange={(e) => set('flag', e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 focus:outline-none focus:border-blue-500"
          >
            {FLAG_OPTIONS.map((f) => (
              <option key={f} value={f}>{f}</option>
            ))}
            <option value="custom">custom…</option>
          </select>
          {form.flag === 'custom' && (
            <input
              type="text"
              placeholder="flag_name"
              onChange={(e) => set('flag', e.target.value)}
              className="mt-1 w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 mono focus:outline-none focus:border-blue-500"
            />
          )}
        </div>

        <div>
          <label className="text-xs text-gray-500 mb-1 block">Mode</label>
          <select
            value={form.mode}
            onChange={(e) => set('mode', e.target.value)}
            className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 focus:outline-none focus:border-blue-500"
          >
            <option value="block">BLOCK</option>
            <option value="alert">ALERT</option>
            <option value="log">LOG</option>
          </select>
        </div>

        <div>
          <label className="text-xs text-gray-500 mb-1 block">Name (optional)</label>
          <input
            type="text"
            value={form.name}
            onChange={(e) => set('name', e.target.value)}
            placeholder="Descriptive name"
            className="w-full bg-gray-800 border border-gray-700 rounded px-2 py-1.5 text-sm text-gray-200 focus:outline-none focus:border-blue-500"
          />
        </div>

        <div className="flex items-end gap-4 pb-0.5">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={form.redact}
              onChange={(e) => set('redact', e.target.checked)}
              className="accent-purple-500"
            />
            <span className="text-sm text-gray-300">Redact output</span>
          </label>
        </div>
      </div>

      <div className="flex gap-2 pt-1">
        <button
          type="submit"
          className="px-4 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded transition-colors"
        >
          Add Rule
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm rounded transition-colors"
        >
          Cancel
        </button>
      </div>
    </form>
  )
}

export default function RulesPanel() {
  const [rules, setRules] = useState([])
  const [error, setError] = useState(null)
  const [adding, setAdding] = useState(false)

  const load = useCallback(async () => {
    try {
      setRules(await fetchRules())
    } catch (e) {
      setError(e.message)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const handleToggle = async (rule) => {
    try {
      await updateRule(rule.id, { ...rule, enabled: !rule.enabled })
      load()
    } catch (e) { setError(e.message) }
  }

  const handleDelete = async (id) => {
    if (!confirm('Delete this rule?')) return
    try {
      await deleteRule(id)
      load()
    } catch (e) { setError(e.message) }
  }

  const handleAdd = async (form) => {
    try {
      await createRule(form)
      setAdding(false)
      load()
    } catch (e) { setError(e.message) }
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-gray-800 bg-gray-900 flex-shrink-0">
        <div>
          <p className="text-sm font-medium text-gray-200">Enforcement Rules</p>
          <p className="text-xs text-gray-500 mt-0.5">Per-flag mode overrides applied before the global default</p>
        </div>
        <button
          onClick={() => setAdding(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded transition-colors"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="w-4 h-4">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          Add Rule
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {error && (
          <div className="m-4 px-3 py-2 bg-red-900/40 border border-red-700 rounded text-red-400 text-sm">
            {error}
          </div>
        )}

        {adding && (
          <div className="p-4">
            <AddRuleForm onAdd={handleAdd} onCancel={() => setAdding(false)} />
          </div>
        )}

        {/* Header row */}
        {rules.length > 0 && (
          <div className="flex items-center gap-3 px-4 py-2 text-xs text-gray-600 border-b border-gray-800">
            <span className="w-9">On/Off</span>
            <span className="flex-1">Flag</span>
            <span className="flex-1">Name</span>
            <span>Mode</span>
            <span className="w-16">Redact</span>
            <span className="w-4" />
          </div>
        )}

        {rules.length === 0 && !adding && !error && (
          <div className="p-8 text-center text-gray-600 text-sm">
            No rules configured. Add a rule to override the global enforcement mode per flag.
          </div>
        )}

        {rules.map((rule) => (
          <RuleRow
            key={rule.id}
            rule={rule}
            onToggle={handleToggle}
            onDelete={handleDelete}
          />
        ))}
      </div>
    </div>
  )
}
