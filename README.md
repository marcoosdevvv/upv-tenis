# Vigilante de plazas — Actividades deportivas UPV

Avisa por Telegram en cuanto una clase de tenis pasa de "Completo" a tener plazas libres.

## Dos capas

- **GitHub Actions** (`.github/workflows/vigila.yml`): comprueba cada 5 minutos, siempre encendido.
- **Servicio local en el Mac** (`arrancar.sh` + launchd): comprueba cada 60 s mientras el Mac esté despierto.

Ambas avisan al mismo chat de Telegram, así que puede llegar un aviso duplicado.

## Configuración

Local: copia tus credenciales en `config.sh` (no se sube al repo).
En GitHub: secretos `TELEGRAM_TOKEN` y `TELEGRAM_CHAT_ID`.

## Comandos

    tail -f vigila.log                                    # ver actividad local
    launchctl bootout gui/$(id -u)/com.marcos.upv-tenis   # parar el servicio local
