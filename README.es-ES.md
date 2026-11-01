

# Social-Hunt

> Agregador OSINT autoalojado — descubrimiento de nombres de usuario, inteligencia de filtraciones, búsqueda inversa de imágenes, restauración facial con IA, registros de votantes, Google dorks, notas seguras y más. Incluye un panel web pulido y una CLI.

![Dashboard](assets/screenshots/dashboard.png)

---

## Tabla de Contenidos

- [Características](#features)
- [Capturas de pantalla](#screenshots)
- [Arquitectura](#architecture)
- [Inicio rápido](#quick-start)
  - [Docker (recomendado)](#docker-recommended)
  - [Docker + proxy inverso integrado](#docker--bundled-reverse-proxy-nginx-or-apache)
  - [Docker + SSL](#docker--ssl-nginx--iopaint)
  - [Instalación manual](#manual-install)
  - [Configuración para Raspberry Pi 5](#raspberry-pi-5-setup)
- [Uso de la CLI](#cli-usage)
- [Configuración](#configuration)
- [Seguridad de inicio de sesión](#login-security)
- [Guías de características](#feature-guides)
  - [Búsqueda de nombres de usuario](#username-search)
  - [Búsqueda en filtraciones](#breach-search)
  - [OSINT de imágenes inversas](#reverse-image-osint)
  - [Google Dorks](#google-dorks)
  - [Registros de votantes](#voter-records)
  - [Desenmascaramiento con IA](#ai-demasking)
  - [Notas seguras](#secure-notes)
  - [Historial](#history)
  - [Sistema de plugins](#plugin-system)
  - [Modo demostración](#demo-mode)
  - [Soporte para Tor / Darkweb](#tor--darkweb-support)
- [Estructura del proyecto](#project-structure)
- [Documentación](#documentation)
- [Colaboradores](#contributors)
- [Aspectos legales y éticos](#legal-and-ethics)

---

## Características

| Característica | Descripción |
|---|---|
| **Búsqueda de nombres de usuario** | Escaneo de presencia en múltiples plataformas a través de cientos de sitios usando packs de proveedores en YAML + Python. Búsqueda facial mejorada opcional mediante imágenes de referencia subidas. |
| **Búsqueda en filtraciones** | Búsqueda de correos, nombres de usuario, IPs y teléfonos en bases de datos de filtraciones indexadas — HIBP, BreachVIP, Snusbase, LeakCheck. Detecta automáticamente el tipo de entrada. |
| **OSINT de imágenes inversas** | Genera enlaces de búsqueda listos para usar en Google Lens, Bing Visual Search, Yandex Images, TinEye y más. Soporta entrada por URL y carga de archivos. |
| **Google Dorks** | Biblioteca integrada de 100 + plantillas de operadores de búsqueda de Google categorizadas para dominios, nombres, usuarios, correos y empresas. Búsqueda con un clic y exportación masiva. |
| **Registros de votantes** | Enlaces directos a 20 + portales oficiales de registro de votantes de EE. UU. (AZ, CO, FL, GA, IL, KS, KY, MD, MI, MN, NJ, NY, NC, OH, OK, OR, PA, SC, TX, UT, VA, WA, WI). |
| **Desenmascaramiento con IA** | Restauración facial y eliminación de mosaicos vía API en la nube de Replicate, servidor interactivo de IOPaint o DeepMosaic automatizado — todo desde el panel. |
| **Notas seguras** | Bóveda de notas cifrada con AES-GCM bloqueada por una contraseña maestra. Las notas nunca abandonan tu navegador sin cifrar. Exportación / importación como JSON cifrado. |
| **Historial** | Registro persistente de todas las búsquedas, consultas de imágenes inversas y trabajos de desenmascaramiento con reapertura y reejecución rápida. |
| **Sistema de plugins** | Recarga en caliente de packs de proveedores en YAML y Python. Cargador web opcional. Instala packs de la comunidad desde el directorio de plugins dentro de la app. |
| **Panel** | Estado del sistema en vivo, estadísticas de búsqueda, consejos OSINT rotativos y enlaces de acceso rápido a búsquedas recientes. |
| **Temas** | Múltiples temas de color integrados (oscuro predeterminado, Tokyo Night, Cobalt) — se aplican al instante sin recargar la página. |
| **Modo demostración** | Censura resultados sensibles para compartir pantallas y demostraciones de forma segura. Actívelo en Configuración. |
| **Soporte Tor / Onion** | Enruta solicitudes a través de un proxy SOCKS para packs de proveedores `.onion` con separación de túnel opcional. |
| **Autenticación por token** | Un único token de administrador protege todo el panel. Modo de bootstrap para la configuración inicial. hCaptcha opcional. |

---

## Capturas de pantalla

| | |
|---|---|
| ![Login](assets/screenshots/login.png) **Inicio de sesión** | ![Dashboard](assets/screenshots/dashboard.png) **Panel** |
| ![Search](assets/screenshots/search-results.png) **Búsqueda de usuarios** | ![Breach](assets/screenshots/breach-search.png) **Búsqueda en filtraciones** |
| ![Reverse](assets/screenshots/reverse-image.png) **Imagen inversa** | ![Demask](assets/screenshots/demasking.png) **Desenmascaramiento IA** |
| ![History](assets/screenshots/history.png) **Historial** | ![Notes](assets/screenshots/secure-notes.png) **Notas seguras** |
| ![Plugins](assets/screenshots/plugins.png) **Plugins** | ![Settings](assets/screenshots/settings.png) **Configuración** |

---

## Arquitectura

- **Backend:** FastAPI + motor de escaneo asíncrono httpx (Python 3.11+)
- **Frontend:** HTML / CSS / JS nativo — sin frameworks pesados, carga rápida
- **Motor principal:** Concurrencia asíncrona con heurísticas por proveedor y detección de estado
- **Almacenamiento:** Archivos planos JSON para configuraciones y resultados de trabajos; notas cifradas en localStorage del navegador
- **Servicios opcionales:** Replicate (IA en la nube), IOPaint (reconstrucción interactiva), DeepMosaic (eliminación automatizada de mosaicos)

---

## Inicio rápido

### Docker (recomendado)

```bash
git clone https://github.com/AfterPacket/Social-Hunt.git
cd Social-Hunt/docker
docker compose up -d --build
```

Abre `http://localhost:8000`. Establece tu token de administrador en la página **Token**.

---

### Docker + proxy inverso integrado (nginx o apache)

Expone la aplicación en el puerto 80:

```bash
cd Social-Hunt/docker

# Nginx
docker compose --profile nginx up -d --build

# Apache
docker compose --profile apache up -d --build
```

Abre `http://localhost/`.

Para incluir los trabajadores de IA (IOPaint + DeepMosaic) junto al proxy:

```bash
docker compose --profile nginx --profile ai up -d --build
```

---

### Docker + SSL (nginx + trabajadores de IA)

Terminación HTTPS. Social-Hunt sirve `/`; los trabajadores de IA (IOPaint, DeepMosaic) corren en contenedores hermanos y se alcanzan por la red interna (`IOPAINT_URL`, `DEEPMOSAIC_URL`). La interfaz web de IOPaint se abre directamente en el puerto `8080` desde el panel (origen separado) — no se enruta bajo una subruta.

```bash
cd Social-Hunt/docker
python setup_ssl.py
docker compose --profile certbot run --rm --service-ports certbot
docker compose --profile ssl up -d
```

Abre `https://tu-dominio`.

---

### Instalación manual

```bash
git clone https://github.com/AfterPacket/Social-Hunt.git
cd Social-Hunt
python -m pip install -r requirements.txt
# Opcional — soporte Tor/SOCKS:
python -m pip install httpx[socks]
python run.py
```

Abre `http://localhost:8000`.

Para una guía detallada (virtualenv, tokens, proxy inverso), consulta [`README_RUN.md`](README_RUN.md).

---

### Configuración para Raspberry Pi 5

Social-Hunt funciona en Raspberry Pi 5 (Raspberry Pi OS Bookworm, 64-bit). DeepMosaic no se recomienda en Pi debido a limitaciones de almacenamiento y cómputo — todas las demás características funcionan.

El Python del sistema por defecto en Bookworm es 3.11+, lo cual es válido, pero `pip install -r requirements.txt` fallará por problemas de compatibilidad de Pillow / dlib con versiones recientes de setuptools. La solución es usar **pyenv** para fijar Python 3.11.9.

#### 1. Instalar dependencias de compilación

```bash
sudo apt update
sudo apt install -y build-essential curl git \
  libssl-dev zlib1g-dev libbz2-dev libreadline-dev \
  libsqlite3-dev libffi-dev libncursesw5-dev xz-utils \
  tk-dev libxml2-dev libxmlsec1-dev liblzma-dev
```

#### 2. Instalar pyenv

```bash
curl https://pyenv.run | bash
```

Agrega a `~/.bashrc`:

```bash
export PYENV_ROOT="$HOME/.pyenv"
export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"
```

Luego:

```bash
source ~/.bashrc
```

#### 3. Instalar Python 3.11.9

```bash
pyenv install 3.11.9
pyenv global 3.11.9
python --version  # debería mostrar Python 3.11.9
```

#### 4. Crear venv e instalar dependencias

```bash
cd Social-Hunt
python -m venv venv
source venv/bin/activate
pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

#### 5. Ejecutar

```bash
python run.py
```

Abre `http://<ip-pi>:8000`.

#### 6. Ejecutar como servicio systemd (opcional)

```bash
sudo cp systemd/social-hunt.service.example /etc/systemd/system/social-hunt.service
# Edita el archivo y establece las rutas WorkingDirectory y ExecStart
sudo systemctl daemon-reload
sudo systemctl enable --now social-hunt
```

#### Limitaciones conocidas en Pi

- DeepMosaic requiere descargas de modelos grandes y mucho cómputo — omítelo en Pi.
- IOPaint puede ejecutarse en CPU pero es lento; usa la API de Replicate en su lugar.
- La coincidencia facial (`dlib`) se compila desde el código fuente en la primera instalación — esto lleva unos minutos en Pi.

---

## Uso de la CLI

```bash
python -m social_hunt.cli --help

# Búsqueda de nombres de usuario
python -m social_hunt.cli search <usuario>

# Búsqueda con proveedores específicos
python -m social_hunt.cli search <usuario> --providers github_api,reddit_json

# Exportar resultados a JSON
python -m social_hunt.cli search <usuario> --output resultados.json
```

---

## Configuración

### Archivo de configuración

La configuración se almacena en `data/settings.json` y se gestiona desde la página **Configuración** del panel. También pueden establecerse mediante variables de entorno (que tienen prioridad).

| Clave | Descripción |
|---|---|
| `admin_token` | Token de acceso al panel (mín. 20 caracteres) |
| `hibp_key` | Clave API de Have I Been Pwned |
| `snusbase_key` | Clave API de Snusbase |
| `leakcheck_key` | Clave API de LeakCheck |
| `breachvip_key` | Clave API de BreachVIP |
| `replicate_key` | Clave API de Replicate (desenmascaramiento IA) |
| `public_url` | URL base de la instancia (usada en exportaciones) |
| `theme` | Tema de color de la UI (`default`, `tokyo`, `cobalt`) |
| `demo_mode` | Censurar salida sensible (`true` / `false`) |

### Variables de entorno

Toda la configuración puede establecerse como variables de entorno (útil para Docker / CI):

| Variable | Descripción |
|---|---|
| `SOCIAL_HUNT_PLUGIN_TOKEN` | Anula `admin_token` de la configuración |
| `SOCIAL_HUNT_HOST` | Dirección de enlace (predeterminado `0.0.0.0`) |
| `SOCIAL_HUNT_PORT` | Puerto (predeterminado `8000`) |
| `SOCIAL_HUNT_RELOAD` | Recarga en caliente para desarrollo (`1` / `0`) |
| `SOCIAL_HUNT_SETTINGS_PATH` | Ruta personalizada para `settings.json` |
| `SOCIAL_HUNT_JOBS_DIR` | Ruta personalizada para almacenamiento de resultados |
| `SOCIAL_HUNT_ENABLE_TOKEN_BOOTSTRAP` | Permitir configuración inicial de token vía UI (`1`) |
| `SOCIAL_HUNT_BOOTSTRAP_SECRET` | Secreto seguro para el endpoint de bootstrap |
| `SOCIAL_HUNT_ENABLE_WEB_PLUGIN_UPLOAD` | Habilitar carga de plugins vía panel (`1`) |
| `SOCIAL_HUNT_FACE_AI_URL` | URL del endpoint propio de IA facial |
| `HCAPTCHA_SECRET` | Secreto del servidor hCaptcha (habilita captcha en login) |
| `HCAPTCHA_SITEKEY` | Clave del sitio hCaptcha (enviada al frontend) |

---

## Seguridad de inicio de sesión

### Limitación de solicitudes

El endpoint de inicio de sesión tiene limitación progresiva integrada:

- **5 intentos fallidos** → bloqueo de 1 minuto
- **10 intentos fallidos** → bloqueo de 5 minutos
- **20+ intentos fallidos** → bloqueo de 15 minutos

El estado de bloqueo se reinicia con un inicio de sesión exitoso. Todos los intentos fallidos se registran en la consola del servidor.

### hCaptcha (opcional)

Añade protección contra bots al formulario de inicio de sesión:

1. Regístrate en [hcaptcha.com](https://hcaptcha.com) y crea un sitio.
2. Establece `HCAPTCHA_SECRET` y `HCAPTCHA_SITEKEY` en tu entorno o `settings.json`.
3. Reinicia — la página de inicio de sesión mostrará automáticamente el widget de hCaptcha.

---

## Guías de características

### Búsqueda de nombres de usuario

Escanea cientos de plataformas sociales y servicios en busca de un nombre de usuario usando proveedores definidos en YAML.

**Cómo usar:**
1. Introduce el nombre de usuario objetivo (no hace falta el prefijo `@`).
2. Selecciona proveedores — usa los interruptores **Todos** / **Ninguno** o elige individualmente.
3. Opcionalmente, activa **Búsqueda facial mejorada** y sube fotos de referencia.
4. Haz clic en **Iniciar investigación**.

Los resultados muestran la URL del perfil, nombre de visualización, conteo de seguidores, fragmentos de biografía y (si la búsqueda facial está habilitada) una puntuación de similitud. Exporta como JSON o CSV.

Los **packs de proveedores** en `plugins/providers/` amplían la cobertura: redes sociales, foros, plataformas de juegos, redes profesionales, sitios Tor, etc.

---

### Búsqueda en filtraciones

Busca en filtraciones de datos indexadas direcciones de correo, nombres de usuario, IPs, números de teléfono y patrones comodín.

**Proveedores soportados:**

| Proveedor | Tipos de entrada | Notas |
|---|---|---|
| **HIBP** (Have I Been Pwned) | Correo | Requiere clave API |
| **BreachVIP** | Correo, usuario, IP, nombre, teléfono | Requiere clave API |
| **Snusbase** | Correo, usuario, IP, nombre, hash | Requiere clave API |
| **LeakCheck** | Correo, usuario | Requiere clave API |

**Ejemplos de detección automática de entrada:**

| Entrada | Detectado como |
|---|---|
| `usuario@ejemplo.com` | Correo |
| `127.0.0.1` | Dirección IP |
| `juan.perez@*.com` | Correo comodín |
| `Juan A Pérez` | Nombre |
| `0000000000` | Número de teléfono |
| `juan_perez` | Nombre de usuario |

Los resultados se muestran por proveedor con campos crudos de la filtración, conteo de registros y exportación CSV.

**Ejemplo — añadir una clave de Snusbase:**

```
Configuración → Claves API → snusbase_key → pegar clave → Guardar
```

---

### OSINT de imágenes inversas

Genera enlaces de búsqueda con un clic para una URL de imagen dada o un archivo subido.

**Motores soportados:**
- Google Lens
- Bing Visual Search
- Yandex Images
- TinEye
- Google (estándar)
- Karma Decay (Reddit)
- IQDB (anime/ilustración)
- SauceNAO

**Uso:** Pega una URL de imagen o arrastra y suelta un archivo — la aplicación lo sube, genera una URL temporal y construye enlaces para cada motor de búsqueda.

---

### Google Dorks

Una biblioteca integrada de 100+ consultas de operadores de búsqueda de Google listas para usar en múltiples categorías.

**Categorías incluidas:**
- Enumeración de sitios y dominios
- Descubrimiento de tipos de archivo (PDF, XLSX, DOCX, volcados SQL…)
- Descubrimiento de páginas de login / paneles de admin
- Exposición de cámaras y dispositivos IoT
- Búsquedas de correo y usuario
- Presencia en redes sociales
- Exposición de código y claves API
- Enumeración de subdominios
- Búsqueda de personas / nombres
- Inteligencia de empresas

**Cómo usar:**
1. Introduce tu objetivo (dominio, nombre, usuario o empresa).
2. Selecciona un filtro de categoría (o déjalo como **Todas**).
3. Haz clic en **Generar Dorks**.
4. Haz clic en **Buscar** en cualquier fila para abrirla en Google, o usa **Copiar todo** / **Descargar .txt** para uso masivo.

---

### Registros de votantes

Un directorio curado de portales oficiales de consulta de registro de votantes por estado en EE. UU.

**Estados soportados (20+):**

AZ · CO · FL · GA · IL · KS · KY · MD · MI · MN · NJ · NY · NC · OH · OK · OR · PA · SC · TX · UT · VA · WA · WI

Cada tarjeta muestra el nombre del estado, el dominio del portal y un enlace directo a la herramienta oficial de consulta de votantes de ese estado. Todos los portales son operados por oficinas electorales gubernamentales estatales y proporcionan datos de registro de votantes de acceso público.

> **Nota:** Todos los portales estatales de votantes requieren que ingreses los detalles directamente en su sitio web — son aplicaciones renderizadas por JavaScript que no admiten precarga externa. Haz clic en **Abrir portal** en cualquier tarjeta de estado para ir directamente a la herramienta oficial.

> **Legal:** Los datos de registro de votantes solo deben utilizarse con fines legales, incluida la administración electoral, actividades políticas, investigación académica y periodismo. La solicitud comercial y el acoso están prohibidos por leyes estatales y federales.

---

### Desenmascaramiento con IA

Elimina la censura con mosaicos y restaura caras usando tres motores diferentes.

#### API de Replicate (nube, recomendado)

Utiliza modelos de vanguardia alojados en [Replicate](https://replicate.com). Requiere una clave API de Replicate.

1. Añade `replicate_key` en Configuración.
2. Ve a **Desenmascaramiento → Subir** una imagen.
3. Selecciona el modo (**Desmosaizar** o **Restaurar**), modelo y calidad.
4. Haz clic en **Procesar** — el resultado aparece en la app con opción de descarga.

#### IOPaint (interactivo)

Ejecuta un servidor local de [IOPaint](https://github.com/Sanster/IOPaint) de reconstrucción accesible desde el panel.

1. Ve a **Desenmascaramiento → Reconstrucción IOPaint**.
2. Selecciona modelo y dispositivo (CPU / CUDA / MPS).
3. Haz clic en **Iniciar servidor** — luego **Abrir IOPaint** para usar el lienzo interactivo.
4. Haz clic en **Detener servidor** cuando termines.

#### DeepMosaic (automatizado)

Eliminación automatizada de mosaicos usando modelos locales de [DeepMosaic](https://github.com/HypoX64/DeepMosaic).

1. Descarga modelos: `python download_deepmosaic_models.py`
2. Ve a **Desenmascaramiento → DeepMosaic**, sube imagen/video, configura y procesa.
3. Descarga el resultado directamente.

#### Autoalojado (endpoint personalizado)

Apunta Social-Hunt a tu propio servicio de restauración facial:

```bash
SOCIAL_HUNT_FACE_AI_URL=http://tu-host-ia:puerto/restaurar
```

Formato esperado de solicitud/respuesta:

```json
// POST con multipart/form-data: { "file": <imagen>, "strength": 0.5 }
// Respuesta: { "image": "<resultado-codificado-en-base64>" }
```

---

### Notas seguras

Una bóveda de notas cifrada de extremo a extremo integrada en el panel. Las notas se almacenan en `localStorage` de tu navegador — nunca abandonan tu dispositivo sin cifrar.

**Cifrado:** AES-256-GCM con una clave derivada por PBKDF2 desde tu contraseña maestra (310,000 iteraciones, SHA-256).

**Características:**
- Crea, edita y elimina notas con títulos y contenido libre.
- Bloquear bóveda — requiere la contraseña maestra para volver a abrirla.
- **Exportar** bóveda a un archivo JSON cifrado para respaldo.
- **Importar** bóveda desde un archivo exportado previamente.
- Las notas guardadas en la bóveda pueden buscarse en todo el contenido.

> **Importante:** Si olvidas tu contraseña maestra, tus notas no podrán recuperarse. No existe mecanismo de reinicio — esto es por diseño.

---

### Historial

La pestaña Historial muestra un registro persistente de:

- **Búsquedas** — usuario, conteo de proveedores, conteo de resultados, marca de tiempo y estado.
- **Consultas de imágenes inversas** — miniatura de vista previa de imagen y enlaces generados.
- **Trabajos de desenmascaramiento** — vistas previas de imagen original y resultado.

Haz clic en cualquier entrada para volver a abrir los resultados completos. Limpia categorías individuales con el icono de papelera.

---

### Sistema de plugins

Amplía Social-Hunt con packs de proveedores adicionales sin modificar el código principal.

**Formatos de packs de proveedores:**

| Formato | Ubicación | Descripción |
|---|---|---|
| YAML (`.yaml`) | `plugins/providers/` | Patrones de URL declarativos — más rápidos de escribir |
| Python (`.py`) | `plugins/python/providers/` | Código asíncrono completo — para APIs, auth, análisis complejo |

**Instalar un plugin:**

```bash
# Coloca un archivo YAML en:
plugins/providers/mi_pack.yaml

# Luego recarga desde el panel:
Configuración → Proveedores → Recargar
```

Si `SOCIAL_HUNT_ENABLE_WEB_PLUGIN_UPLOAD=1` está establecido, también puedes subir archivos `.yaml`, `.py` o `.zip` directamente desde **Plugins** en el panel.

**Escribir un proveedor YAML (ejemplo mínimo):**

```yaml
providers:
  - name: sitio_ejemplo
    url: "https://ejemplo.com/usuarios/{usuario}"
    error_type: status_code
    error_code: 404
```

Consulta [`PLUGINS.md`](PLUGINS.md) para la especificación completa de proveedores y la API de proveedores Python.

---

### Modo demostración

Censura datos sensibles en los resultados de búsqueda — útil para compartir pantallas, demos y presentaciones.

**Interruptor:** Configuración → Modo demostración → Habilitar / Deshabilitar → Guardar

Cuando está activo, aparece una insignia roja de **MODO DEMO** en la barra superior. Correos, IPs, nombres y otros PII se reemplazan con asteriscos en toda la salida.

---

### Soporte para Tor / Darkweb

Enruta solicitudes de proveedores a través de un proxy SOCKS para alcanzar sitios `.onion`.

#### Requisitos previos

```bash
# Instalar Tor
sudo apt install tor

# Instalar soporte SOCKS para httpx
pip install httpx[socks]
```

#### Configuración

Agrega a tu `settings.json` o entorno:

```json
{
  "socks_proxy": "socks5://127.0.0.1:9050",
  "tor_enabled_providers": ["proveedor_onion_ejemplo"]
}
```

O establece globalmente para todos los proveedores:

```json
{
  "proxy": "socks5://127.0.0.1:9050"
}
```

#### Proxy clearnet (opcional)

Para enrutar todo el tráfico (incluido clearnet) a través del proxy:

```bash
HTTPS_PROXY=socks5://127.0.0.1:9050 python run.py
```

Consulta `plugins/providers/tor_pack.yaml` para ejemplos de definiciones de proveedores `.onion`.

---

## Estructura del proyecto

```
Social-Hunt/
├── api/
│   ├── main.py                # Backend FastAPI — todos los endpoints
│   └── settings_store.py      # Persistencia de configuración
├── social_hunt/
│   ├── engine.py              # Motor de escaneo asíncrono
│   ├── registry.py            # Registro de proveedores
│   ├── providers/             # Módulos de proveedores integrados
│   ├── addons/                # Módulos adicionales (coincidencia facial, etc.)
│   └── ...
├── web/
│   ├── index.html             # Cascara de la app
│   ├── app.js                 # Todo el JS del frontend (~4000 líneas)
│   ├── styles.css             # Estilos globales + temas
│   └── views/                 # Fragmentos HTML por vista
│       ├── dashboard.html
│       ├── search.html
│       ├── breach-search.html
│       ├── reverse.html
│       ├── google-dorks.html
│       ├── voter-records.html
│       ├── demask.html
│       ├── iopaint.html
│       ├── deepmosaic.html
│       ├── secure-notes.html
│       ├── history.html
│       ├── plugins.html
│       ├── settings.html
│       └── tokens.html
├── plugins/
│   ├── providers/             # Packs de proveedores YAML
│   └── python/providers/      # Packs de proveedores Python
├── docker/
│   ├── docker-compose.yml
│   ├── nginx.conf
│   ├── Dockerfile
│   └── ...
├── data/                      # Datos en tiempo de ejecución (gitignore)
├── run.py                     # Punto de entrada
├── providers.yaml             # Lista predeterminada de proveedores
└── requirements.txt
```

---

## Documentación

| Documento | Descripción |
|---|---|
| [`README.md`](README.md) | Este archivo — descripción completa de características y guía de configuración |
| [`README_RUN.md`](README_RUN.md) | Guía detallada de ejecución / despliegue |
| [`PLUGINS.md`](PLUGINS.md) | Guía de autoría de packs de proveedores |
| [`APACHE_SETUP.md`](APACHE_SETUP.md) | Configuración de proxy inverso Apache |
| [`NGINX_SETUP.md`](NGINX_SETUP.md) | Configuración de proxy inverso Nginx |
| [`docker/docs/`](docker/docs/) | Guías específicas de Docker (SSL, IOPaint, actualizaciones de dev) |
| [`docs/CHANGELOG.md`](docs/CHANGELOG.md) | Historial de lanzamientos |
| [`docs/CANARY.md`](docs/CANARY.md) | Declaración de warrant canario |
| [`SECURITY.md`](SECURITY.md) | Política de seguridad y divulgación responsable |

---

## Notas sobre proxy inverso (trabajadores de IA)

Al usar el perfil integrado de nginx o Apache, Social-Hunt sirve `/` y su API bajo `/sh-api/`. Los trabajadores de IA (IOPaint, DeepMosaic) corren en contenedores hermanos y el panel los alcanza por la red interna de docker vía `IOPAINT_URL` / `DEEPMOSAIC_URL` — **no** se enrutan a través de nginx.

La interfaz web de IOPaint es una SPA que asume servirse en la raíz del sitio, por lo que se abre directamente en su propio puerto (`http://<host>:8080/`) desde el panel en vez de bajo una subruta. Enrutarla bajo `/iopaint/` rompe sus llamadas internas a `/assets/` y `/api/`. Ver `FIXES.md` para el razonamiento completo.

- `/` → Social-Hunt (`social-hunt:8000`)
- `/sh-api/` → API de Social-Hunt (`social-hunt:8000`)
- WebUI de IOPaint → puerto directo `8080` (origen separado, sin proxy)
- API de DeepMosaic → puerto directo `8081` (sin proxy)

> **Importante:** Social-Hunt usa `/sh-api/` exclusivamente. No añadas una regla global `/api/` — colisiona con el namespace interno `/api/` de IOPaint.

---

## Entornos probados

| Entorno | Estado |
|---|---|
| Ubuntu 22.04 LTS (VPS) | ✅ Probado |
| Ubuntu 24.04 LTS (VPS) | ✅ Probado |
| Raspberry Pi 5 — RPi OS Bookworm 64-bit | ✅ Probado (ver configuración de Pi arriba) |
| macOS (Apple Silicon) | ✅ Probado |
| Windows 11 (Docker Desktop) | ✅ Probado |
| Debian 12 Bookworm (VPS) | ✅ Probado |

Otras imágenes basadas en Debian/Ubuntu deberían funcionar. Informa resultados en un issue o PR.

---

## Colaboradores

Gracias a todos los colaboradores que han hecho posible este proyecto. Consulta [`docs/CONTRIBUTORS.md`](docs/CONTRIBUTORS.md) para la lista completa.

Se agradecen pull requests, informes de errores, nuevos packs de proveedores y mejoras en la documentación. Lee [`SECURITY.md`](SECURITY.md) antes de reportar vulnerabilidades.

---

## Aspectos legales y éticos

Social-Hunt está diseñado exclusivamente para **investigación OSINT legal** — investigación de seguridad, periodismo, estudio académico y auditoría de privacidad personal. El desarrollador no aprueba ni permite:

- Acecho, acoso o abuso dirigido a cualquier individuo.
- Acceso no autorizado a cuentas, sistemas o datos privados.
- Uso en jurisdicciones o contextos donde estas herramientas estén restringidas.
- Extracción o agregación de datos que violen los Términos de Servicio de una plataforma.
- Venta comercial o redistribución de datos obtenidos mediante esta herramienta.
- Cualquier uso que viole leyes locales, nacionales o internacionales aplicables.

La característica de registros de votantes enlaza a portales gubernamentales oficiales. El uso de datos de registro de votantes está regulado por leyes estatales y federales — consulta las normativas correspondientes antes de usarlos.

**Eres únicamente responsable de cómo usas este software.**

---

*Social-Hunt se publica bajo la [Licencia GPL-3.0](LICENSE).*
