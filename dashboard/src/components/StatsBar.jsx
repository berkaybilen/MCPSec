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
      <Stat label="Sessions" value={stats?.total_sessions} />
      <Stat label="Events" value={stats?.total_events} />
      <Stat label="Alerts" value={stats?.alert_count} color="text-yellow-400" />
      <Stat label="Blocks" value={stats?.block_count} color="text-red-400" />
      <Stat label="Credential Leaks" value={stats?.credential_leak_count} color="text-orange-400" />
    </div>
  )
}
