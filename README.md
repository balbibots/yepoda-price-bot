# Vigilante de precio — Yepoda Advent Calendar 2026

Comprueba cada 6 horas el precio del calendario de adviento de Yepoda y te
escribe por Telegram cuando baja de **100 €**, cuando se agota, o cuando
vuelve a haber stock.

No manda avisos de "sigue todo igual" en cada ejecucion: esta en silencio
hasta que pasa algo real. La unica excepcion deliberada es un **"sigo vivo"
una vez por semana**, para que sepas que el bot sigue activo aunque no haya
novedades. Si el propio bot se rompe, eso tambien se avisa (ver mas abajo).

- **Producto:** https://yepoda.es/products/the-yepoda-advent-calendar-2026
- **Precio cuando se monto esto:** 169,00 € (PVP marcado: 475 €)
- **Umbral de aviso:** 100 €

## Como lee el precio

Yepoda funciona sobre Shopify, y Shopify expone cada producto en formato JSON
si le añades `.js` al final de la URL:

```
https://yepoda.es/products/the-yepoda-advent-calendar-2026.js
```

```json
{ "title": "The Yepoda Advent Calendar", "price": 16900, "available": true }
```

`price` viene **en centimos**, por eso el script divide entre 100.

Esto es importante: **no estamos haciendo scraping de HTML**. No dependemos de
ninguna clase CSS ni de la maquetacion. Aunque rediseñen la web entera, este
endpoint seguira devolviendo lo mismo. Es la diferencia entre un bot que dura
años y uno que se rompe en la primera actualizacion de la tienda.

## Montarlo (unos 10 minutos)

### 1. Crear el bot de Telegram

1. Abre Telegram y busca **@BotFather**.
2. Envia `/newbot` y sigue las instrucciones (nombre y usuario, que debe
   acabar en `bot`).
3. Te dara un token con esta pinta: `7123456789:AAH...`. **Guardalo**, es la
   contraseña de tu bot.

### 2. Conseguir tu chat id

1. Busca tu bot recien creado en Telegram y pulsa **Start**.
   (Sin este paso el bot no puede escribirte: Telegram no deja que un bot
   inicie conversaciones.)
2. Escribele cualquier cosa, por ejemplo "hola".
3. Abre en el navegador, sustituyendo `<TOKEN>`:
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
4. Busca `"chat":{"id":123456789` — ese numero es tu `TELEGRAM_CHAT_ID`.

### 3. Probarlo en tu ordenador

En PowerShell:

```powershell
$env:TELEGRAM_BOT_TOKEN="tu_token"
$env:TELEGRAM_CHAT_ID="tu_chat_id"
python check_price.py --test
```

Si te llega el mensaje de prueba, ya esta conectado. Ahora una ejecucion real:

```powershell
python check_price.py
```

### 4. Ponerlo en automatico con GitHub Actions

1. Crea un repositorio en GitHub y sube estos archivos.
2. Ve a **Settings → Secrets and variables → Actions → New repository secret**
   y crea dos secretos:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
3. Entra en la pestaña **Actions**, elige *Vigilar precio* y pulsa
   **Run workflow** para probarlo a mano.

A partir de ahi se ejecuta solo cada 6 horas, con tu ordenador apagado.

> **Repo privado o publico:** los publicos tienen minutos ilimitados; los
> privados incluyen 2.000 min/mes gratis. Este bot gasta unos 15 segundos por
> ejecucion (~30 min al mes), asi que cabe de sobra en cualquiera de los dos.

## Ajustes

Se cambian en `.github/workflows/check-price.yml`, en el bloque `env:`.

| Variable | Por defecto | Para que sirve |
|---|---|---|
| `THRESHOLD_EUR` | `100` | Precio por debajo del cual quieres el aviso |
| `PRODUCT_URL` | el calendario | Sirve para **cualquier** producto de Shopify |
| `NOTIFY_ON_ANY_CHANGE` | `false` | `true` avisa de todo cambio, no solo del umbral |
| `HEARTBEAT_DAYS` | `7` | Cada cuantos dias mandar el "sigo vivo" |

Para cambiar el umbral a, por ejemplo, 120 €, edita esa linea:

```yaml
          THRESHOLD_EUR: "120"
```

Y la frecuencia, en `cron`:

```yaml
- cron: "17 */2 * * *"   # cada 2 horas
- cron: "17 8 * * *"     # una vez al dia, a las 8:17 UTC
```

## Que te avisa (y que no)

| Evento | ¿Avisa? |
|---|---|
| El precio baja de 100 € | ✅ Una vez, hasta que vuelva a subir |
| El precio sigue igual, ejecucion tras ejecucion | ❌ Silencio total |
| El producto se agota | ✅ Una vez, hasta que vuelva a haber stock |
| Vuelve a haber stock | ✅ |
| Ha pasado una semana sin ningun aviso | ✅ Un "sigo vigilando" con el precio y stock actual |
| El bot no puede leer la web (esta rota, timeout...) | ✅ Maximo 1 vez / 24 h |

La primera vez que se ejecuta el bot **no** avisa de disponibilidad ni manda
el primer heartbeat (no hay nada previo con que comparar): solo guarda el
punto de partida y el contador de la semana empieza a correr desde ahi. Si en
ese primer arranque el precio ya esta por debajo del umbral, si que avisa.

Si justo el dia que toca el heartbeat tambien cambia el precio o el stock,
solo recibes **el aviso real** (no un heartbeat redundante el mismo dia) — el
"sigo vivo" se pospone a la siguiente vez que no haya novedades.

## Detalles que hacen que esto no te falle

**No repite avisos.** `state.json` recuerda si ya te aviso. Si el precio baja
de 100 € no recibes un mensaje cada 6 horas: recibes uno. Si vuelve a subir,
el aviso se rearma solo para la proxima bajada. Lo mismo con el stock.

**Te avisa si se rompe.** Este es el fallo clasico de los bots caseros: la web
cambia, el bot deja de leer el precio, y tu interpretas el silencio como "no ha
bajado". Aqui, si no puede leer el precio, te manda un aviso de error (como
mucho uno cada 24 h, para no ser pesado).

**No pierde avisos.** Si el precio baja pero Telegram falla en ese momento, el
aviso *no* se marca como enviado y se reintenta en la siguiente ejecucion.

**No martillea la web.** Cada 6 horas son 4 peticiones al dia. Si bajas mucho
la frecuencia te arriesgas a que te bloqueen la IP, y tampoco ganas nada.

## Un aviso sobre los cron de GitHub

- Los `schedule` de GitHub Actions **no son puntuales**: pueden retrasarse
  bastante si la plataforma esta cargada. Para vigilar precios da igual.
- GitHub **desactiva los workflows programados** en repos sin actividad
  durante 60 dias. Te avisa por email; basta con reactivarlo desde Actions.
  Como este bot hace commit de `state.json` cuando el precio cambia, suele
  haber actividad suficiente, pero no lo des por hecho.

## Estructura

```
check_price.py                      el script (solo libreria estandar)
.github/workflows/check-price.yml   la programacion cada 6 horas
state.json                          memoria entre ejecuciones (se crea solo)
```
