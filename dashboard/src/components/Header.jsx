export default function Header({ wsStatus }) {
  const statusColor = {
    connected: 'bg-green-500',
    disconnected: 'bg-red-500',
    connecting: 'bg-yellow-500',
  }[wsStatus] ?? 'bg-gray-500'

  const statusLabel = {
    connected: 'Live',
    disconnected: 'Disconnected',
    connecting: 'Connecting…',
  }[wsStatus] ?? wsStatus

  return (
    <header className="flex items-center justify-between px-5 py-3 bg-gray-900 border-b border-gray-800 flex-shrink-0">
      <div className="flex items-center gap-3">
        <div className="w-7 h-7 rounded bg-blue-600 flex items-center justify-center">
          <svg viewBox="0 0 24 24" fill="none" className="w-4 h-4 text-white" stroke="currentColor" strokeWidth="2">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75m-3-7.036A11.959 11.959 0 013.598 6 11.99 11.99 0 003 9.749c0 5.592 3.824 10.29 9 11.623 5.176-1.332 9-6.03 9-11.622 0-1.31-.21-2.571-.598-3.751h-.152c-3.196 0-6.1-1.248-8.25-3.285z" />
          </svg>
        </div>
        <div>
          <h1 className="text-sm font-semibold text-gray-100">MCPSec</h1>
          <p className="text-xs text-gray-500">MCP Security Proxy</p>
        </div>
      </div>

      <div className="flex items-center gap-2">
        <span className={`w-2 h-2 rounded-full ${statusColor} ${wsStatus === 'connected' ? 'animate-pulse' : ''}`} />
        <span className="text-xs text-gray-400">{statusLabel}</span>
      </div>
    </header>
  )
}
