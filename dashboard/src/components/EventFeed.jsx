import { useEffect, useMemo, useState } from 'react'
import { fetchEvents } from '../api'

const DECISION_STYLES = {
  block: 'bg-red-900 text-red-300 border-red-700',
  alert: 'bg-yellow-900 text-yellow-300 border-yellow-700',
  log: 'bg-blue-900 text-blue-300 border-blue-800',
  pass: 'bg-gray-800 text-gray-400 border-gray-700',
}

const DIRECTION_ICON = {
  request: '→',
  response: '←',
}

function DecisionBadge({ decision }) {
  const style = DECISION_STYLES[decision] ?? DECISION_STYLES.pass
  return (
    <span className={`text-xs px-1.5 py-0.5 rounded border font-medium ${style}`}>
      {decision?.toUpperCase() ?? 'PASS'}
    </span>
  )
}

function Flag({ flag }) {
  const isChain = flag.startsWith('chain:')
  return (
    <span
      className={`text-xs px-1.5 py-0.5 rounded mono ${
        isChain
          ? 'bg-purple-900 text-purple-300'
          : 'bg-gray-800 text-gray-400'
      }`}
    >
      {flag}
    </span>
  )
}

function EventRow({ event }) {
  const [expanded, setExpanded] = useState(false)
  const isAlert = event.decision === 'block' || event.decision === 'alert'

  return (
    <div
      className={`border-b border-gray-800 px-4 py-2 hover:bg-gray-900 cursor-pointer transition-colors ${
        isAlert ? 'border-l-2 border-l-yellow-600' : ''
      } ${event.decision === 'block' ? 'border-l-red-500' : ''}`}
      onClick={() => setExpanded((v) => !v)}
    >
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-gray-600 text-xs mono w-[160px] flex-shrink-0">
          {new Date(event.timestamp).toLocaleTimeString()}
        </span>
        <span className="text-gray-500 text-xs w-4">
          {DIRECTION_ICON[event.direction] ?? '?'}
        </span>
        <span className="text-gray-200 text-sm font-medium flex-1 truncate">
          {event.tool_name || event.type || '—'}
        </span>
        <DecisionBadge decision={event.decision} />
        {event.flags?.map((f) => <Flag key={f} flag={f} />)}
        {event.matched_combination && (
          <span className="text-xs bg-purple-900 text-purple-300 px-1.5 py-0.5 rounded mono">
            {event.matched_combination} {event.step}
          </span>
        )}
      </div>

      {/* Chain tracking alert/block — special row */}
      {(event.type === 'chain_tracking_alert' || event.type === 'chain_tracking_block') && (
        <div className="mt-1 flex items-center gap-2">
          <span className="text-xs text-purple-400 font-medium">Chain Tracking</span>
          <span className="text-xs text-gray-400">
            {event.matched_combination} · step {event.step}
          </span>
        </div>
      )}

      {/* Expanded detail */}
      {expanded && event.content && (
        <pre className="mt-2 text-xs text-gray-500 bg-gray-900 rounded p-2 overflow-x-auto max-h-48 overflow-y-auto">
          {JSON.stringify(event.content ?? event.context, null, 2)}
        </pre>
      )}
    </div>
  )
}

const FILTER_OPTIONS = ['all', 'block', 'alert', 'log', 'pass']

function eventKey(event) {
  return event.id
    ? `db:${event.id}`
    : [
        event.session_id,
        event.timestamp,
        event.direction,
        event.tool_name || event.type,
        event.decision,
        (event.flags || []).join(','),
      ].join('|')
}

export default function EventFeed({ liveEvents, selectedSession, refreshToken }) {
  const [filter, setFilter] = useState('all')
  const [persistedEvents, setPersistedEvents] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true

    async function load() {
      setLoading(true)
      setError(null)
      try {
        const events = await fetchEvents(
          selectedSession ? { session_id: selectedSession, limit: 1000 } : { limit: 200 }
        )
        if (active) {
          setPersistedEvents(events)
        }
      } catch (e) {
        if (active) {
          setError(e.message)
        }
      } finally {
        if (active) {
          setLoading(false)
        }
      }
    }

    load()
    return () => {
      active = false
    }
  }, [selectedSession, refreshToken])

  const matchingLiveEvents = selectedSession
    ? liveEvents.filter((e) => e.session_id === selectedSession)
    : liveEvents

  const events = useMemo(() => {
    const merged = []
    const seen = new Set()
    for (const event of [...matchingLiveEvents, ...persistedEvents]) {
      const key = eventKey(event)
      if (seen.has(key)) continue
      seen.add(key)
      merged.push(event)
    }
    return merged
  }, [matchingLiveEvents, persistedEvents])

  const filtered = filter === 'all'
    ? events
    : events.filter((e) => e.decision === filter || e.type?.includes(filter))

  return (
    <div className="flex flex-col h-full">
      {/* Filter bar */}
      <div className="flex items-center gap-1 px-4 py-2 border-b border-gray-800 bg-gray-900 flex-shrink-0">
        <span className="text-xs text-gray-500 mr-2">Filter:</span>
        {FILTER_OPTIONS.map((opt) => (
          <button
            key={opt}
            onClick={() => setFilter(opt)}
            className={`text-xs px-2 py-1 rounded transition-colors ${
              filter === opt
                ? 'bg-blue-800 text-blue-200'
                : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
            }`}
          >
            {opt.toUpperCase()}
          </button>
        ))}
        <span className="ml-auto text-xs text-gray-600">
          {filtered.length} events
        </span>
      </div>

      {/* Event list */}
      <div className="flex-1 overflow-y-auto">
        {error && (
          <div className="p-8 text-center text-red-500 text-sm">
            {error}
          </div>
        )}
        {!error && loading && events.length === 0 && (
          <div className="p-8 text-center text-gray-600 text-sm">
            Loading events…
          </div>
        )}
        {!error && !loading && filtered.length === 0 ? (
          <div className="p-8 text-center text-gray-600 text-sm">
            {events.length === 0
              ? selectedSession
                ? 'No persisted events for the selected session yet.'
                : 'No persisted events yet. Run a demo scenario or use the proxy.'
              : 'No events match the current filter.'}
          </div>
        ) : (
          filtered.map((event, i) => (
            <EventRow key={eventKey(event) || `${event.session_id}-${event.timestamp}-${i}`} event={event} />
          ))
        )}
      </div>
    </div>
  )
}
