#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

CONFIG="$HOME/.bashrc"
BACKUP_DIR="$HOME/.mily-termux-backups"
STAMP="$(date +%Y%m%d-%H%M%S)"

backup() {
  mkdir -p "$BACKUP_DIR"
  if [ -f "$CONFIG" ]; then
    cp "$CONFIG" "$BACKUP_DIR/bashrc-$STAMP"
    echo "Respaldo: $BACKUP_DIR/bashrc-$STAMP"
  else
    echo "No existe $CONFIG; se creará cuando sea necesario."
  fi
}

preview() {
  echo "=== MILY Termux Customizer :: Preview ==="
  echo
  echo "Se propone:"
  echo "  • prompt MILY"
  echo "  • alias básicos para navegación"
  echo "  • función 'mily-status'"
  echo "  • bienvenida limpia"
  echo
  echo "No se modifica nada."
}

apply() {
  backup
  touch "$CONFIG"

  if ! grep -q 'MILY_TERMUX_CUSTOMIZER_START' "$CONFIG"; then
    cat >> "$CONFIG" <<'EOF'

# MILY_TERMUX_CUSTOMIZER_START
export MILY_TERMUX=1
export PS1='\[\e[1;36m\]MILY\[\e[0m\] \[\e[1;35m\]\w\[\e[0m\] $ '

alias ll='ls -lah'
alias la='ls -A'
alias cls='clear'
alias ..='cd ..'

mily-status() {
  echo "MILY Termux Customizer"
  echo "Shell: $SHELL"
  echo "Home: $HOME"
  echo "Python: $(python --version 2>/dev/null || echo no-disponible)"
  echo "Git: $(git --version 2>/dev/null || echo no-disponible)"
}

# MILY_TERMUX_CUSTOMIZER_END
EOF
    echo "Personalización aplicada."
  else
    echo "La personalización MILY ya existe; no se duplicó."
  fi
}

restore() {
  latest="$(ls -1t "$BACKUP_DIR"/bashrc-* 2>/dev/null | head -n 1 || true)"
  if [ -z "$latest" ]; then
    echo "No hay respaldos disponibles."
    exit 1
  fi
  cp "$latest" "$CONFIG"
  echo "Restaurado: $latest"
}

status() {
  echo "=== Estado MILY Termux ==="
  if grep -q 'MILY_TERMUX_CUSTOMIZER_START' "$CONFIG" 2>/dev/null; then
    echo "Personalización: activa"
  else
    echo "Personalización: no instalada"
  fi
  echo "Backups: $BACKUP_DIR"
}

case "${1:-preview}" in
  preview) preview ;;
  backup) backup ;;
  customize|apply) apply ;;
  restore) restore ;;
  status) status ;;
  *)
    echo "Uso: $0 {preview|backup|customize|restore|status}"
    exit 1
    ;;
esac
