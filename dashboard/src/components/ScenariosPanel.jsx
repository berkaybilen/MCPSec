import { useState, useEffect } from 'react'
import { fetchScenarios, runScenario } from '../api'

const STATE_STYLES = {
  SAFE: 'bg-green-900 text-green-300 border-green-700',
  TAINTED: 'bg-yellow-900 text-yellow-300 border-yellow-700',
  SANITIZED: 'bg-blue-900 text-blue-300 border-blue-700',
}

const DECISION_STYLES = {
  block: 'bg-red-900 text-red-300',
  alert: 'bg-yellow-900 text-yellow-300',
  log: 'bg-blue-900 text-blue-300',
  pass: 'bg-gray-800 text-gray-400',
}

function Badge({ label, style }) {
  return (
    <span className={`inline-block text-xs px-1.5 py-0.5 rounded font-medium ${style}`}>
      {label}
    </span>
  )
}

function ExpectedOutcome({ expect }) {
  if (!expect) return null
  return (
    <div className="flex flex-wrap gap-1 mt-1">
      {expect.session_state && (
        <Badge
          label={`session → ${expect.session_state}`}
          style={STATE_STYLES[expect.session_state] ?? 'bg-gray-800 text-gray-400 border-gray-700'}
        />
      )}
      {expect.events?.map((ev, i) => (
        <Badge
          key={i}
          label={`${ev.tool} ${ev.direction} → ${ev.decision}${ev.flags_include?.length ? ' [' + ev.flags_include.join(', ') + ']' : ''}`}
          style={DECISION_STYLES[ev.decision] ?? 'bg-gray-800 text-gray-400'}
        />
      ))}
    </div>
  )
}

function StepRow({ step, result }) {
  const hasResult = result != null
  const passed = result?.passed
  return (
    <div className={`flex items-start gap-2 px-3 py-1.5 rounded text-xs ${
      hasResult
        ? passed ? 'bg-green-950 border border-green-900' : 'bg-red-950 border border-red-900'
        : 'bg-gray-900 border border-gray-800'
    }`}>
      <span className={`mt-0.5 text-sm leading-none ${
        hasResult ? (passed ? 'text-green-400' : 'text-red-400') : 'text-gray-600'
      }`}>
        {hasResult ? (passed ? '✓' : '✗') : '·'}
      </span>
      <div className="flex-1 min-w-0">
        <span className="font-mono text-gray-200">{step.tool}</span>
        {step.arguments && Object.keys(step.arguments).length > 0 && (
          <span className="text-gray-500 ml-2">
            {Object.entries(step.arguments)
              .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
              .join(', ')}
          </span>
        )}
        {step.expect_response?.text_contains && (
          <div className="text-gray-600 mt-0.5">
            expects: contains <span className="text-gray-400">"{step.expect_response.text_contains}"</span>
          </div>
        )}
        {step.expect_response?.text_not_contains && (
          <div className="text-gray-600 mt-0.5">
            expects: not contains <span className="text-gray-400">"{step.expect_response.text_not_contains}"</span>
          </div>
        )}
        {step.expect_response?.error_contains && (
          <div className="text-gray-600 mt-0.5">
            expects error: <span className="text-gray-400">"{step.expect_response.error_contains}"</span>
          </div>
        )}
        {result?.error && (
          <div className="text-red-400 mt-0.5">{result.error}</div>
        )}
      </div>
    </div>
  )
}

function EventRow({ event }) {
  return (
    <div className="flex items-center gap-2 text-xs py-0.5">
      <span className="text-gray-600 w-4">{event.direction === 'request' ? '→' : '←'}</span>
      <span className="font-mono text-gray-300 flex-1 truncate">{event.tool_name || event.type}</span>
      <Badge
        label={(event.decision || 'pass').toUpperCase()}
        style={DECISION_STYLES[event.decision] ?? DECISION_STYLES.pass}
      />
      {event.flags?.map((f) => (
        <span key={f} className="text-xs text-gray-500 font-mono">{f}</span>
      ))}
    </div>
  )
}

function ScenarioCard({ scenario }) {
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState(null)
  const [expanded, setExpanded] = useState(false)
  const [tab, setTab] = useState('steps')

  const handleRun = async (e) => {
    e.stopPropagation()
    setRunning(true)
    setResult(null)
    try {
      const res = await runScenario(scenario.id)
      setResult(res)
      setExpanded(true)
    } catch (err) {
      setResult({ passed: false, error: err.message, step_results: [], events: [], session: null, duration_ms: null })
      setExpanded(true)
    } finally {
      setRunning(false)
    }
  }

  const borderColor = result
    ? result.passed ? 'border-green-700' : 'border-red-700'
    : 'border-gray-800'

  return (
    <div className={`border rounded-lg overflow-hidden transition-colors ${borderColor}`}>
      {/* Header row */}
      <div
        className="flex items-center gap-3 px-4 py-3 bg-gray-900 cursor-pointer hover:bg-gray-850 select-none"
        onClick={() => setExpanded(v => !v)}
      >
        <span className="text-xs font-mono text-blue-400 w-20 flex-shrink-0">{scenario.id}</span>
        <span className="text-sm font-medium text-gray-100 flex-1 min-w-0 truncate">{scenario.name}</span>
        {result && (
          <Badge
            label={result.passed ? 'PASS' : 'FAIL'}
            style={result.passed ? 'bg-green-800 text-green-200' : 'bg-red-800 text-red-200'}
          />
        )}
        {result?.duration_ms != null && (
          <span className="text-xs text-gray-600">{result.duration_ms}ms</span>
        )}
        <button
          onClick={handleRun}
          disabled={running}
          className="text-xs px-3 py-1 rounded bg-blue-700 hover:bg-blue-600 disabled:opacity-40 disabled:cursor-not-allowed text-white transition-colors flex-shrink-0"
        >
          {running ? 'Running…' : 'Run'}
        </button>
        <span className="text-gray-600 text-xs w-3">{expanded ? '▲' : '▼'}</span>
      </div>

      {/* Expanded body */}
      {expanded && (
        <div className="bg-gray-950 border-t border-gray-800">
          {/* Description */}
          {scenario.description && (
            <div className="px-4 pt-3 pb-2 text-xs text-gray-400 leading-relaxed border-b border-gray-900">
              {scenario.description}
            </div>
          )}

          {/* Tabs */}
          <div className="flex gap-0 border-b border-gray-800 px-4">
            {['steps', 'expects', ...(result ? ['events'] : [])].map(t => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`text-xs px-3 py-2 border-b-2 transition-colors capitalize ${
                  tab === t
                    ? 'border-blue-500 text-blue-400'
                    : 'border-transparent text-gray-500 hover:text-gray-300'
                }`}
              >
                {t}
                {t === 'events' && result?.events?.length ? ` (${result.events.length})` : ''}
              </button>
            ))}
          </div>

          <div className="px-4 py-3 space-y-2">
            {/* Steps tab */}
            {tab === 'steps' && (
              <div className="space-y-1.5">
                {(scenario.steps || []).map((step, i) => (
                  <StepRow
                    key={i}
                    step={step}
                    result={result?.step_results?.[i] ?? null}
                  />
                ))}
              </div>
            )}

            {/* Expected tab */}
            {tab === 'expects' && (
              <div>
                <ExpectedOutcome expect={scenario.expect} />
                {result?.error && (
                  <div className="mt-2 text-xs text-red-400">
                    Assertion failure: {result.error}
                  </div>
                )}
                {result?.session && (
                  <div className="mt-2 text-xs text-gray-500">
                    Actual session state:{' '}
                    <Badge
                      label={result.session.state}
                      style={STATE_STYLES[result.session.state] ?? 'bg-gray-800 text-gray-400 border-gray-700'}
                    />
                  </div>
                )}
              </div>
            )}

            {/* Events tab */}
            {tab === 'events' && result?.events && (
              <div className="space-y-0.5">
                {result.events.length === 0 ? (
                  <div className="text-xs text-gray-600">No events recorded.</div>
                ) : (
                  result.events.map((ev, i) => <EventRow key={i} event={ev} />)
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export default function ScenariosPanel() {
  const [scenarios, setScenarios] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [runningAll, setRunningAll] = useState(false)
  const [allResults, setAllResults] = useState(null)

  useEffect(() => {
    fetchScenarios()
      .then(setScenarios)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const passCount = allResults ? Object.values(allResults).filter(r => r.passed).length : null
  const total = scenarios.length

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800 bg-gray-900 flex-shrink-0">
        <div>
          <h2 className="text-sm font-semibold text-gray-100">Demo Scenarios</h2>
          <p className="text-xs text-gray-500 mt-0.5">
            {total} scenarios · runs against local mock MCP backend
          </p>
        </div>
        {allResults && (
          <span className={`text-xs font-medium px-2 py-1 rounded ${
            passCount === total ? 'bg-green-900 text-green-300' : 'bg-red-900 text-red-300'
          }`}>
            {passCount}/{total} passed
          </span>
        )}
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {loading && (
          <div className="text-center text-gray-600 text-sm py-12">Loading scenarios…</div>
        )}
        {error && (
          <div className="text-center text-red-500 text-sm py-12">{error}</div>
        )}
        {!loading && !error && scenarios.map(s => (
          <ScenarioCard key={s.id} scenario={s} />
        ))}
      </div>
    </div>
  )
}
