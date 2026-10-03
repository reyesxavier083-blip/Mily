#!/data/data/com.termux/files/usr/bin/bash
set -e
pkg update -y
pkg install python -y
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo
echo "MILY Research Agent instalado."
echo 'Configura: export OPENAI_API_KEY="TU_CLAVE"'
echo 'Ejemplo: python mily_research.py "Investiga este tema"'
