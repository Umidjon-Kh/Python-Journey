from threading import Semaphore, Thread
from time import sleep

semaphore = Semaphore(3)


def task(name):
    with semaphore:
        print(f"{name} entered semaphore lock")
        sleep(2)
        print(f"{name} exiting sempahore lock")


threads = [Thread(target=task, args=(f"Thread {i}",)) for i in range(7)]

for t in threads:
    t.start()
for t in threads:
    t.join()
