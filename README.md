# NovaBrowse

NovaBrowse is a lightweight, PyQt-based desktop browser with a built-in Gemini assistant for simple agentic tasks. Load any webpage, describe what you want to do, and Gemini will work from the current HTML snapshot to help.

## Getting Started

1. Create and activate a virtual environment (recommended):
   ```bash
   python -m venv .venv
   source .venv/bin/activate        # On Windows use: .venv\Scripts\activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Launch NovaBrowse:
   ```bash
   python main.py
   ```
4. On first launch you will be prompted for your Gemini API key. The key is stored in `~/.novabrowse/gemini_api_key` so you do not have to re-enter it next time. You can still set the `GEMINI_API_KEY` environment variable if you prefer to manage it yourself.

## Using the Assistant



- Navigate as usual with the URL bar and Back/Forward/Reload controls.
- Enter a short instruction in the Gemini Assistant panel (for example, “Summarize this article” or “List the main steps mentioned on the page”).
- Click “Run Task with Gemini” to send the task along with the current page snapshot to Gemini. The response appears in the panel.

If the assistant button is disabled, provide a Gemini API key when prompted or set `GEMINI_API_KEY` before starting the application.

## Notes

- Gemini sees a truncated version of the page HTML (first 12k characters) to stay within model limits.
- Responses depend on the visible HTML; if critical information is missing, Gemini will let you know.
