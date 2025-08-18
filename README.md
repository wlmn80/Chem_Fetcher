# Student Results Fetcher

A Tkinter GUI tool for automatically retrieving student result data from a Firebase Realtime Database and exporting it to CSV.

## Features

* Batch fetch: select Year, Paper, index range and export to CSV
* Single-index fetch: enter a full index and get marks across all papers
* Missing-index retry and CSV export
* Animated status feedback and progress bar
* Configurable save folder remembered between sessions
* Results and configuration stored locally ‑ no credentials required

## Running from source

```bash
# create (optional) virtual environment
python -m venv env
source env/bin/activate  # Windows: env\Scripts\activate

pip install -r requirements.txt
python results_gui_dynamic.py
```

## Building a standalone Windows EXE

```bash
pip install pyinstaller
pyinstaller -F -n StudentResultsFetcher results_gui_dynamic.py
```

## License

Distributed under the MIT License. See `LICENSE` for details.
