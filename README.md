# MNT-DRIVE - Subidor de Carpetas a Google Drive

## Descripción

MNT-DRIVE es una aplicación de escritorio desarrollada en Python con interfaz gráfica (PyQt5) que permite subir carpetas completas a Google Drive de manera eficiente y con seguimiento de progreso en tiempo real.

### Características Principales

- **Interfaz gráfica intuitiva**: Aplicación de escritorio con PyQt5
- **Subida múltiple**: Permite seleccionar múltiples carpetas para subir simultáneamente
- **Progreso en tiempo real**: Barras de progreso individuales para cada carpeta
- **Gestión de errores**: Reintentos automáticos en caso de fallos de conexión
- **Explorador de Drive**: Navegación completa por Google Drive (Mi unidad y Unidades compartidas)
- **Renombrado automático**: Renombra archivos MP4 y SRT para evitar conflictos
- **Subida concurrente**: Hasta 3 subidas simultáneas para optimizar el rendimiento

## Requisitos del Sistema

- Python 3.7 o superior
- Conexión a Internet
- Cuenta de Google con Google Drive habilitado

## Instalación y Configuración

### 1. Preparar el Entorno Virtual

```bash
# Crear entorno virtual
python -m venv venv

# Activar entorno virtual
# En Windows:
venv\Scripts\activate
# En Linux/Mac:
source venv/bin/activate
```

### 2. Instalar Dependencias

```bash
pip install PyQt5
pip install PyDrive2
pip install google-api-python-client
pip install python-dotenv
pip install requests
pip install oauth2client
```

### 3. Compilar el Programa (Opcional)

Para crear un ejecutable independiente de Windows:

```bash
# Instalar PyInstaller
pip install pyinstaller

# Compilar el programa
pyinstaller --onefile --noconsole MNT-DRIVE.py
```

**Opciones de compilación:**

- `--onefile`: Crea un solo archivo ejecutable
- `--noconsole`: No muestra la ventana de consola al ejecutar
- `--windowed`: Alternativa a --noconsole para aplicaciones GUI

El ejecutable se creará en la carpeta `dist/` con el nombre `MNT-DRIVE.exe`.

**Nota:** Asegúrate de que los archivos `client_secrets.json` y `credentials.txt` estén en el mismo directorio que el ejecutable compilado.

### 4. Configurar Credenciales de Google Drive

El programa requiere dos archivos de configuración:

#### Archivo `client_secrets.json`

Contiene las credenciales de la aplicación de Google Cloud:

```json
{
  "installed": {
    "client_id": "tu_client_id",
    "project_id": "tu_project_id",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_secret": "tu_client_secret",
    "redirect_uris": ["http://localhost"]
  }
}
```

#### Archivo `credentials.txt`

Se genera automáticamente después de la primera autenticación y contiene los tokens de acceso.

### 5. Configurar Google Cloud Console

1. Ve a [Google Cloud Console](https://console.cloud.google.com/)
2. Crea un nuevo proyecto o selecciona uno existente
3. Habilita la API de Google Drive
4. Crea credenciales OAuth 2.0 para aplicación de escritorio
5. Descarga el archivo `client_secrets.json` y colócalo en el directorio del proyecto

## Uso del Programa

### Ejecutar desde Código Fuente

```bash
# Activar entorno virtual
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Ejecutar el programa
python MNT-DRIVE.py
```

### Ejecutar desde el Ejecutable

- El programa compilado (`MNT-DRIVE.exe`)
- Los archivos de configuración necesarios (`client_secrets.json` y `credentials.txt`)

Para usar el ejecutable:

1. Compila el programa con `pyinstaller --onefile --noconsole MNT-DRIVE.py`
2. Asegúrate de que los archivos `client_secrets.json` y `credentials.txt` estén en el mismo directorio que el ejecutable
3. Ejecuta `MNT-DRIVE.exe`

## Instrucciones de Uso

### 1. Seleccionar Unidad de Google Drive

- Haz clic en "Seleccionar Unidad de Drive"
- Navega por "Mi unidad" o "Unidades compartidas"
- Selecciona la unidad donde quieres subir las carpetas

### 2. Seleccionar Carpetas Locales

- Haz clic en "Seleccionar" para elegir carpetas de tu computadora
- Puedes seleccionar múltiples carpetas
- Usa "Eliminar" para quitar carpetas de la lista

### 3. Elegir Carpeta de Destino

- Selecciona la carpeta de destino en Google Drive desde el menú desplegable
- Usa "Crear carpeta" para crear una nueva carpeta en Drive

### 4. Iniciar Subida

- Haz clic en "Subir Carpetas" para comenzar la transferencia
- El progreso se muestra en tiempo real con barras de progreso individuales
- Puedes cancelar todas las subidas desde la ventana de progreso

## Características Técnicas

### Gestión de Errores

- Reintentos automáticos en caso de fallos de conexión
- Manejo de límites de tasa de Google Drive
- Detección de pérdida de conexión

### Optimizaciones

- Subida concurrente (máximo 3 carpetas simultáneamente)
- Renombrado automático de archivos MP4 y SRT para evitar conflictos
- Cálculo de velocidad de transferencia y tiempo restante

### Seguridad

- Tokens de acceso seguros
- Refresh tokens para renovación automática
- Credenciales almacenadas localmente

## Estructura del Proyecto

```
RaspApp/
├── MNT-DRIVE.py          # Código fuente principal
├── client_secrets.json    # Credenciales de Google Cloud
├── credentials.txt        # Tokens de acceso (generado automáticamente)
├── README.md             # Este archivo
├── .gitignore           # Archivos ignorados por Git
└── WIN-exe.zip          # Ejecutable para Windows
```

## Solución de Problemas

### Error de Autenticación

- Verifica que `client_secrets.json` esté presente y sea válido
- Elimina `credentials.txt` para forzar una nueva autenticación
- Asegúrate de que la API de Google Drive esté habilitada

### Error de Conexión

- Verifica tu conexión a Internet
- El programa reintentará automáticamente en caso de fallos

### Límites de Google Drive

- El programa maneja automáticamente los límites de tasa
- Implementa backoff exponencial para reintentos

## Notas Importantes

- Los archivos `client_secrets.json` y `credentials.txt` contienen información sensible y no deben compartirse
- El programa está configurado para trabajar con archivos grandes y carpetas complejas
- Se recomienda tener una conexión estable a Internet para subidas grandes

---
