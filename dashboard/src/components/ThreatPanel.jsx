import { useState, useEffect } from 'react'
import { fetchToxicFlow } from '../api'

const SEVERITY_STYLES = {
  CRITICAL: { badge: 'bg-red-900 text-red-300 border border-red-700', bar: 'bg-red-500' },
  HIGH:     { badge: 'bg-orange-900 text-orange-300 border border-orange-700', bar: 'bg-orange-500' },
  MEDIUM:   { badge: 'bg-yellow-900 text-yellow-300 border border-yellow-700', bar: 'bg-yellow-500' },
  LOW:      { badge: 'bg-blue-900 text-blue-300 border border-blue-800', bar: 'bg-blue-500' },
  NONE:     { badge: 'bg-gray-800 text-gray-400 border border-gray-700', bar: 'bg-gray-600' },
}

const LABEL_STYLES = {
  U: 'bg-purple-900 text-purple-200 border border-purple-700',
  S: 'bg-blue-900 text-blue-200 border border-blue-800',
  E: 'bg-red-900 text-red-200 border border-red-800',
}

function SeverityBadge({ severity }) {
  const s = SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.NONE
  return (
    <span className={`text-xs px-2 py-0.5 rounded font-semibold ${s.badge}`}>
      {severity}
    </span>
  )
}

function LabelBadge({ label }) {
  const style = LABEL_STYLES[label] ?? 'bg-gray-800 text-gray-400'
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded font-bold mono ${style}`} title={
      label === 'U' ? 'Untrusted Input' : label === 'S' ? 'Sensitive Access' : 'External Output'
    }>
      {label}
    </span>
  )
}

function ConfidenceBar({ score }) {
  const pct = Math.round((score ?? 0) * 100)
  const color =
    pct >= 85 ? 'bg-red-500' :
    pct >= 70 ? 'bg-orange-500' :
    pct >= 50 ? 'bg-yellow-500' : 'bg-blue-500'
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 bg-gray-800 rounded-full h-1.5">
        <div className={`h-1.5 rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-gray-400 mono w-8 text-right">{pct}%</span>
    </div>
  )
}

function DangerousPathCard({ path }) {
  const [open, setOpen] = useState(false)
  const labels = path.chain_labels ?? []
  const tools = path.chain ?? []
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen(v => !v)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-gray-800 transition-colors"
      >
        <SeverityBadge severity={path.severity} />
        <div className="flex gap-1 items-center">
          {labels.map((l, i) => (
            <span key={i} className="flex items-center gap-1">
              <LabelBadge label={l} />
              {i < labels.length - 1 && <span className="text-gray-600 text-xs">→</span>}
            </span>
          ))}
        </div>
        <span className="ml-2 text-gray-300 text-sm flex-1 truncate">
          {tools.join(' → ')}
        </span>
        <svg
          className={`w-4 h-4 text-gray-500 flex-shrink-0 transition-transform ${open ? 'rotate-180' : ''}`}
          fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && (
        <div className="px-4 pb-4 border-t border-gray-800 space-y-3 pt-3">
          <div className="flex flex-wrap gap-2">
            {tools.map((tool) => (
              <span key={tool} className="mono text-xs bg-gray-800 text-gray-300 px-2 py-1 rounded">
                {tool}
              </span>
            ))}
          </div>
          {path.recommendation && (
            <p className="text-sm text-gray-400 leading-relaxed">
              {path.recommendation}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

function ToolCard({ name, data }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg px-4 py-3">
      <div className="flex items-center justify-between mb-2">
        <span className="mono text-sm text-gray-200">{name}</span>
        <div className="flex gap-1">
          {data.labels?.map((l) => <LabelBadge key={l} label={l} />)}
          {(!data.labels || data.labels.length === 0) && (
            <span className="text-xs text-gray-700">no labels</span>
          )}
        </div>
      </div>
      <ConfidenceBar score={data.confidence} />
    </div>
  )
}

export default function ThreatPanel() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [activeTab, setActiveTab] = useState('paths')

  useEffect(() => {
    fetchToxicFlow()
      .then(setData)
      .catch((e) => setError(e.message))
  }, [])

  if (error) return (
    <div className="flex items-center justify-center h-full text-red-500 text-sm">{error}</div>
  )
  if (!data) return (
    <div className="flex items-center justify-center h-full text-gray-600 text-sm">Loading…</div>
  )

  const tools = Object.entries(data.tools ?? {})
  const paths = data.dangerous_paths ?? []
  const sessionSeverity = data.session_severity ?? 'NONE'

  const labelCounts = { U: 0, S: 0, E: 0 }
  tools.forEach(([, d]) => d.labels?.forEach((l) => { if (l in labelCounts) labelCounts[l]++ }))

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Summary bar */}
      <div className="flex items-center gap-6 px-6 py-4 bg-gray-900 border-b border-gray-800 flex-shrink-0">
        <div>
          <p className="text-xs text-gray-500 mb-1">Session Severity</p>
          <SeverityBadge severity={sessionSeverity} />
        </div>
        <div className="h-8 border-l border-gray-800" />
        <div>
          <p className="text-xs text-gray-500 mb-1">Dangerous Paths</p>
          <p className="text-lg font-bold text-gray-100">{paths.length}</p>
        </div>
        <div>
          <p className="text-xs text-gray-500 mb-1">Tools Analyzed</p>
          <p className="text-lg font-bold text-gray-100">{tools.length}</p>
        </div>
        <div className="h-8 border-l border-gray-800" />
        <div className="flex gap-4">
          {Object.entries(labelCounts).map(([label, count]) => (
            <div key={label}>
              <p className="text-xs text-gray-500 mb-1">
                {label === 'U' ? 'Untrusted' : label === 'S' ? 'Sensitive' : 'External'}
              </p>
              <div className="flex items-center gap-1">
                <LabelBadge label={label} />
                <span className="text-sm font-bold text-gray-200">{count}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-gray-800 px-4 bg-gray-900 flex-shrink-0">
        {[
          { id: 'paths', label: `Dangerous Paths (${paths.length})` },
          { id: 'tools', label: `Tools (${tools.length})` },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors ${
              activeTab === tab.id
                ? 'border-blue-500 text-blue-400'
                : 'border-transparent text-gray-400 hover:text-gray-200'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-5 space-y-3">
        {activeTab === 'paths' && (
          paths.length === 0
            ? <p className="text-gray-600 text-sm">No dangerous paths detected.</p>
            : paths.map((path, i) => <DangerousPathCard key={i} path={path} />)
        )}
        {activeTab === 'tools' && (
          tools.length === 0
            ? <p className="text-gray-600 text-sm">No tools analyzed yet. Run a rescan.</p>
            : <div className="grid grid-cols-2 gap-3">
                {tools.map(([name, d]) => <ToolCard key={name} name={name} data={d} />)}
              </div>
        )}
      </div>
    </div>
  )
}
