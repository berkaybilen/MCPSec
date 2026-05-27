#!/usr/bin/env bash
# MCPSec — start backend + dashboard as independent background services
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

BACKEND_PID_FILE="$LOG_DIR/backend.pid"
FRONTEND_PID_FILE="$LOG_DIR/frontend.pid"

PYTHON="$SCRIPT_DIR/mcpsec/.venv/bin/python3"
CONFIG="$SCRIPT_DIR/mcpsec-config.yaml"

stop_service() {
    local pid_file="$1"
    local name="$2"
    if [ -f "$pid_file" ]; then
        local pid
        pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            echo "Stopping $name (pid=$pid)..."
            kill "$pid"
        fi
        rm -f "$pid_file"
    fi
}

case "${1:-start}" in
    start)
        echo "=== Starting MCPSec ==="

        # Backend
        if [ -f "$BACKEND_PID_FILE" ] && kill -0 "$(cat "$BACKEND_PID_FILE")" 2>/dev/null; then
            echo "Backend already running (pid=$(cat "$BACKEND_PID_FILE"))"
        else
            echo "Starting backend (http://localhost:8080)..."
            "$PYTHON" -m mcpsec \
                --config "$CONFIG" \
                --sse \
                --log-file "$LOG_DIR/backend.log" \
                &
            echo $! > "$BACKEND_PID_FILE"
            echo "Backend started (pid=$!, log=$LOG_DIR/backend.log)"
        fi

        # Frontend
        if [ -f "$FRONTEND_PID_FILE" ] && kill -0 "$(cat "$FRONTEND_PID_FILE")" 2>/dev/null; then
            echo "Dashboard already running (pid=$(cat "$FRONTEND_PID_FILE"))"
        else
            echo "Starting dashboard (http://localhost:5173)..."
            cd "$SCRIPT_DIR/dashboard"
            npm run dev -- --host 2>> "$LOG_DIR/frontend.log" &
            echo $! > "$FRONTEND_PID_FILE"
            echo "Dashboard started (pid=$!, log=$LOG_DIR/frontend.log)"
        fi

        echo ""
        echo "Dashboard: http://localhost:5173"
        echo "API:       http://localhost:8080"
        echo ""
        echo "Logs: $LOG_DIR/"
        echo "Stop: $0 stop"
        ;;

    stop)
        echo "=== Stopping MCPSec ==="
        stop_service "$BACKEND_PID_FILE" "backend"
        stop_service "$FRONTEND_PID_FILE" "dashboard"
        echo "Done."
        ;;

    restart)
        "$0" stop
        sleep 1
        "$0" start
        ;;

    status)
        if [ -f "$BACKEND_PID_FILE" ] && kill -0 "$(cat "$BACKEND_PID_FILE")" 2>/dev/null; then
            echo "Backend:  running (pid=$(cat "$BACKEND_PID_FILE"))"
        else
            echo "Backend:  stopped"
        fi
        if [ -f "$FRONTEND_PID_FILE" ] && kill -0 "$(cat "$FRONTEND_PID_FILE")" 2>/dev/null; then
            echo "Dashboard: running (pid=$(cat "$FRONTEND_PID_FILE"))"
        else
            echo "Dashboard: stopped"
        fi
        ;;

    logs)
        echo "=== Backend log ==="
        tail -50 "$LOG_DIR/backend.log" 2>/dev/null || echo "(no log yet)"
        echo ""
        echo "=== Frontend log ==="
        tail -20 "$LOG_DIR/frontend.log" 2>/dev/null || echo "(no log yet)"
        ;;

    *)
        echo "Usage: $0 {start|stop|restart|status|logs}"
        exit 1
        ;;
esac
