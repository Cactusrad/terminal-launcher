#!/bin/bash

# Workspace Multi-Agents - Terminal Launcher
SESSION_NAME="terminal-launcher"
PROJECT_DIR="/home/cactus/claude/terminal-launcher"

tmux has-session -t $SESSION_NAME 2>/dev/null
if [ $? == 0 ]; then
    tmux attach -t $SESSION_NAME
    exit 0
fi

# Créer la session
tmux new-session -d -s $SESSION_NAME -n "Claude" -c $PROJECT_DIR
tmux send-keys -t $SESSION_NAME:Claude "echo '🎯 TERMINAL LAUNCHER - Claude Principal'" C-m
tmux send-keys -t $SESSION_NAME:Claude "echo 'Lancer: claude --dangerously-skip-permissions'" C-m

# Fenêtre Structure
tmux new-window -t $SESSION_NAME -n "Structure"
tmux send-keys -t $SESSION_NAME:Structure "cd $PROJECT_DIR && watch -n 5 'tree -L 2 --dirsfirst'" C-m

# Fenêtre Docker
tmux new-window -t $SESSION_NAME -n "Docker"
tmux send-keys -t $SESSION_NAME:Docker "cd $PROJECT_DIR && echo '🐳 Docker - Port 80'" C-m
tmux send-keys -t $SESSION_NAME:Docker "echo 'Logs: docker logs -f terminal-launcher'" C-m

# Fenêtre Logs
tmux new-window -t $SESSION_NAME -n "Logs"
tmux send-keys -t $SESSION_NAME:Logs "docker logs -f terminal-launcher 2>/dev/null || echo 'Container non démarré'" C-m

# Fenêtre Git
tmux new-window -t $SESSION_NAME -n "Git"
tmux send-keys -t $SESSION_NAME:Git "cd $PROJECT_DIR && watch -n 10 'git status --short && echo \"\" && git log --oneline -5 2>/dev/null'" C-m

tmux select-window -t $SESSION_NAME:Claude
tmux attach -t $SESSION_NAME
