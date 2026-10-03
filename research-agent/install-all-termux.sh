#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

echo "=== MILY Research Agent :: Termux Installer ==="

pkg update -y
pkg upgrade -y

# Base tools
pkg install -y \
  python \
  git \
  curl \
  wget \
  openssl \
  clang \
  make \
  pkg-config \
  libffi \
  rust

python -m pip install --upgrade pip setuptools wheel

# MILY Python dependencies
if [ -f requirements.txt ]; then
  python -m pip install -r requirements.txt
else
  python -m pip install "openai>=1.0.0"
fi

# Useful optional packages for local research/report processing
python -m pip install requests beautifulsoup4 lxml markdown

echo
echo "=== Instalación terminada ==="
echo
echo "Configura tu clave SIN escribirla en el repositorio:"
echo 'export OPENAI_API_KEY="TU_CLAVE"'
echo
echo "Prueba:"
echo 'python mily_deep_person.py "tema que quieres investigar"'
echo
echo "Informe TXT + JSON:"
echo 'python mily_deep_person.py --txt --json "tema que quieres investigar"'
