import os
import sys
import textwrap
from pathlib import Path
from typing import Optional

from PyQt5 import QtCore, QtGui, QtWidgets

try:
    from PyQt5 import QtWebEngineWidgets
except ImportError as exc:
    raise SystemExit(
        "PyQt5.QtWebEngineWidgets is required. Install PyQt5 with web engine "
        "support (e.g. `pip install PyQt5 PyQtWebEngine`)."
    ) from exc

try:
    import google.generativeai as genai
except ImportError as exc:
    raise SystemExit(
        "The google-generativeai package is required. "
        "Install it with `pip install google-generativeai`."
    ) from exc


MAX_HTML_CHARS = 12000
CONFIG_DIR = Path.home() / ".novabrowse"
API_KEY_FILE = CONFIG_DIR / "gemini_api_key"


def _load_api_key() -> Optional[str]:
    env_key = os.getenv("GEMINI_API_KEY")
    if env_key:
        env_key = env_key.strip()
        if env_key:
            return env_key

    try:
        file_key = API_KEY_FILE.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    except OSError:
        return None
    return file_key or None


def _save_api_key(api_key: str) -> bool:
    sanitized = api_key.strip()
    if not sanitized:
        return False
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        API_KEY_FILE.write_text(f"{sanitized}\n", encoding="utf-8")
        if os.name == "posix":
            os.chmod(API_KEY_FILE, 0o600)
    except OSError:
        return False
    return True


class ApiKeyDialog(QtWidgets.QDialog):
    """Dialog that allows pasting or revealing the Gemini API key."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Gemini API Key Required")
        self.setModal(True)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(QtWidgets.QLabel("Enter your Gemini API key:"))

        self._line_edit = QtWidgets.QLineEdit()
        self._line_edit.setEchoMode(QtWidgets.QLineEdit.Password)
        self._line_edit.setPlaceholderText("Paste your API key here…")
        self._line_edit.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)
        self._line_edit.setClearButtonEnabled(True)
        layout.addWidget(self._line_edit)

        paste_action = QtWidgets.QAction("Paste", self._line_edit)
        paste_action.setShortcut(QtGui.QKeySequence.Paste)
        paste_action.triggered.connect(self._line_edit.paste)
        self._line_edit.addAction(paste_action)

        paste_button = QtWidgets.QPushButton("Paste from clipboard")
        paste_button.clicked.connect(self._paste_from_clipboard)
        layout.addWidget(paste_button)

        toggle_checkbox = QtWidgets.QCheckBox("Show API key")
        toggle_checkbox.toggled.connect(self._toggle_echo_mode)
        layout.addWidget(toggle_checkbox)

        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self._line_edit.setFocus()

    def api_key(self) -> str:
        return self._line_edit.text().strip()

    def _toggle_echo_mode(self, checked: bool) -> None:
        self._line_edit.setEchoMode(
            QtWidgets.QLineEdit.Normal if checked else QtWidgets.QLineEdit.Password
        )

    def _paste_from_clipboard(self) -> None:
        clipboard = QtWidgets.QApplication.clipboard()
        if clipboard is None:
            return
        text = clipboard.text(QtGui.QClipboard.Clipboard)
        if not text and clipboard.supportsSelection():
            text = clipboard.text(QtGui.QClipboard.Selection)
        if text:
            self._line_edit.setText(text.strip())


class GeminiWorker(QtCore.QObject):
    finished = QtCore.pyqtSignal(str)
    failed = QtCore.pyqtSignal(str)

    def __init__(self, api_key: str, instruction: str, page_html: str) -> None:
        super().__init__()
        self._api_key = api_key
        self._instruction = instruction
        self._page_html = page_html

    @QtCore.pyqtSlot()
    def run(self) -> None:
        try:
            genai.configure(api_key=self._api_key)
            model = genai.GenerativeModel("gemini-pro")
            html_excerpt = self._page_html[:MAX_HTML_CHARS]
            system_prompt = textwrap.dedent(
                """\
                You are an assistant embedded inside a lightweight desktop web browser.
                Use the provided HTML snapshot of the current tab to complete the user's
                instruction. If information is missing in the markup, say so and suggest
                what the user could try next. Keep responses concise and actionable.
                """
            ).strip()
            user_message = textwrap.dedent(
                f"""\
                Instruction:
                {self._instruction.strip()}

                HTML snapshot (truncated to {MAX_HTML_CHARS} characters):
                {html_excerpt}
                """
            )
            response = model.generate_content(
                [
                    {"role": "system", "parts": [{"text": system_prompt}]},
                    {"role": "user", "parts": [{"text": user_message}]},
                ]
            )
            text = response.text or "[No text returned from Gemini]"
            self.finished.emit(text.strip())
        except Exception as error:  # pylint: disable=broad-except
            self.failed.emit(str(error))


class BrowserWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("NovaBrowse")
        self.resize(1200, 800)

        self._api_key = _load_api_key()

        self.web_view = QtWebEngineWidgets.QWebEngineView()
        self.web_view.setUrl(QtCore.QUrl("https://example.com"))

        self.url_bar = QtWidgets.QLineEdit()
        self.url_bar.setPlaceholderText("Enter URL and press Enter…")
        self.url_bar.returnPressed.connect(self.load_url)

        go_button = QtWidgets.QPushButton("Go")
        go_button.clicked.connect(self.load_url)

        back_button = QtWidgets.QPushButton("Back")
        back_button.clicked.connect(self.web_view.back)

        forward_button = QtWidgets.QPushButton("Forward")
        forward_button.clicked.connect(self.web_view.forward)

        reload_button = QtWidgets.QPushButton("Reload")
        reload_button.clicked.connect(self.web_view.reload)

        nav_layout = QtWidgets.QHBoxLayout()
        nav_layout.addWidget(back_button)
        nav_layout.addWidget(forward_button)
        nav_layout.addWidget(reload_button)
        nav_layout.addWidget(self.url_bar)
        nav_layout.addWidget(go_button)

        self.task_input = QtWidgets.QPlainTextEdit()
        self.task_input.setPlaceholderText("Describe what you need Gemini to do with the current page…")
        self.task_input.setFixedHeight(100)

        self.run_task_button = QtWidgets.QPushButton("Run Task with Gemini")
        self.run_task_button.clicked.connect(self.handle_run_task)

        self.assistant_output = QtWidgets.QPlainTextEdit()
        self.assistant_output.setReadOnly(True)

        agent_layout = QtWidgets.QVBoxLayout()
        agent_layout.addWidget(QtWidgets.QLabel("Gemini Assistant"))
        agent_layout.addWidget(self.task_input)
        agent_layout.addWidget(self.run_task_button)
        agent_layout.addWidget(QtWidgets.QLabel("Response"))
        agent_layout.addWidget(self.assistant_output)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
        splitter.addWidget(self.web_view)

        agent_widget = QtWidgets.QWidget()
        agent_widget.setLayout(agent_layout)
        splitter.addWidget(agent_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        central_widget = QtWidgets.QWidget()
        central_layout = QtWidgets.QVBoxLayout(central_widget)
        central_layout.addLayout(nav_layout)
        central_layout.addWidget(splitter)
        self.setCentralWidget(central_widget)

        if not self._api_key:
            self.run_task_button.setEnabled(False)
            QtCore.QTimer.singleShot(0, self._prompt_for_api_key)
        else:
            self.statusBar().showMessage("Gemini assistant ready.", 5000)

        self.web_view.urlChanged.connect(self._sync_url_bar)

    def load_url(self) -> None:
        raw_input = self.url_bar.text().strip()
        if not raw_input:
            return
        if "://" not in raw_input:
            raw_input = f"https://{raw_input}"

        url = QtCore.QUrl.fromUserInput(raw_input)
        if not url.isValid():
            self.statusBar().showMessage("Invalid URL. Please try again.", 5000)
            return

        self._set_url_bar_text(url.toString())
        self.web_view.setUrl(url)

    def _sync_url_bar(self, url: QtCore.QUrl) -> None:
        if self.url_bar.hasFocus() and self.url_bar.isModified():
            return
        self._set_url_bar_text(url.toString())

    def _set_url_bar_text(self, text: str) -> None:
        if self.url_bar.text() == text:
            self.url_bar.setModified(False)
            return

        was_blocked = self.url_bar.blockSignals(True)
        try:
            self.url_bar.setText(text)
        finally:
            self.url_bar.blockSignals(was_blocked)
        self.url_bar.setModified(False)

    def handle_run_task(self) -> None:
        if not self._api_key:
            self.assistant_output.setPlainText("Gemini API key missing. Set GEMINI_API_KEY and restart NovaBrowse.")
            return
        instruction = self.task_input.toPlainText().strip()
        if not instruction:
            self.assistant_output.setPlainText("Enter a task description for Gemini.")
            return

        self.run_task_button.setEnabled(False)
        self.assistant_output.setPlainText("Gathering page data…")

        def on_html_ready(html: str) -> None:
            self._start_gemini_worker(instruction, html)

        self.web_view.page().toHtml(on_html_ready)

    def _start_gemini_worker(self, instruction: str, html: str) -> None:
        self.assistant_output.appendPlainText("Contacting Gemini…")
        worker = GeminiWorker(self._api_key, instruction, html)
        thread = QtCore.QThread(self)
        worker.moveToThread(thread)

        thread.started.connect(worker.run)
        worker.finished.connect(self._on_gemini_result)
        worker.failed.connect(self._on_gemini_error)
        worker.finished.connect(thread.quit)
        worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)

        thread.start()

    @QtCore.pyqtSlot(str)
    def _on_gemini_result(self, text: str) -> None:
        self.assistant_output.setPlainText(text)
        self.run_task_button.setEnabled(True)

    @QtCore.pyqtSlot(str)
    def _on_gemini_error(self, message: str) -> None:
        self.assistant_output.setPlainText(f"Gemini request failed: {message}")
        self.run_task_button.setEnabled(True)

    def _prompt_for_api_key(self) -> None:
        while True:
            dialog = ApiKeyDialog(self)
            if dialog.exec_() != QtWidgets.QDialog.Accepted:
                if not self._api_key:
                    self.statusBar().showMessage(
                        "Gemini assistant disabled until an API key is provided.", 10000
                    )
                return

            sanitized = dialog.api_key()
            if not sanitized:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Invalid API Key",
                    "Please enter a non-empty Gemini API key.",
                )
                continue

            self._api_key = sanitized
            if not _save_api_key(sanitized):
                QtWidgets.QMessageBox.warning(
                    self,
                    "Could Not Save Key",
                    (
                        "The Gemini API key could not be saved to "
                        f"{API_KEY_FILE}. It will be used for this session only."
                    ),
                )
            else:
                self.statusBar().showMessage("Gemini API key saved. Assistant enabled.", 7000)

            self.run_task_button.setEnabled(True)
            return


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    window = BrowserWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
