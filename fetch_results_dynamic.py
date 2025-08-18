import os
import sys
import json
import csv
import re
from typing import List, Dict
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError
from urllib.parse import quote

BASE_URL = "https://results-app-5e81d-default-rtdb.asia-southeast1.firebasedatabase.app"
TIMEOUT = 10  # seconds
USER_AGENT = {"User-Agent": "Mozilla/5.0"}

# Globals that get set after the user makes selections
YEAR: int | None = None
PAPER_NAME: str = ""
START_INDEX: int = 0
END_INDEX: int = 0

############################ REST HELPERS ################################

def _get_json(url: str) -> dict | list | None:
    try:
        req = Request(url, headers=USER_AGENT)
        with urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
        return json.loads(raw.decode())
    except (HTTPError, URLError, json.JSONDecodeError):
        return None


def fetch_all_result_keys() -> List[str]:
    """Return all keys present under Results using the shallow query."""
    url = f"{BASE_URL}/Results.json?shallow=true"
    data = _get_json(url)
    if not isinstance(data, dict):
        raise RuntimeError("Unable to read Results keys from Firebase")
    return list(data.keys())

############################ BUSINESS LOGIC ##############################

def get_grade(mark: int) -> str:
    if mark >= 75:
        return "A"
    if mark >= 65:
        return "B"
    if mark >= 55:
        return "C"
    if mark >= 35:
        return "S"
    return "F"


def build_key(index_number: int) -> str:
    return f"{YEAR}_{PAPER_NAME}_{index_number}"


def fetch_result_record(index_number: int) -> Dict:
    key = build_key(index_number)
    encoded = quote(key, safe="")
    url = f"{BASE_URL}/Results/{encoded}.json"
    return _get_json(url) or {}


def fetch_student_record(index_number: int) -> Dict:
    url = f"{BASE_URL}/Students/{index_number}.json"
    return _get_json(url) or {}


def gather_records(start_idx: int, end_idx: int, show_progress: bool = True) -> List[Dict]:
    total = end_idx - start_idx + 1
    combined: List[Dict] = []
    for count, idx in enumerate(range(start_idx, end_idx + 1), 1):
        res = fetch_result_record(idx)
        if res:
            stu = fetch_student_record(idx)
            record = {
                "Rank": res.get("rank"),
                "Index Number": idx,
                "Name": stu.get("name"),
                "School": stu.get("school"),
                "Mark": res.get("mark"),
                "Grade": get_grade(res.get("mark", 0)),
            }
            combined.append(record)
        if show_progress:
            progress = (count / total) * 100
            print(f"\rProgress: {progress:.2f}%", end="", flush=True)
    if show_progress:
        print()  # newline after progress
    return combined


def write_csv(records: List[Dict], path: str) -> None:
    if not records:
        print("[ERROR] No records to write; aborting.")
        return
    fieldnames = ["Rank", "Index Number", "Name", "School", "Mark", "Grade"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    print(f"[SUCCESS] Wrote {len(records)} records to {path}")

############################ INTERACTIVE FLOW ############################

def choose_year(all_keys: List[str]) -> int | None:
    years = sorted({int(k.split("_", 1)[0]) for k in all_keys if k[:4].isdigit()})
    if not years:
        print("No years found in database.")
        return None
    while True:
        print("Available years:")
        for i, y in enumerate(years, 1):
            print(f"  {i}. {y}")
        choice = input("Select year (number or value) (Enter to quit): ").strip()
        if not choice:
            return None
        if choice.isdigit():
            # If user typed an index number
            idx = int(choice)
            if 1 <= idx <= len(years):
                return years[idx - 1]
            # If user typed the actual year value
            year_val = int(choice)
            if year_val in years:
                return year_val
        print("Invalid choice; try again.\n")


def get_available_papers(all_keys: List[str], year: int) -> List[str]:
    prefix = f"{year}_"
    papers = {k.split("_", 2)[1] for k in all_keys if k.startswith(prefix)}

    def _sort_key(name: str):
        m = re.search(r"\d+", name)
        if m:
            # Papers with digits come first, sorted numerically
            return (0, int(m.group()))
        # Papers without digits come after, sorted alphabetically
        return (1, name.lower())

    return sorted(papers, key=_sort_key)


def choose_paper(papers: List[str]) -> str | None:
    if not papers:
        return None
    while True:
        print("Available papers:")
        for i, p in enumerate(papers, 1):
            print(f"  {i}. {p}")
        choice = input("Select paper (number or name) (Enter to cancel): ").strip().lower()
        if not choice:
            return None
        # number selection
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(papers):
                return papers[idx - 1]
        # direct name selection
        if choice in papers:
            return choice
        print("Invalid choice; try again.\n")


def detect_index_range(all_keys: List[str], year: int, paper: str) -> tuple[int, int] | None:
    prefix = f"{year}_{paper}_"
    year_str = str(year)
    indexes = [
        int(k.rsplit("_", 1)[-1])
        for k in all_keys
        if k.startswith(prefix) and k.rsplit("_", 1)[-1].startswith(year_str)
    ]
    if not indexes:
        return None
    return min(indexes), max(indexes)


def main() -> None:
    try:
        print("Fetching available years...", end="", flush=True)
        keys = fetch_all_result_keys()
        print(" done.\n")
    except Exception as exc:
        print(f"\n[ERROR] Could not connect to Firebase: {exc}")
        return

    while True:
        year = choose_year(keys)
        if year is None:
            print("Exiting.")
            break

        available_papers = get_available_papers(keys, year)
        if not available_papers:
            print("No papers found for that year.\n")
            continue
        paper = choose_paper(available_papers)
        if paper is None:
            continue

        rng = detect_index_range(keys, year, paper)
        if not rng:
            print("No records found for that year & paper.\n")
            continue

        start_idx, end_idx = rng
        print(f"Detected index range: {start_idx}-{end_idx}")
        proceed = input("Press Enter to proceed, or type 'b' to go back: ").strip().lower()
        if proceed == 'b':
            print()
            continue

        default_name = f"results_{year}_{paper}"
        prompt = f"Enter output CSV filename (without .csv) or press Enter for default ({default_name}), or type 'b' to go back: "
        filename_input = input(prompt).strip()
        if filename_input.lower() == 'b':
            print()
            continue
        filename = filename_input or default_name
        csv_path = os.path.join(os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__)), filename + ".csv")

        global YEAR, PAPER_NAME, START_INDEX, END_INDEX
        YEAR = year
        PAPER_NAME = paper
        START_INDEX, END_INDEX = start_idx, end_idx

        print("Fetching records... This may take a moment.")
        data = gather_records(start_idx, end_idx)
        if not data:
            print("No data retrieved.\n")
            continue
        write_csv(data, csv_path)
        print()


if __name__ == "__main__":
    main()
