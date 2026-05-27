import { useState, useEffect, useCallback } from 'react'
import { fetchBackends, resetRuntimeState, triggerRescan } from '../api'

function StatusDot({ status }) {
  const color = status === 'running' ? 'bg-green-500' : 'bg-red-500'
  return <span className={`w-2 h-2 rounded-full flex-shrink-0 ${color}`} />
}

function BackendCard({ backend }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg px-5 py-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <StatusDot status={backend.status ?? 'running'} />
          <span className="font-medium text-gray-200">{backend.name}</span>
        </div>
        <span className="text-xs text-gray-500 bg-gray-800 px-2 py-0.5 rounded">
          {backend.transport ?? 'stdio'}
        </span>
      </div>

      <div className="space-y-1.5 text-sm">
        {backend.command && (
          <div className="flex gap-2">
            <span className="text-gray-600 w-20 flex-shrink-0">Command</span>
            <span className="mono text-gray-300">{backend.command}</span>
          </div>
        )}
        {backend.args?.length > 0 && (
          <div className="flex gap-2">
            <span className="text-gray-600 w-20 flex-shrink-0">Args</span>
            <span className="mono text-gray-400 text-xs">{backend.args.join(' ')}</span>
          </div>
        )}
        {backend.url && (
          <div className="flex gap-2">
            <span className="text-gray-600 w-20 flex-shrink-0">URL</span>
            <span className="mono text-gray-300">{backend.url}</span>
          </div>
        )}
      </div>
    </div>
  )
}

export default function BackendsPanel({ onRescan, onRuntimeReset }) {
  const [backends, setBackends] = useState([])
  const [error, setError] = useState(null)
  const [rescanning, setRescanning] = useState(false)
  const [rescanMsg, setRescanMsg] = useState(null)
  const [resetting, setResetting] = useState(false)

  const load = useCallback(async () => {
    try {
      setBackends(await fetchBackends())
    } catch (e) {
      setError(e.message)
    }
  }, [])

  useEffect(() => { load() }, [load])

  const handleRescan = async () => {
    setRescanning(true)
    setRescanMsg(null)
    try {
      await triggerRescan()
      setRescanMsg('Rescan triggered — discovery and toxic flow analysis are running in the background.')
      onRescan?.()
    } catch (e) {
      setRescanMsg(`Rescan failed: ${e.message}`)
    } finally {
      setRescanning(false)
    }
  }

  const handleResetRuntime = async () => {
    const confirmed = window.confirm(
      'Clear stored demo sessions, events, and cached analysis results? This cannot be undone.'
    )
    if (!confirmed) return

    setResetting(true)
    setRescanMsg(null)
    try {
      const result = await resetRuntimeState()
      setRescanMsg(
        `Runtime data cleared — removed ${result.deleted_sessions} sessions and ${result.deleted_events} events.`
      )
      await load()
      onRuntimeReset?.()
    } catch (e) {
      setRescanMsg(`Reset failed: ${e.message}`)
    } finally {
      setResetting(false)
    }
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-gray-800 bg-gray-900 flex-shrink-0">
        <div>
          <p className="text-sm font-medium text-gray-200">Backend Servers</p>
          <p className="text-xs text-gray-500 mt-0.5">
            MCP backends connected through the proxy
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleResetRuntime}
            disabled={resetting}
            className={`px-4 py-1.5 rounded text-sm font-medium transition-colors ${
              resetting
                ? 'bg-gray-800 text-gray-500 cursor-not-allowed'
                : 'bg-red-900 hover:bg-red-800 text-red-100'
            }`}
          >
            {resetting ? 'Clearing…' : 'Clear Demo Data'}
          </button>
          <button
            onClick={handleRescan}
            disabled={rescanning}
            className={`flex items-center gap-1.5 px-4 py-1.5 rounded text-sm font-medium transition-colors ${
              rescanning
                ? 'bg-gray-800 text-gray-500 cursor-not-allowed'
                : 'bg-blue-600 hover:bg-blue-500 text-white'
            }`}
          >
            <svg
              viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
              className={`w-4 h-4 ${rescanning ? 'animate-spin' : ''}`}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
            </svg>
            {rescanning ? 'Scanning…' : 'Rescan'}
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-5 space-y-3">
        {error && (
          <div className="px-3 py-2 bg-red-900/40 border border-red-700 rounded text-red-400 text-sm">
            {error}
          </div>
        )}

        {rescanMsg && (
          <div className="px-3 py-2 bg-blue-900/40 border border-blue-700 rounded text-blue-300 text-sm">
            {rescanMsg}
          </div>
        )}

        {backends.length === 0 && !error && (
          <p className="text-gray-600 text-sm text-center py-8">
            No backends found. Check mcpsec-config.yaml.
          </p>
        )}

        {backends.map((backend) => (
          <BackendCard key={backend.name} backend={backend} />
        ))}

        {/* Info box */}
        <div className="mt-4 px-4 py-3 bg-gray-900 border border-gray-800 rounded-lg">
          <p className="text-xs text-gray-500 font-medium mb-1">How rescan works</p>
          <p className="text-xs text-gray-600 leading-relaxed">
            Rescan rebuilds the routing table by calling tools/list on all backends,
            re-runs tool discovery (schema probing, hidden tool detection, change detection),
            and re-runs Toxic Flow analysis with the updated tool schemas.
            Sessions and events are not affected.
          </p>
        </div>
      </div>
    </div>
  )
}
