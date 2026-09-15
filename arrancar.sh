#!/bin/zsh
cd "$(dirname "$0")"
source ./config.sh
exec /usr/bin/python3 ./vigila_tenis.py
