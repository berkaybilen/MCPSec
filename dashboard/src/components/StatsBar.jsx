function Stat({ label, value, color = 'text-gray-100' }) {
  return (
    <div className="flex flex-col items-center px-6 py-2 border-r border-gray-800 last:border-0">
      <span className={`text-xl font-bold mono ${color}`}>
        {value ?? '—'}
      </span>
      <span className="text-xs text-gray-500 mt-0.5">{label}</span>
    </div>
  )
}

export default function StatsBar({ stats }) {
  return (
    <div className="flex items-center bg-gray-900 border-b border-gray-800 flex-shrink-0">
      <Stat label="Sessions" value={stats?.sessions_total} />
      <Stat label="Events" value={stats?.events_total} />
      <Stat label="Flagged" value={stats?.flagged_events} color="text-orange-400" />
      <Stat label="Alerts" value={stats?.alerted} color="text-yellow-400" />
      <Stat label="Blocks" value={stats?.blocked} color="text-red-400" />
    </div>
  )
}
