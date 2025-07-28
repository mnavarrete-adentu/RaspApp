import os
import subprocess
import re
from queue import Queue
from PyQt5 import QtCore, QtGui, QtWidgets
from PyQt5.QtCore import pyqtSignal, QObject, QThread
from dotenv import load_dotenv
import requests
import logging
from pydrive2.auth import GoogleAuth
from pydrive2.drive import GoogleDrive
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import io
import time

# Autenticación con Google Drive usando credenciales almacenadas
gauth = GoogleAuth()

# Asegúrate de solicitar el refresh token en modo offline
gauth.settings['get_refresh_token'] = True

# Intenta cargar las credenciales desde un archivo
gauth.LoadCredentialsFile("credentials.txt")

if not gauth.credentials or gauth.access_token_expired:
    if gauth.access_token_expired:
        try:
            gauth.Refresh()  # Renueva el token de acceso usando el refresh token
        except Exception as e:
            print(f"Error al renovar el token: {e}")
            gauth.LocalWebserverAuth()  # Reautentica si no se puede renovar el token
    else:
        # Si no hay credenciales, solicita la autenticación
        gauth.LocalWebserverAuth()  # Esto abrirá el navegador para autenticarse

    # Guarda las credenciales después de autenticarse
    gauth.SaveCredentialsFile("credentials.txt")

# Crea la instancia de Google Drive
drive = GoogleDrive(gauth)
# Crear el servicio para la API de Google Drive
service = build('drive', 'v3', credentials=gauth.credentials)

selected_folders = []
total_files = 0

progress_bars = {}
progress_labels = {}
upload_threads = {}

MAX_CONCURRENT_UPLOADS = 3



def check_internet_connection():
    try:
        response = requests.get("https://www.google.com", timeout=5)
        return response.status_code == 200
    except requests.ConnectionError:
        return False


class ProgressFile(io.FileIO):
    def __init__(self, path, mode, callback):
        super().__init__(path, mode)
        self.callback = callback
        self.length = os.path.getsize(path)
        self.total_read = 0

    def read(self, size=-1):
        chunk = super().read(size)
        self.total_read += len(chunk)
        self.callback(self.total_read, self.length)
        return chunk



class ProgressWindow(QtWidgets.QWidget):
    cancel_all = pyqtSignal()
    reset_ui = pyqtSignal()
    def __init__(self):
        super().__init__()
        self.initUI()
        self.close_event_handled = False



    def initUI(self):
        self.setWindowTitle("Progreso de Carga")
        self.setMinimumWidth(600)
        self.setMaximumWidth(600)

        barra_altura = 25
        etiqueta_altura = 20
        espacio_entre_barras = 15

        altura_total = (barra_altura + etiqueta_altura + espacio_entre_barras) * 4 * 2

        self.setMinimumHeight(altura_total)
        self.setMaximumHeight(altura_total)


        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(15)

        scroll_area = QtWidgets.QScrollArea(self)
        scroll_area.setWidgetResizable(True)
        scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOn)
        scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        scroll_content = QtWidgets.QWidget()
        self.progress_layout = QtWidgets.QVBoxLayout(scroll_content)
        self.progress_layout.setContentsMargins(5, 5, 5, 5)
        self.progress_layout.setSpacing(15)

        scroll_area.setWidget(scroll_content)
        layout.addWidget(scroll_area)

        self.setLayout(layout)
        self.show()



    def add_progress_ui(self, folder_name, initial_message="Cargando archivos..."):

        group_box = QtWidgets.QGroupBox()
        group_box_layout = QtWidgets.QVBoxLayout()
        group_box_layout.setContentsMargins(5, 5, 5, 5)
        group_box_layout.setSpacing(5)

        folder_label = QtWidgets.QLabel(f"Subiendo Carpeta: {folder_name}", self)
        group_box_layout.addWidget(folder_label)

        barra_layout = QtWidgets.QHBoxLayout()
        barra_layout.setContentsMargins(5, 5, 5, 5)
        barra_layout.setSpacing(5)

        progress_bar = QtWidgets.QProgressBar(self)
        progress_bar.setMaximum(100)
        progress_bar.setValue(100)

        palette = progress_bar.palette()
        palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor("yellow"))
        progress_bar.setPalette(palette)

        barra_layout.addWidget(progress_bar)

        group_box_layout.addLayout(barra_layout)

        progress_label = QtWidgets.QLabel(initial_message, self)
        group_box_layout.addWidget(progress_label)

        group_box.setLayout(group_box_layout)

        self.progress_layout.addWidget(group_box)

        progress_bars[folder_name] = progress_bar
        progress_labels[folder_name] = progress_label



    def update_progress(self, folder_name, value, message):

        if folder_name in progress_bars:
            progress_bars[folder_name].setValue(int(value))
            progress_labels[folder_name].setText(message)

            if value == 100:
                self.set_progress_color(folder_name, "green")

            elif value == 0:
                self.set_progress_color(folder_name, "default")



    def set_progress_color(self, folder_name, color):

        if folder_name in progress_bars:
            progress_bar = progress_bars[folder_name]
            palette = progress_bar.palette()

            if color == "green":
                palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor("green"))

            elif color == "red":
                palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor("red"))

            elif color == "yellow":
                palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor("yellow"))

            elif color == "orange":
                palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor("orange"))

            else:

                palette.setColor(
                    QtGui.QPalette.Highlight,
                    self.style().standardPalette().color(QtGui.QPalette.Highlight),
              )

            progress_bar.setPalette(palette)



    def closeEvent(self, event):

        if not self.close_event_handled:
            self.close_event_handled = True
            reply = QtWidgets.QMessageBox.question(

                self,
                "Confirmación de cierre",
                "Si cierras la ventana, todas las subidas pendientes se cancelarán. ¿Estás seguro de que deseas cerrar?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,

            )

            if reply == QtWidgets.QMessageBox.Yes:
                self.cancel_all.emit()
                self.reset_ui.emit()
                event.accept()

            else:
                self.close_event_handled = False
                event.ignore()

        else:
            event.ignore()

class ProgressFile(io.FileIO):
    def __init__(self, path, mode, callback):
        super().__init__(path, mode)
        self.callback = callback
        self.length = os.path.getsize(path)
        self.total_read = 0

    def read(self, size=-1):
        chunk = super().read(size)
        self.total_read += len(chunk)
        self.callback(self.total_read, self.length)
        return chunk

class UploadWorker(QObject):
    progress_updated = pyqtSignal(str, float, str)
    upload_complete = pyqtSignal(str, bool)
    cancel_signal = pyqtSignal()

    def __init__(self, folder, parent_folder_id, max_retries=3):
        super().__init__()
        self.folder = folder
        self.parent_folder_id = parent_folder_id
        self.is_canceled = False
        self.max_retries = max_retries
        self.cancel_signal.connect(self.cancel_upload)

    def run(self):
        retries = 0
        success = False
        print(f"Iniciando subida de la carpeta: {self.folder} con un máximo de {self.max_retries} reintentos")

        while retries < self.max_retries and not success and not self.is_canceled:
            if not check_internet_connection():
                print("No hay conexión. Esperando reconexión antes de iniciar...")
                self.handle_connection_loss()
                retries += 1
                QtCore.QThread.sleep(5)
                continue

            print(f"Intento {retries+1} de subir la carpeta: {self.folder}")
            success = self.upload_folder(self.folder, self.parent_folder_id)
            if not success:
                retries += 1
                if retries < self.max_retries:
                    print(f"Fallo en la subida. Reintento {retries} para {self.folder}")
                    self.progress_updated.emit(
                        self.folder, 0, "Error: Fallo en la subida. Reintentando..."
                    )
                    self.handle_connection_loss()
                    QtCore.QThread.sleep(5)
                else:
                    print(f"Máximo de reintentos alcanzado para {self.folder}")
                    self.progress_updated.emit(
                        self.folder,
                        0,
                        "Error: Fallo en la subida. Máximo número de reintentos alcanzado.",
                    )

        print(f"Subida completa para {self.folder}, éxito: {success}")
        self.upload_complete.emit(self.folder, success)

    def get_total_size(self, folder_path):
        total_size = 0
        for dirpath, dirnames, filenames in os.walk(folder_path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if os.path.isfile(fp):
                    total_size += os.path.getsize(fp)
        return total_size

    def upload_folder(self, local_folder_path, parent_id):
        if self.is_canceled:
            print("Subida de carpeta cancelada antes de iniciar:", local_folder_path)
            return False

        if not hasattr(self, 'total_size') or self.total_size == 0:
            self.total_size = self.get_total_size(local_folder_path)
            self.bytes_uploaded = 0
            self.start_time = time.time()
            print(f"Tamaño total de la carpeta {local_folder_path}: {self.total_size} bytes")

        folder_name = os.path.basename(local_folder_path)
        print(f"Creando carpeta remota: {folder_name}")
        folder_id = self.create_folder(folder_name, parent_id)
        items = os.listdir(local_folder_path)

        for item_name in items:
            if self.is_canceled:
                print("Subida de carpeta cancelada en medio de la operación:", local_folder_path)
                return False

            item_path = os.path.join(local_folder_path, item_name)
            if os.path.isdir(item_path):
                print(f"Entrando a subcarpeta: {item_path}")
                self.upload_folder(item_path, parent_id=folder_id)
            else:
                print(f"Iniciando subida de archivo en carpeta: {item_path}")
                self.upload_file(item_path, parent_id=folder_id)
                time.sleep(1)  # Retraso entre subidas de archivos

        print(f"Finalizada subida de carpeta: {local_folder_path}")
        return not self.is_canceled

    def upload_file(self, file_path, parent_id):
        if self.is_canceled:
            print("Subida cancelada antes de iniciar el archivo:", file_path)
            return False

        file_name = os.path.basename(file_path)
        base, ext = os.path.splitext(file_name)
        folder_name = os.path.basename(os.path.dirname(file_path))

        print(f"Iniciando subida de archivo: {file_path}")

        # Renombrar archivos si es necesario
        if ext.lower() in ['.mp4', '.srt']:
            if not base.endswith(f"_{folder_name}"):
                new_file_name = f"{base}_{folder_name}{ext}"
                new_file_path = os.path.join(os.path.dirname(file_path), new_file_name)
                try:
                    print(f"Renombrando {file_name} a {new_file_name}")
                    os.rename(file_path, new_file_path)
                    file_path = new_file_path  # Actualizar la ruta del archivo
                    file_name = new_file_name  # Actualizar el nombre del archivo
                except Exception as e:
                    print(f"Error al renombrar archivo {file_name}: {str(e)}")
                    self.progress_updated.emit(
                        os.path.basename(self.folder),
                        0,
                        f"Error al renombrar archivo: {str(e)}"
                    )
                    return False

        gfile = drive.CreateFile({'title': file_name, 'parents': [{'id': parent_id}]})

        def progress(current, total):
            if self.is_canceled:
                print("Subida cancelada en medio del progreso de:", file_path)
                raise Exception("Upload canceled")
            bytes_this_chunk = current - progress.last_current
            progress.last_current = current
            self.bytes_uploaded += bytes_this_chunk

            progress_percentage = (self.bytes_uploaded / self.total_size) * 100

            elapsed_time = time.time() - self.start_time
            speed = self.bytes_uploaded / elapsed_time if elapsed_time > 0 else 0
            remaining_bytes = self.total_size - self.bytes_uploaded
            time_remaining = remaining_bytes / speed if speed > 0 else float('inf')

            completed_data, completed_unit = self.format_size(self.bytes_uploaded)
            total_data, total_unit = self.format_size(self.total_size)
            time_remaining_str = self.format_time2finish(time_remaining)

            # Emitir señal de progreso
            self.progress_updated.emit(
                os.path.basename(self.folder),
                progress_percentage,
                f"{completed_data}{completed_unit} de {total_data}{total_unit} Subidos. "
                f"Tiempo restante: {time_remaining_str}.",
            )

        progress.last_current = 0

        attempts = 0
        max_attempts = 5

        while attempts < max_attempts and not self.is_canceled:
            try:
                print(f"Intento {attempts+1} de subida de {file_path}")
                with ProgressFile(file_path, 'rb', callback=progress) as f:
                    gfile.content = f
                    gfile.Upload()  # Intento de subida
                print(f"Archivo subido exitosamente: {file_path}")
                return not self.is_canceled
            except ConnectionResetError:
                attempts += 1
                print(f"ConnectionResetError al subir {file_path}, reintentando...")
                self.handle_connection_loss()
                while not check_internet_connection() and not self.is_canceled:
                    print("Esperando reconexión a Internet...")
                    time.sleep(5)
                if self.is_canceled:
                    print("Subida cancelada durante espera de reconexión:", file_path)
                    return False
                print("Conexión restaurada. Reintentando subida...")
            except pydrive2.files.ApiRequestError as e:
                if 'userRateLimitExceeded' in str(e):
                    attempts += 1
                    wait_time = 2 ** attempts  # Exponential backoff
                    print(f"Límite de tasa alcanzado. Reintentando en {wait_time} segundos...")
                    time.sleep(wait_time)
                else:
                    raise e
            except Exception as e:
                print(f"Error inesperado al subir {file_path}: {str(e)}")
                self.progress_updated.emit(
                    os.path.basename(self.folder),
                    0,
                    f"Error inesperado al subir el archivo: {str(e)}"
                )
                return False

        print(f"No se pudo reanudar la subida después de {max_attempts} intentos: {file_path}")
        self.progress_updated.emit(
            os.path.basename(self.folder),
            0,
            "Error: No se pudo reanudar la subida después de varios intentos."
        )
        return False

    def format_size(self, size_in_bytes):
        if size_in_bytes >= 1024**3:
            size = size_in_bytes / (1024**3)
            unit = 'GiB'
        elif size_in_bytes >= 1024**2:
            size = size_in_bytes / (1024**2)
            unit = 'MiB'
        elif size_in_bytes >= 1024:
            size = size_in_bytes / 1024
            unit = 'KiB'
        else:
            size = size_in_bytes
            unit = 'Bytes'
        return round(size, 2), unit

    def format_time2finish(self, seconds):
        if seconds == float('inf'):
            return 'infinito'
        else:
            h = int(seconds // 3600)
            m = int((seconds % 3600) // 60)
            s = int(seconds % 60)
            return f"{h}h {m}m {s}s"

    def handle_connection_loss(self):
        base_folder_name = os.path.basename(self.folder)
        message = "Se perdió conexión. Esperando a reconectarse para reintentar..."
        self.progress_updated.emit(base_folder_name, 0, message)

        if base_folder_name in progress_bars:
            if base_folder_name in progress_labels:
                progress_labels[base_folder_name].setText(message)
            palette = progress_bars[base_folder_name].palette()
            palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor("orange"))
            progress_bars[base_folder_name].setPalette(palette)

    def cancel_upload(self):
        self.is_canceled = True

    def create_folder(self, folder_name, parent_id=None):
        folder_metadata = {
            'title': folder_name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [{'id': parent_id}] if parent_id else []
        }
        folder = drive.CreateFile(folder_metadata)
        
        max_attempts = 5
        attempt = 0
        while attempt < max_attempts:
            try:
                folder.Upload()
                return folder['id']
            except pydrive2.files.ApiRequestError as e:
                if 'userRateLimitExceeded' in str(e):
                    attempt += 1
                    wait_time = 2 ** attempt  # Exponential backoff
                    print(f"Límite de tasa alcanzado. Reintentando en {wait_time} segundos...")
                    time.sleep(wait_time)
                else:
                    raise e
        raise Exception("No se pudo crear la carpeta después de varios intentos.")


class DriveFileExplorer(QtWidgets.QDialog):
    folder_selected = pyqtSignal(str, str)  # Signal para emitir el ID y nombre de la carpeta seleccionada

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Explorador de Google Drive")
        self.setGeometry(100, 100, 800, 600)
        self.current_folder_id = None
        self.is_shared_drive = False  # Para saber si estamos navegando en unidades compartidas
        self.history = []  # Lista para almacenar el historial de carpetas
        self.history_index = -1  # Índice para rastrear la posición en el historial
        self.selected_folder_name = ""  # Almacenar la carpeta seleccionada
        self.initUI()

    def initUI(self):
        main_layout = QtWidgets.QVBoxLayout(self)

        toolbar = QtWidgets.QHBoxLayout()

        # Botón "Home"
        self.home_button = QtWidgets.QPushButton("Home")
        self.home_button.clicked.connect(self.go_home)

        # Botón "Refrescar"
        self.refresh_button = QtWidgets.QPushButton("Refrescar")
        self.refresh_button.clicked.connect(self.refresh)

        toolbar.addWidget(self.home_button)
        toolbar.addWidget(self.refresh_button)

        self.path_edit = QtWidgets.QLineEdit(self)
        self.path_edit.setText("Mi unidad")
        self.path_edit.setReadOnly(True)
        toolbar.addWidget(self.path_edit)

        main_layout.addLayout(toolbar)

        # Etiqueta para mostrar la carpeta seleccionada
        self.selected_folder_label = QtWidgets.QLabel("Carpeta seleccionada: Ninguna", self)
        self.selected_folder_label.setAlignment(QtCore.Qt.AlignLeft)
        main_layout.addWidget(self.selected_folder_label)
        
        # TreeView para mostrar las carpetas de Google Drive
        self.tree_view = QtWidgets.QTreeWidget(self)
        self.tree_view.setHeaderLabel("Nombre")
        self.tree_view.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.tree_view.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)  # Permitir selección de un solo elemento
        self.tree_view.itemSelectionChanged.connect(self.update_selected_folder_label)  # Conectar para actualizar la carpeta seleccionada
        main_layout.addWidget(self.tree_view)

        # Layout para botones "Seleccionar carpeta" y "Cancelar"
        buttons_layout = QtWidgets.QHBoxLayout()

        # Botón "Seleccionar carpeta"
        self.select_button = QtWidgets.QPushButton("Seleccionar carpeta", self)
        self.select_button.clicked.connect(self.select_folder)
        buttons_layout.addWidget(self.select_button)

        # Botón "Cancelar"
        self.cancel_button = QtWidgets.QPushButton("Cancelar", self)
        self.cancel_button.clicked.connect(self.close)
        buttons_layout.addWidget(self.cancel_button)

        main_layout.addLayout(buttons_layout)

        self.setLayout(main_layout)
        self.load_initial_view()  # Cargar "Mi unidad" y "Unidades compartidas"

    def load_initial_view(self):
        """Cargar la vista inicial con 'Mi unidad' y 'Unidades compartidas'."""
        self.tree_view.clear()
        self.current_folder_id = None
        self.path_edit.setText("Inicio")

        # Agregar "Mi unidad"
        my_drive_item = QtWidgets.QTreeWidgetItem(self.tree_view, ["Mi unidad"])
        my_drive_item.setData(0, QtCore.Qt.UserRole, "root")  # El ID de la raíz de Google Drive
        my_drive_item.setData(0, QtCore.Qt.UserRole + 1, False)  # No es unidad compartida
        folder_icon = self.style().standardIcon(QtWidgets.QStyle.SP_DirIcon)
        my_drive_item.setIcon(0, folder_icon)

        # Agregar "Unidades compartidas"
        shared_drives_item = QtWidgets.QTreeWidgetItem(self.tree_view, ["Unidades compartidas"])
        shared_drives_item.setData(0, QtCore.Qt.UserRole, "shared")  # ID ficticio para manejar la lógica
        shared_drives_item.setData(0, QtCore.Qt.UserRole + 1, True)  # Es unidad compartida
        shared_drives_item.setIcon(0, folder_icon)

        # Reseteamos el historial cuando se carga la vista inicial
        self.history = [{"id": None, "name": "Inicio"}]
        self.history_index = 0

    def load_drive_folder(self, folder_id='root', is_shared_drive=False):
        """Carga las carpetas en la vista TreeWidget."""
        self.tree_view.clear()
        self.current_folder_id = folder_id
        self.is_shared_drive = is_shared_drive
        self.path_edit.setText(folder_id if folder_id != 'root' else 'Mi unidad')

        try:
            folder_icon = self.style().standardIcon(QtWidgets.QStyle.SP_DirIcon)
            if is_shared_drive:
                # Listar las carpetas en una unidad compartida
                file_list = drive.ListFile({'q': f"'{folder_id}' in parents and trashed=false"}).GetList()
         
            else:
                # Listar las carpetas en "Mi unidad"
                file_list = drive.ListFile({'q': f"'{folder_id}' in parents and trashed=false"}).GetList()

            # Ordenar las carpetas por nombre
            file_list.sort(key=lambda x: x['title'])
            
            for file in file_list:
                item = QtWidgets.QTreeWidgetItem(self.tree_view, [file['title']])
                item.setData(0, QtCore.Qt.UserRole, file['id'])
                if file['mimeType'] == 'application/vnd.google-apps.folder':
                    item.setIcon(0, folder_icon)

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", str(e))

    def load_shared_drives(self):
        """Cargar las unidades compartidas disponibles."""
        self.tree_view.clear()
        self.path_edit.setText("Unidades compartidas")
        try:
            folder_icon = self.style().standardIcon(QtWidgets.QStyle.SP_DirIcon)
            shared_drives = service.drives().list().execute().get('drives', [])
            # Ordenar las unidades compartidas por nombre
            shared_drives.sort(key=lambda x: x['name'])
            
            for drive in shared_drives:
                item = QtWidgets.QTreeWidgetItem(self.tree_view, [drive['name']])
                item.setData(0, QtCore.Qt.UserRole, drive['id'])
                item.setData(0, QtCore.Qt.UserRole + 1, True)  # Es unidad compartida
                item.setIcon(0, folder_icon)

        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Error", str(e))

    def on_item_double_clicked(self, item, column):
        """Cuando se hace doble clic en una carpeta o en la unidad inicial."""
        folder_id = item.data(0, QtCore.Qt.UserRole)
        is_shared_drive = item.data(0, QtCore.Qt.UserRole + 1)

        if folder_id == "shared":  # Cuando se selecciona "Unidades compartidas"
            self.load_shared_drives()
        else:
            self.load_drive_folder(folder_id, is_shared_drive)

    def go_home(self):
        """Vuelve a la carpeta raíz (vista inicial con 'Mi unidad' y 'Unidades compartidas')."""
        self.load_initial_view()

    def refresh(self):
        """Refresca el contenido de la carpeta actual."""
        if self.current_folder_id:
            self.load_drive_folder(self.current_folder_id, self.is_shared_drive)
        else:
            self.load_initial_view()

    def select_folder(self):
        """Selecciona la carpeta seleccionada y emite la señal."""
        selected_items = self.tree_view.selectedItems()
        if selected_items:
            selected_item = selected_items[0]
            folder_id = selected_item.data(0, QtCore.Qt.UserRole)
            folder_name = selected_item.text(0)
            self.folder_selected.emit(folder_id, folder_name)
            self.accept()  # Cierra el diálogo al seleccionar la carpeta
        else:
            QtWidgets.QMessageBox.warning(self, "No selección", "Por favor, selecciona una carpeta.")

    def update_selected_folder_label(self):
        """Actualiza la etiqueta con el nombre de la carpeta seleccionada."""
        selected_items = self.tree_view.selectedItems()
        if selected_items:
            selected_item = selected_items[0]
            folder_name = selected_item.text(0)
            self.selected_folder_label.setText(f"Carpeta seleccionada: {folder_name}")
        else:
            self.selected_folder_label.setText("Carpeta seleccionada: Ninguna")

            
class DriveUploaderApp(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.upload_queue = Queue()
        self.active_uploads = 0
        self.progress_window = None
        self.close_event_handled = False
        self.last_selected_folder = os.path.expanduser("~")
        self.selected_drive_folder_id = 'root'  # Default to root
        self.unit_selected = 'root'

    def initUI(self):
        self.setWindowTitle("Subir Carpetas a Google Drive")
        self.setMinimumWidth(700)
        main_layout = QtWidgets.QVBoxLayout()

        self.selected_folder_label = QtWidgets.QLabel("Carpeta seleccionada: Ninguna", self)
        self.selected_folder_label.setFont(QtGui.QFont("Arial", 13))
        main_layout.addWidget(self.selected_folder_label)

        # Botón para abrir el DriveFileExplorer
        self.drive_unit_button = QtWidgets.QPushButton("Seleccionar Unidad de Drive", self)
        self.drive_unit_button.clicked.connect(self.show_drive_file_explorer)  # Conectar con la función que abre el explorador
        main_layout.addWidget(self.drive_unit_button)

            
        folder_layout = QtWidgets.QHBoxLayout()

        self.file_list = QtWidgets.QListWidget(self)
        folder_layout.addWidget(self.file_list)

        btn_fldr_layout = QtWidgets.QVBoxLayout()
        self.select_folder_button = QtWidgets.QPushButton("Seleccionar", self)
        self.select_folder_button.clicked.connect(self.select_folder)
        btn_fldr_layout.addWidget(self.select_folder_button)

        self.delete_folder_button = QtWidgets.QPushButton("Eliminar", self)
        self.delete_folder_button.clicked.connect(self.delete_selected_folders)
        btn_fldr_layout.addWidget(self.delete_folder_button)

        folder_layout.addLayout(btn_fldr_layout)

        main_layout.addLayout(folder_layout)

        
        # Sección de Selección de Carpeta de Destino en Google Drive
        self.drive_folder_info_label = QtWidgets.QLabel("Selecciona Carpeta de Destino:", self)
        self.drive_folder_info_label.setFont(QtGui.QFont("Arial", 13))
        
        main_layout.addWidget(self.drive_folder_info_label)

        drive_folder_layout = QtWidgets.QHBoxLayout()

        self.drive_folder_combobox = QtWidgets.QComboBox(self)
        self.drive_folder_combobox.currentIndexChanged.connect(self.on_drive_folder_selected)
        drive_folder_layout.addWidget(self.drive_folder_combobox)

        self.create_folder_button = QtWidgets.QPushButton("Crear carpeta", self)
        self.create_folder_button.clicked.connect(self.create_new_drive_folder)
        drive_folder_layout.addWidget(self.create_folder_button)

        main_layout.addLayout(drive_folder_layout)

        btn_layout = QtWidgets.QHBoxLayout()

        self.upload_button = QtWidgets.QPushButton("Subir Carpetas", self)
        self.upload_button.setEnabled(False)
        self.upload_button.clicked.connect(self.upload_folder)
        btn_layout.addWidget(self.upload_button)

        main_layout.addLayout(btn_layout)

        self.result_list = QtWidgets.QListWidget(self)
        main_layout.addWidget(self.result_list)

        self.setLayout(main_layout)
        self.show()

    def show_drive_file_explorer(self):
        """Abrir el DriveFileExplorer para seleccionar la unidad de Google Drive."""
        self.drive_file_explorer = DriveFileExplorer()
        self.drive_file_explorer.folder_selected.connect(self.on_folder_selected)
        self.drive_file_explorer.exec_()  # Mostrar el explorador como una ventana modal

    def on_folder_selected(self, folder_id, folder_name):
        """Manejar la selección de carpeta desde el DriveFileExplorer."""
        self.selected_folder_label.setText(f"Carpeta seleccionada: {folder_name}")  # Mostrar el nombre de la carpeta seleccionada
        self.result_list.addItem(f"Unidad seleccionada: {folder_name} (ID: {folder_id})")
        self.unit_selected = folder_id
        self.update_drive_folder_combobox(folder_id)  # Rellenar el ComboBox con las subcarpetas
        
    def update_drive_folder_combobox(self, parent_id='root'):
        """Actualizar el ComboBox con las subcarpetas de la carpeta seleccionada."""
        folders = self.list_drive_folders(parent_id)
        self.drive_folder_combobox.clear()

        # Argegar root como primero
        self.drive_folder_combobox.addItem("Raíz Drive", 'root')
        
        for folder in folders:
            self.drive_folder_combobox.addItem(folder['title'], folder['id'])

        if folders:
            # Seleccionar la primera carpeta si hay resultados
            self.drive_folder_combobox.setCurrentIndex(0)
            self.selected_drive_folder_id = folders[0]['id']
        else:
            self.selected_drive_folder_id = None  # No hay carpetas disponibles

    def list_drive_folders(self, parent_id='root'):
        """Obtener las subcarpetas dentro de una carpeta de Google Drive."""
        folder_list = []
        try:
            file_list = drive.ListFile({'q': f"'{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed=false"}).GetList()
            for file in file_list:
                folder_list.append({'title': file['title'], 'id': file['id']})
        except Exception as e:
            self.result_list.addItem(f"Error al listar carpetas: {str(e)}")
        return folder_list

    def create_new_drive_folder(self):
        """Crear una nueva carpeta en la unidad seleccionada."""
        unit_id = self.unit_selected

        new_folder_name, ok = QtWidgets.QInputDialog.getText(
            self, "Nueva carpeta", "Ingrese el nombre de la nueva carpeta:"
        )
        if ok and new_folder_name:
            try:
                folder_metadata = {
                    'title': new_folder_name,
                    'mimeType': 'application/vnd.google-apps.folder',
                    'parents': [{'id': unit_id}]
                }
                new_folder = drive.CreateFile(folder_metadata)
                new_folder.Upload()
                self.result_list.addItem(f"Carpeta creada: {new_folder_name} (ID: {new_folder['id']})")
                self.update_drive_folder_combobox(unit_id)
            except Exception as e:
                self.result_list.addItem(f"Error al crear carpeta: {str(e)}")
            self.result_list.scrollToBottom()
            
            self.update_drive_folder_combobox(unit_id) 
    def update_unit(self):
        
        # Listar las unidades compartidas
        shared_drives = self.list_shared_drives()
        for drive in shared_drives:
            self.drive_unit_combobox.addItem(drive['name'], drive['id'])
            
    def on_drive_unit_selected(self):
        # Obtener la unidad seleccionada (ID de la unidad)
        unit_id = self.unit_selected
        
        # Actualizar la lista de carpetas basándonos en la unidad seleccionada
        self.update_drive_folder_combobox(unit_id)

    def list_shared_drives(self):
        """
        Lista las unidades compartidas (Shared Drives).
        """
        try:
            shared_drives = service.drives().list().execute().get('drives', [])
            return shared_drives
        except Exception as e:
            self.result_list.addItem(f"Error al listar unidades compartidas: {str(e)}")
            return []
        
        
    def show_drive_directory(self):
        self.drive_dir_view_window = DriveFileExplorer()
        self.drive_dir_view_window.show()

    def closeEvent(self, event):
        if not self.close_event_handled:
            self.close_event_handled = True
            reply = QtWidgets.QMessageBox.question(
                self,
                "Confirmación de cierre",
                "Si cierras la ventana, todas las subidas pendientes se cancelarán. ¿Estás seguro de que deseas cerrar?",
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No,
                QtWidgets.QMessageBox.No,
            )
            if reply == QtWidgets.QMessageBox.Yes:
                self.cancel_all_uploads()
                if self.progress_window:
                    self.progress_window.close_event_handled = True
                    self.progress_window.close()
                event.accept()
            else:
                self.close_event_handled = False
                event.ignore()
        else:
            event.ignore()

    def select_folder(self):
        global selected_folders, total_files

        file_dialog = QtWidgets.QFileDialog(self)
        file_dialog.setFileMode(QtWidgets.QFileDialog.DirectoryOnly)
        file_dialog.setOption(QtWidgets.QFileDialog.DontUseNativeDialog, True)

        # Permitir la selección de múltiples directorios
        file_view = file_dialog.findChild(QtWidgets.QListView, 'listView')
        if file_view:
            file_view.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
        f_tree_view = file_dialog.findChild(QtWidgets.QTreeView)
        if f_tree_view:
            f_tree_view.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)

        if file_dialog.exec():
            paths = file_dialog.selectedFiles()
            for selected_folder in paths:
                self.last_selected_folder = selected_folder
                selected_folders.append(selected_folder)
                self.file_list.addItem(selected_folder)
                self.result_list.addItem(f"Seleccionada la carpeta: {selected_folder}")
                self.result_list.addItem("Contando archivos...")
                self.result_list.scrollToBottom()
                total_files += sum(len(files) for _, _, files in os.walk(selected_folder))
                self.result_list.addItem(
                    f"Se han detectado {total_files} archivos en total por subir de la carpeta {os.path.basename(selected_folder)}."
                )
                self.result_list.scrollToBottom()
        self.update_upload_button_state()

    def delete_selected_folders(self):
        selected_items = self.file_list.selectedItems()
        if not selected_items:
            return

        for item in selected_items:
            folder_path = item.text()
            selected_folders.remove(folder_path)
            self.file_list.takeItem(self.file_list.row(item))

        self.update_upload_button_state()

    def list_drive_folders(self, parent_id='root'):
        folder_list = []
        try:
            file_list = drive.ListFile({'q': f"'{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed=false"}).GetList()
            for file in file_list:
                folder_list.append({'title': file['title'], 'id': file['id']})
            
        except Exception as e:
            self.result_list.addItem(f"Error al listar carpetas: {str(e)}")
        return folder_list

    def update_drive_folder_combobox(self, parent_id='root'):
        folders = self.list_drive_folders(parent_id)
        self.drive_folder_combobox.clear()
        
        
        for folder in folders:
            self.drive_folder_combobox.addItem(folder['title'], folder['id'])
        
        # Establece la primera carpeta (root) como seleccionada por defecto
        self.drive_folder_combobox.setCurrentIndex(0)
        self.selected_drive_folder_id = 'root'



    def on_drive_folder_selected(self):
        """Actualizar el ID de la carpeta seleccionada desde el ComboBox."""
        index = self.drive_folder_combobox.currentIndex()
        folder_id = self.drive_folder_combobox.itemData(index)
        folder_name = self.drive_folder_combobox.currentText()
        if folder_id:
            self.selected_drive_folder_id = folder_id
            self.result_list.addItem(f"Carpeta de destino seleccionada: {folder_name} (ID: {folder_id})")
        else:
            self.selected_drive_folder_id = 'root'  # Si no hay carpeta seleccionada, usar la raíz
            self.result_list.addItem("No se seleccionó ninguna carpeta de Google Drive.")
        self.result_list.scrollToBottom()
        self.update_upload_button_state()

    def create_new_drive_folder(self):
        unit_id = self.unit_selected
        new_folder_name, ok = QtWidgets.QInputDialog.getText(
            self, "Nueva carpeta", "Ingrese el nombre de la nueva carpeta:"
        )
        if ok and new_folder_name:
            try:
                folder_metadata = {
                    'title': new_folder_name,
                    'mimeType': 'application/vnd.google-apps.folder',
                    'parents': [{'id': unit_id}]
                }
                new_folder = drive.CreateFile(folder_metadata)
                new_folder.Upload()
                self.result_list.addItem(f"Carpeta creada: {new_folder_name} (ID: {new_folder['id']})")
                self.update_drive_folder_combobox(unit_id)
            except Exception as e:
                self.result_list.addItem(f"Error al crear carpeta: {str(e)}")
            self.result_list.scrollToBottom()

    def upload_folder(self):
        global progress_bars, progress_labels, upload_threads

        folder_name = self.drive_folder_combobox.currentText()
        folder_id = self.selected_drive_folder_id  # Usar la carpeta seleccionada
        self.result_list.addItem(f"Directorio de destino: {folder_name} (ID: {folder_id})")

        if not self.progress_window or not self.progress_window.isVisible():
            self.progress_window = ProgressWindow()
            self.progress_window.cancel_all.connect(self.cancel_all_uploads)
            self.progress_window.reset_ui.connect(self.reset_ui_state)
            self.progress_window.show()

            progress_bars.clear()
            progress_labels.clear()

        for folder in selected_folders:
            base_folder_name = os.path.basename(folder)
            if base_folder_name not in progress_bars:
                self.progress_window.add_progress_ui(
                    base_folder_name, "Carpeta en cola"
                )
                # Asegúrate de que el folder_id sea el correcto (no root)
                self.upload_queue.put((folder, folder_id))  # Usar la carpeta seleccionada como destino

        self.start_next_uploads()


    def start_next_uploads(self):
        while (
            self.active_uploads < MAX_CONCURRENT_UPLOADS
            and not self.upload_queue.empty()
        ):
            folder, parent_folder_id = self.upload_queue.get()  # Asegúrate de que parent_folder_id es correcto
            base_folder_name = os.path.basename(folder)

            self.progress_window.update_progress(base_folder_name, 0, "Iniciando...")
            self.progress_window.set_progress_color(base_folder_name, "default")

            worker = UploadWorker(folder, parent_folder_id)  # Pasar el ID de la carpeta seleccionada
            worker_thread = QThread()
            worker.moveToThread(worker_thread)

            worker.progress_updated.connect(self.progress_window.update_progress)
            worker.upload_complete.connect(self.on_upload_complete)

            worker_thread.started.connect(worker.run)
            worker_thread.start()
            upload_threads[folder] = (worker, worker_thread)

            self.active_uploads += 1


    def on_upload_complete(self, folder, success):
        base_folder_name = os.path.basename(folder)
        if success:
            self.result_list.addItem(f"La carpeta {folder} se ha subido exitosamente.")
            if base_folder_name in progress_bars:
                self.progress_window.update_progress(
                    base_folder_name, 100, "Carpeta subida con éxito."
                )
                self.progress_window.set_progress_color(base_folder_name, "green")
        else:
            self.result_list.addItem(f"Error al subir la carpeta {folder}.")
            if base_folder_name in progress_bars:
                self.progress_window.set_progress_color(base_folder_name, "red")
            if base_folder_name in progress_labels:
                progress_labels[base_folder_name].setText(
                    "Error al subir la carpeta o problema de conexión."
                )

        self.result_list.scrollToBottom()

        self.active_uploads -= 1
        self.start_next_uploads()

    def cancel_all_uploads(self):
        global upload_threads

        for folder, (worker, worker_thread) in upload_threads.items():
            worker.cancel_signal.emit()
            worker_thread.quit()
            worker_thread.wait()

        upload_threads.clear()
        self.result_list.addItem("Todas las cargas pendientes han sido canceladas.")
        self.upload_queue.queue.clear()

        if self.progress_window:
            self.progress_window.close()
            self.progress_window = None

    def update_upload_button_state(self):
        if selected_folders and self.drive_folder_combobox.currentIndex() != -1:
            self.upload_button.setEnabled(True)
        else:
            self.upload_button.setEnabled(False)

    def reset_ui_state(self):
        global selected_folders, total_files, progress_bars, progress_labels, upload_threads

        selected_folders = []
        total_files = 0
        progress_bars = {}
        progress_labels = {}
        upload_threads = {}

        self.file_list.clear()
        self.select_folder_button.setEnabled(True)
        self.create_folder_button.setEnabled(True)
        self.upload_button.setEnabled(False)



if __name__ == "__main__":

    app = QtWidgets.QApplication([])
    uploader = DriveUploaderApp()
    app.exec_()