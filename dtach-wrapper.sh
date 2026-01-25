#!/bin/bash
# Usage: dtach-wrapper.sh <session-name> <project-folder> [command]
# Called by ttyd with arguments passed via URL
# Example URL: http://host:7681?arg=my-session&arg=rad_serial_pro&arg=claude

SESSION="$1"
PROJECT="$2"
COMMAND="${3:-bash}"
PROJECT_PATH="/home/cactus/claude/$PROJECT"
SOCKET_DIR="/tmp/dtach-sessions"
LOG_DIR="/tmp/terminal-logs"

# Create directories if needed
mkdir -p "$SOCKET_DIR" "$LOG_DIR"
chmod 777 "$SOCKET_DIR" "$LOG_DIR" 2>/dev/null

if [ -z "$SESSION" ] || [ -z "$PROJECT" ]; then
    # No arguments = default behavior (interactive bash)
    exec bash -l
fi

# Sanitize session name
SESSION=$(echo "$SESSION" | tr '.,:/' '____')
SOCKET="$SOCKET_DIR/$SESSION.sock"
LOG_FILE="$LOG_DIR/$SESSION.log"

# Check if project folder exists
if [ ! -d "$PROJECT_PATH" ]; then
    echo "Error: Project '$PROJECT' not found at $PROJECT_PATH"
    echo "Starting in home directory instead..."
    PROJECT_PATH="/home/cactus"
fi

# Build the command to run (wrapped with script for logging)
if [ "$COMMAND" = "bash" ]; then
    RUN_CMD="cd '$PROJECT_PATH' && exec script -f -q '$LOG_FILE' -c 'bash -l'"
else
    RUN_CMD="cd '$PROJECT_PATH' && exec script -f -q '$LOG_FILE' -c '$COMMAND'"
fi

# Check if session already exists
if [ -S "$SOCKET" ]; then
    # Attach to existing session
    exec dtach -a "$SOCKET" -z
else
    # Create new session in background, then attach
    # Initialize empty log file
    touch "$LOG_FILE"
    chmod 666 "$LOG_FILE" 2>/dev/null
    dtach -n "$SOCKET" -z bash -c "$RUN_CMD"
    sleep 0.3
    exec dtach -a "$SOCKET" -z
fi
