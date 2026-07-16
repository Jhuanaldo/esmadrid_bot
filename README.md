# esmadrid_bot

Bot de Telegram que consulta la agenda cultural de Madrid ([esmadrid.com](https://www.esmadrid.com/opendata/agenda_v1_es.xml)) y envía informes personalizados a los usuarios según sus preferencias de categorías, fechas y frecuencia.

## Funcionamiento

- **08:00** (hora española): Descarga y filtra el XML, guardando solo eventos con fecha de fin posterior a hoy.
- **10:00** (hora española): Envía el informe a cada usuario según su configuración.
- **`/report`**: Consulta el informe al instante en cualquier momento.

## Comandos

| Comando | Descripción |
|---|---|
| `/start` | Configuración inicial guiada |
| `/settings` | Modificar configuración existente |
| `/config` | Ver resumen de configuración actual |
| `/report` | Recibir el informe ahora |

## Configuración de usuario

Cada usuario puede elegir:

1. **Categorías y subcategorías** (Música, Exposiciones, Teatro, etc.)
2. **Rango de tiempo** (esta semana, 2 semanas, 3 semanas)
3. **Frecuencia de envío** (diario, lun-mié-vie, solo lunes)

## Instalación

```bash
pip install -r requirements.txt
export ESMADRID_BOT_TOKEN=tu_token_de_telegram
python3 bot.py
```