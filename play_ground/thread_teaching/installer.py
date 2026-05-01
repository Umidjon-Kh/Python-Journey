import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from queue import Queue

import requests
from tqdm import tqdm

MAX_WORKERS = 3
DOWNLAOD_DIR = "downloads"
TIMEOUT = 30

# real little size files for downloading
URLS = [
    "https://speed.hetzner.de/100MB.bin",
    "https://proof.ovh.net/files/10Mb.dat",
    "https://ash-speed.hetzner.com/10MB.bin",
    "https://speed.cloudflare.com/__down?bytes=1000000",
    "https://httpbin.org/bytes/500000",
]

# main objects for threads
queue = Queue()
lock = threading.Lock()
semaphore = threading.Semaphore(MAX_WORKERS)
stop_event = threading.Event()
results = []  # in this sequence e store all results

os.makedirs(DOWNLAOD_DIR, exist_ok=True)


def producer():
    for url in URLS:
        # returns False if stop signal is not received
        if stop_event.is_set():
            break
        queue.put(url)
        print(f"📥 added to queue: {url}")

    # Notify workers that all urls is downloaded
    for _ in range(MAX_WORKERS):
        queue.put(None)  # None - sign breaking all workers


def download(url):
    with semaphore:  # max count of workers can acquire
        if stop_event.is_set():
            return None

        try:
            file_name = url.split("/")[-1] or f"file_{time.time()}"
            filepath = os.path.join(DOWNLAOD_DIR, file_name)

            print(f"⬇️ start downloading: {file_name}")

            response = requests.get(url, stream=True, timeout=10)
            total = int(response.headers.get("content-length", 0))

            with open(filepath, "wb") as f:
                with tqdm(
                    total=total, unit="B", unit_scale=True, desc=file_name, leave=True
                ) as bar:
                    for chunk in response.iter_content(chunk_size=1024):
                        if stop_event.is_set():
                            return None
                        f.write(chunk)
                        bar.update(len(chunk))

            return filepath

        except Exception as exc:
            print(f"Error {url}: {exc}")
            return None


def consumer():
    while True:
        url = queue.get()

        if url is None:
            queue.task_done()
            break

        result = download(url)

        with lock:
            if result is not None:
                results.append(result)

        queue.task_done()


def monitor():
    while not stop_event.is_set():
        with lock:
            done = len(results)
        print(f"📊 downloaded files: {done}/{len(URLS)}")
        time.sleep(3)  # updates visual every 3 seconds


def main():
    print("🚀 Start!")

    # Timer - after 30 seconds stops everything
    # It needed to avoid inifinity download or any other loop that not completes
    timer = threading.Timer(30, stop_event.set)
    timer.daemon = True
    timer.start()

    # daemon thread - monitoring
    monitor_thread = threading.Thread(target=monitor, daemon=True)
    monitor_thread.start()

    # producer thread - puts urls into a queue
    producer_thread = threading.Thread(target=producer)
    producer_thread.start()

    # consumer threads created via ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for _ in range(MAX_WORKERS):
            executor.submit(consumer)

    producer_thread.join()
    queue.join()

    timer.cancel()  # caceling time if eveything is downloaded
    stop_event.set()  # breaking monitor

    with lock:
        print(f"\n✅ Completed! Downloaded: {len(results)} files")
        for r in results:
            print(f"    📁 {r}")


if __name__ == "__main__":
    main()
