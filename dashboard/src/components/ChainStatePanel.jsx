import { useState, useEffect } from 'react'
import { fetchChainState } from '../api'

const STATE_STYLES = {
  USE_COMPLETE: 'bg-red-900 text-red-300 border border-red-700',
  US_SEEN: 'bg-orange-900 text-orange-300 border border-orange-700',
  SE_SEEN: 'bg-orange-900 text-orange-300 border border-orange-700',
  UE_SEEN: 'bg-yellow-900 text-yellow-300 border border-yellow-700',
  U_SEEN: 'bg-yellow-900 text-yellow-300 border border-yellow-800',
  S_SEEN: 'bg-blue-900 text-blue-300 border border-blue-800',
  IDLE: 'bg-gray-800 text-gray-400 border border-gray-700',
}

const SEVERITY_STYLES = {
  CRITICAL: 'text-red-400',
  HIGH: 'text-orange-400',
  MEDIUM: 'text-yellow-400',
  LOW: 'text-gray-400',
}

const LABEL_STYLES = {
  U: 'bg-purple-900 text-purple-200',
  S: 'bg-blue-900 text-blue-200',
  E: 'bg-red-900 text-red-200',
}

function LabelBadge({ label }) {
  const style = LABEL_STYLES[label] ?? 'bg-gray-800 text-gray-400'
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded font-bold mono ${style}`}>
      {label}
    </span>
  )
}

export default function ChainStatePanel({ sessionId }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!sessionId) {
      setData(null)
      setError(null)
      return
    }

    let active = true
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const result = await fetchChainState(sessionId)
        if (active) setData(result)
      } catch (e) {
        if (active) setError(e.message)
      } finally {
        if (active) setLoading(false)
      }
    }

    load()
    const interval = setInterval(load, 2000)
    return () => {
      active = false
      clearInterval(interval)
    }
  }, [sessionId])

  if (!sessionId) {
    return (
      <div className="flex items-center justify-center h-full text-gray-600 text-sm">
        Select a session from the sidebar to view its chain state.
      </div>
    )
  }

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center h-full text-gray-600 text-sm">
        Loading…
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full text-red-500 text-sm">
        {error}
      </div>
    )
  }

  if (!data) return null

  const stateStyle = STATE_STYLES[data.current_chain_state] ?? STATE_STYLES.IDLE

  return (
    <div className="p-5 overflow-y-auto h-full space-y-5">
      {/* Current state */}
      <div className="flex items-center gap-4">
        <div>
          <p className="text-xs text-gray-500 mb-1">Chain State</p>
          <span className={`text-sm px-3 py-1 rounded font-semibold ${stateStyle}`}>
            {data.current_chain_state}
          </span>
        </div>
        <div>
          <p className="text-xs text-gray-500 mb-1">Session State</p>
          <span
            className={`text-sm px-3 py-1 rounded font-semibold ${
              data.session_state === 'ALERT'
                ? 'bg-yellow-900 text-yellow-300 border border-yellow-700'
                : 'bg-green-900 text-green-300 border border-green-800'
            }`}
          >
            {data.session_state}
          </span>
        </div>
        <div className="ml-auto text-right">
          <p className="text-xs text-gray-500">Window</p>
          <p className="text-sm text-gray-300">{data.window_entries?.length ?? 0} / {data.window_size} calls</p>
        </div>
      </div>

      {/* Active combinations */}
      {data.active_combinations?.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
            Active Combinations
          </p>
          <div className="space-y-2">
            {data.active_combinations.map((combo) => (
              <div
                key={combo.combination}
                className="flex items-center justify-between bg-gray-900 rounded px-3 py-2 border border-gray-800"
              >
                <div className="flex items-center gap-3">
                  <span className="font-bold text-gray-200 mono">{combo.combination}</span>
                  <span className="text-xs text-gray-400">step {combo.step}</span>
                </div>
                <span className={`text-xs font-semibold ${SEVERITY_STYLES[combo.severity] ?? 'text-gray-400'}`}>
                  {combo.severity}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Window entries */}
      <div>
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
          Window Entries ({data.window_entries?.length ?? 0})
        </p>
        {data.window_entries?.length === 0 ? (
          <p className="text-xs text-gray-600">No tool calls in window yet.</p>
        ) : (
          <div className="space-y-1">
            {data.window_entries?.map((entry, i) => (
              <div
                key={i}
                className="flex items-center gap-2 bg-gray-900 rounded px-3 py-2 border border-gray-800"
              >
                <span className="text-xs text-gray-600 mono w-6 text-right">{i + 1}</span>
                <span className="text-sm text-gray-200 flex-1">{entry.tool}</span>
                <div className="flex gap-1">
                  {entry.labels.length > 0
                    ? entry.labels.map((l) => <LabelBadge key={l} label={l} />)
                    : <span className="text-xs text-gray-700">—</span>}
                </div>
                <span className="text-xs text-gray-600">{entry.backend}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
