#!/usr/bin/env python3
"""
Vigila las plazas de las actividades deportivas de la UPV y avisa por Telegram
en cuanto una clase pasa de "Completo" a tener plazas libres.

Uso:
    export TELEGRAM_TOKEN="123456:ABC..."
    export TELEGRAM_CHAT_ID="123456789"
    python3 vigila_tenis.py

Variables opcionales:
    INTERVALO   segundos entre comprobaciones (por defecto 15)
    ACTIVIDADES lista "codigo:nombre" separada por comas
"""

import html
import json
import os
import random
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

BASE = "https://intranet.upv.es/pls/soalu/sic_depact.HSemActividades"
DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]

TOKEN = os.environ.get("TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
INTERVALO = int(os.environ.get("INTERVALO", "15"))

# codigo_actividad : nombre legible
ACTIVIDADES = {}
for item in os.environ.get("ACTIVIDADES", "21963:TENIS").split(","):
    item = item.strip()
    if not item:
        continue
    codigo, _, nombre = item.partition(":")
    ACTIVIDADES[codigo.strip()] = (nombre.strip() or codigo.strip())

ESTADO = Path(os.environ.get("ESTADO_FILE") or Path(__file__).with_name("estado.json"))
LOG = Path(os.environ.get("LOG_FILE") or Path(__file__).with_name("vigila.log"))


def log(msg):
    linea = f"{datetime.now():%Y-%m-%d %H:%M:%S}  {msg}"
    print(linea, flush=True)
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(linea + "\n")
    except OSError:
        pass


def descargar(codigo):
    params = {
        "p_campus": "V",
        "p_codacti": codigo,
        "p_vista": "intranet",
        "p_idioma": "c",
        "p_tipoact": "6896",
        "p_solo_matricula_sn": "",
        "p_anc": "bloque_inscritas",
    }
    url = f"{BASE}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("iso-8859-1", errors="replace"), url


def limpiar(texto):
    texto = re.sub(r"(?s)<[^>]+>", " ", texto)
    return re.sub(r"\s+", " ", html.unescape(texto)).strip()


def parsear(pagina):
    """Devuelve {clave: {...}} con una entrada por celda del horario."""
    grupos = {}
    for fila in re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", pagina):
        celdas = re.findall(r"(?is)<td([^>]*)>(.*?)</td>", fila)
        if len(celdas) != 8:
            continue
        franja = limpiar(celdas[0][1])
        if not re.match(r"^\d{2}:\d{2}-\d{2}:\d{2}", franja):
            continue
        for i, (attrs, cuerpo) in enumerate(celdas[1:]):
            texto = limpiar(cuerpo)
            if not texto:
                continue
            partes = re.split(r"(?i)<br\s*/?>", cuerpo, maxsplit=1)
            grupo = limpiar(partes[0])
            estado = limpiar(partes[1]) if len(partes) > 1 else ""
            m = re.search(r"(\d+)\s*libre", estado, re.I)
            libres = int(m.group(1)) if m else 0
            if not m and "libre" in attrs.lower():
                libres = 1  # marcada como libre aunque no diga el número
            clave = f"{franja}|{DIAS[i]}|{grupo}"
            grupos[clave] = {
                "franja": franja,
                "dia": DIAS[i],
                "grupo": grupo,
                "estado": estado,
                "libres": libres,
            }
    return grupos


def telegram(texto):
    if not TOKEN or not CHAT_ID:
        log("!! Sin TELEGRAM_TOKEN / TELEGRAM_CHAT_ID, no se envía nada")
        return False
    datos = urllib.parse.urlencode(
        {
            "chat_id": CHAT_ID,
            "text": texto,
            "parse_mode": "HTML",
            "disable_web_page_preview": "false",
        }
    ).encode()
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    for intento in range(3):
        try:
            with urllib.request.urlopen(url, data=datos, timeout=20) as r:
                json.load(r)
            return True
        except Exception as e:  # noqa: BLE001
            log(f"!! Telegram falló ({intento + 1}/3): {e}")
            time.sleep(3)
    return False


def cargar_estado():
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def guardar_estado(estado):
    tmp = ESTADO.with_suffix(".tmp")
    tmp.write_text(json.dumps(estado, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(ESTADO)


def revisar(codigo, nombre, previo):
    pagina, url = descargar(codigo)
    actual = parsear(pagina)
    if not actual:
        log(f"[{nombre}] la página no trajo horario (¿caída o cambio de formato?)")
        return previo, []

    novedades = []
    for clave, info in actual.items():
        antes = previo.get(clave, {}).get("libres", 0) if previo else 0
        if info["libres"] > antes:
            novedades.append((info, antes))

    nuevo = {k: v for k, v in actual.items()}
    if novedades and previo:
        lineas = [f"🎾 <b>¡PLAZAS EN {html.escape(nombre)}!</b>", ""]
        for info, antes in novedades:
            lineas.append(
                f"• <b>{html.escape(info['grupo'])}</b> — {html.escape(info['dia'])} "
                f"{html.escape(info['franja'])}\n  {html.escape(info['estado'])}"
                + (f" (antes {antes})" if antes else "")
            )
        lineas += ["", f'<a href="{html.escape(url)}">Apuntarse ahora</a>']
        telegram("\n".join(lineas))
        log(f"[{nombre}] AVISO enviado: {[i['grupo'] for i, _ in novedades]}")
    elif novedades:
        libres = [i["grupo"] for i, _ in novedades]
        log(f"[{nombre}] estado inicial, plazas libres ya existentes: {libres}")

    return nuevo, novedades


def main():
    if not TOKEN or not CHAT_ID:
        print(
            "Faltan TELEGRAM_TOKEN y/o TELEGRAM_CHAT_ID.\n"
            "Créalos con @BotFather y expórtalos antes de arrancar.",
            file=sys.stderr,
        )
        return 1

    una_vez = "--once" in sys.argv
    estado = cargar_estado()
    primera = not estado
    log(f"Vigilando {', '.join(ACTIVIDADES.values())} cada {INTERVALO}s")

    if primera and not una_vez:
        telegram(
            "✅ Vigilante UPV en marcha.\n"
            f"Compruebo {', '.join(ACTIVIDADES.values())} cada {INTERVALO}s "
            "y te aviso en cuanto se libere una plaza."
        )

    fallos = 0
    while True:
        for codigo, nombre in ACTIVIDADES.items():
            try:
                previo = estado.get(codigo)
                estado[codigo], _ = revisar(codigo, nombre, previo)
                fallos = 0
            except Exception as e:  # noqa: BLE001
                fallos += 1
                log(f"[{nombre}] error: {e}")
                if fallos == 20:
                    telegram(f"⚠️ Llevo 20 fallos seguidos consultando la UPV: {e}")
        guardar_estado(estado)
        if una_vez:
            return 0
        time.sleep(INTERVALO + random.uniform(0, 3))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("Parado a mano")
