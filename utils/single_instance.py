import sys
from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

_SERVER_NAME = "infinisper_app_single_instance_lock"


class SingleInstance(QObject):
    """Ensures only one instance of Infinisper runs at a time.
    If another instance is launched, it notifies the existing one to show itself
    and gracefully exits."""
    show_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._server = None

    def is_already_running(self) -> bool:
        socket = QLocalSocket()
        socket.connectToServer(_SERVER_NAME)
        if socket.waitForConnected(500):
            # Send wake-up signal to existing instance
            socket.write(b"SHOW\n")
            socket.waitForBytesWritten(500)
            socket.disconnectFromServer()
            return True

        # Stale socket cleanup
        QLocalServer.removeServer(_SERVER_NAME)

        self._server = QLocalServer(self)
        self._server.newConnection.connect(self._on_new_connection)
        self._server.listen(_SERVER_NAME)
        return False

    def _on_new_connection(self):
        while self._server and self._server.hasPendingConnections():
            client = self._server.nextPendingConnection()
            client.readyRead.connect(lambda: self._handle_client(client))

    def _handle_client(self, client: QLocalSocket):
        data = client.readAll().data().decode("utf-8", errors="ignore").strip()
        if "SHOW" in data:
            self.show_requested.emit()
        client.disconnectFromServer()
