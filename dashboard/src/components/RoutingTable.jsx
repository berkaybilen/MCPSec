import { useState, useEffect } from 'react'
import { fetchRoutingTable } from '../api'

export default function RoutingTable() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true
    async function load() {
      try {
        const result = await fetchRoutingTable()
        if (active) setData(result)
      } catch (e) {
        if (active) setError(e.message)
      }
    }
    load()
    const interval = setInterval(load, 10000)
    return () => {
      active = false
      clearInterval(interval)
    }
  }, [])

  if (error) {
    return (
      <div className="flex items-center justify-center h-full text-red-500 text-sm">
        {error}
      </div>
    )
  }

  if (!data) {
    return (
      <div className="flex items-center justify-center h-full text-gray-600 text-sm">
        Loading…
      </div>
    )
  }

  const toolMap = data.tool_to_backend ?? {}
  const tools = Object.entries(toolMap)

  return (
    <div className="p-5 overflow-y-auto h-full">
      <div className="flex items-center justify-between mb-4">
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
          Tool → Backend Mapping
        </p>
        <span className="text-xs text-gray-600">{tools.length} tools</span>
      </div>

      {tools.length === 0 ? (
        <p className="text-sm text-gray-600">
          No tools discovered yet. Make a tools/list request through the proxy.
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-gray-500 border-b border-gray-800">
                <th className="pb-2 pr-4 font-medium">Tool</th>
                <th className="pb-2 font-medium">Backend</th>
              </tr>
            </thead>
            <tbody>
              {tools.map(([tool, backend]) => (
                <tr key={tool} className="border-b border-gray-800 hover:bg-gray-900 transition-colors">
                  <td className="py-2 pr-4 mono text-gray-200">{tool}</td>
                  <td className="py-2">
                    <span className="bg-blue-900 text-blue-300 text-xs px-2 py-0.5 rounded">
                      {backend}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data.updated_at && (
        <p className="mt-4 text-xs text-gray-700">
          Last updated: {new Date(data.updated_at).toLocaleString()}
        </p>
      )}
    </div>
  )
}
