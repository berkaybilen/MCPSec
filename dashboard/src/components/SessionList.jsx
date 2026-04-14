function StateBadge({ state }) {
  const styles = {
    ALERT: 'bg-yellow-900 text-yellow-300 border border-yellow-700',
    NORMAL: 'bg-green-900 text-green-300 border border-green-800',
  }[state] ?? 'bg-gray-800 text-gray-400'

  return (
    <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${styles}`}>
      {state}
    </span>
  )
}

function timeAgo(isoString) {
  if (!isoString) return ''
  const diff = Date.now() - new Date(isoString).getTime()
  const s = Math.floor(diff / 1000)
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  return `${h}h ago`
}

export default function SessionList({ sessions, selectedSession, onSelect }) {
  if (!sessions.length) {
    return (
      <div className="p-4 text-center text-gray-600 text-xs">
        No sessions yet.<br />Start the proxy to begin.
      </div>
    )
  }

  return (
    <ul>
      {sessions.map((session) => {
        const isSelected = session.session_id === selectedSession
        return (
          <li
            key={session.session_id}
            onClick={() => onSelect(session.session_id)}
            className={`px-4 py-3 border-b border-gray-800 cursor-pointer transition-colors ${
              isSelected ? 'bg-blue-950 border-l-2 border-l-blue-500' : 'hover:bg-gray-900'
            }`}
          >
            <div className="flex items-center justify-between mb-1">
              <StateBadge state={session.state} />
              <span className="text-xs text-gray-600">{timeAgo(session.created_at)}</span>
            </div>
            <p className="mono text-gray-400 truncate text-xs">{session.session_id}</p>
            <p className="text-xs text-gray-600 mt-0.5">{session.event_count ?? 0} events</p>
          </li>
        )
      })}
    </ul>
  )
}
