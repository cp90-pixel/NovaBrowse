import os
import sys
import textwrap

from PyQt5 import QtCore, QtWidgets

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

        self._api_key = os.getenv("GEMINI_API_KEY")

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
            self.statusBar().showMessage("Set GEMINI_API_KEY to enable the Gemini assistant.", 15000)

        self.web_view.urlChanged.connect(self._sync_url_bar)

    def load_url(self) -> None:
        raw_url = self.url_bar.text().strip()
        if not raw_url:
            return
        if "://" not in raw_url:
            raw_url = f"https://{raw_url}"
        self.web_view.setUrl(QtCore.QUrl(raw_url))

    def _sync_url_bar(self, url: QtCore.QUrl) -> None:
        self.url_bar.setText(url.toString())

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


def main() -> None:
    app = QtWidgets.QApplication(sys.argv)
    window = BrowserWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
