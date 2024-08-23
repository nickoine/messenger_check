#!/usr/env/bin python3
from __future__ import annotations

# External
import json
import requests
import asyncio
from telethon import TelegramClient
from telethon.tl.types import InputPhoneContact
from telethon.tl.functions.contacts import ImportContactsRequest

# Builtin
import logging
from pathlib import Path
from datetime import datetime
from queue import Queue
from threading import Thread
from abc import ABC, abstractmethod

from typing import *
if TYPE_CHECKING:
    from typing import List, Any, Generator, Dict, Tuple

# Use your values from my.telegram.org.
api_id = 0
api_hash = ""
session_name = "anon"
client = TelegramClient(session_name, api_id, api_hash)

# Use your values from whatsapp Green API instance.
wa_instance_id = 0
wa_api_token = ""
wa_api_url = "" # https://0000.api.greenapi.com

date = datetime.now().strftime("%d.%m.%Y-%H:%M:%S")
target_file, output_file = "target_list.csv", f"results_{date}.json"
path_to_file, path_to_output = f"{Path.cwd()}/{target_file}", f"{Path.cwd()}/{output_file}"

logger = logging.getLogger(__name__)
if not logger.hasHandlers():
    logging.basicConfig(
        level=logging.ERROR,
        format="%(asctime)s - %(levelname)s - %(message)s"
    )


class Reader:
    """Reads data from the file setting up a pipeline."""
    be_checked = 0

    def __init__(self, filepath: str) -> None:
        self.file = filepath
        self.checked_numbers = []

    def read(self) -> Generator[str, None, None]:
        try:
            with open(self.file, "r") as f:
                file_empty = True
                for row in f:
                    phone_num = row.strip()

                    # Skip empty rows
                    if not phone_num:
                        continue

                    file_empty = False

                    if phone_num.isdigit():
                        if phone_num not in self.checked_numbers:
                            self.checked_numbers.append(phone_num)
                            self.be_checked += 1
                            yield phone_num
                        else:
                            logging.warning(f"Duplicate number found: {phone_num}")
                    else:
                        logging.error(f"Invalid number: {phone_num}")
                print(f"{self.be_checked} numbers was checked")

                if file_empty:
                    raise ValueError("File is empty, give it phone numbers")
        except (FileNotFoundError, IOError) as e:
            logging.error(f"Error opening file {self.file}: {e}. The file must be in the specified path.")
        except ValueError as ve:
            logging.error(f"{ve}")


class Writer:
    """Writes data from handlers to a JSON file."""

    def __init__(self, file: str) -> None:
        self.file = file
        self.opened_lists = {"Telegram": False, "Whatsapp": False}
        self.first_write = True

    def write_json(self, handler_type: str, result: Dict | None) -> None:
        if result:
            with open(self.file, 'a') as f:
                if self.first_write:
                    f.write('{\n')
                    self.first_write = False

                if not self.opened_lists[handler_type]:
                    # Start the list for this handler
                    if any(self.opened_lists.values()):
                        f.write(',\n')
                    f.write(f'    "{handler_type}": [\n')
                    self.opened_lists[handler_type] = True
                else:
                    # Add a comma before the new object if it's not the first in the list
                    f.write(',\n')

                f.write(f'        {json.dumps(result, indent=8)}')

    def finalize(self) -> None:
        with open(self.file, 'a') as f:
            for handler_type, opened in self.opened_lists.items():
                if opened:
                    f.write('\n    ]')
            f.write('\n}\n')


class Observer(ABC):
    """Observer Interface: Defines the contract for observers."""

    @abstractmethod
    def update(self, data: Any) -> None:
        pass


class QueueHandler(ABC):
    """QueueHandler Interface: Defines the contract for queue handlers."""

    def __init__(self) -> None:
        self.queue = Queue()

    def enqueue_data(self, data: Any) -> None:
        self.queue.put(data)

    @abstractmethod
    def process_queue(self, data: Any) -> None:
        pass

    def worker(self) -> None:
        while not self.queue.empty():
            data = self.queue.get()
            self.process_queue(data)
            self.queue.task_done()


class ObserverManager(object):
    """Manages observers and notifies them with data."""

    def __init__(self) -> None:
        self.observers = []

    def register_observer(self, observer: Observer) -> None:
        self.observers.append(observer)

    def notify_observers(self, reader_data: str) -> Generator[Tuple[Observer, type], None, None]:
        for observer in self.observers:
            updated_data = observer.update(reader_data)
            observer_class = type(observer)
            yield observer_class, updated_data,


class QueueManager(object):
    """Manages the relationship between observers and their corresponding handlers."""

    def __init__(self, reader: Reader, obs_man: ObserverManager) -> None:
        self.queue_handlers = {}  # keys are instances of observers, values are instances of handlers
        self.threads = []
        self.reader = reader
        self.obs_man = obs_man

    def register_handler(self, observer_class: Observer, handler: QueueHandler) -> None:
        self.queue_handlers[type(observer_class)] = handler

    def enqueue_data(self, observer_class: Observer, data: [InputPhoneContact | Tuple]) -> None:
        if observer_class in self.queue_handlers:
            self.queue_handlers[observer_class].enqueue_data(data)

    def process_data(self) -> None:
        for data in self.reader.read():
            for observer_class, updated_data in self.obs_man.notify_observers(data):
                self.enqueue_data(observer_class, updated_data)

    def start_workers(self) -> None:
            for handler in self.queue_handlers.values():
                if isinstance(handler, TelegramQueueHandler):
                    # Start async worker in a separate thread
                    tg_thread = Thread(target=handler.start_async_worker, daemon=False)
                    tg_thread.start()
                    self.threads.append(tg_thread)
                else:
                    # Run synchronous worker in the main thread
                    handler.worker()

            for thread in self.threads:
                thread.join()

class TelegramQueueHandler(QueueHandler):
    """Manages queue for processing data asynchronously."""

    def __init__(self, writer: Writer):
        super().__init__()
        self.tg = Telegram()
        self.wr = writer

    async def process_queue(self, data: InputPhoneContact) -> None:
        res = await self.tg.tg_import_contact(data)
        if res is not None:
            self.wr.write_json("Telegram", res)
        else:
            pass

    async def async_worker(self) -> None:
        while True:
            if self.queue.empty():
                break
            data = await self.get_queue_data()
            await self.process_queue(data)
            self.queue.task_done()

    async def get_queue_data(self) -> InputPhoneContact:
        return await asyncio.get_event_loop().run_in_executor(None, self.queue.get)

    def start_async_worker(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(loop.create_task(self.async_worker()))
        except Exception as e:
            print(f"Exception in event loop: {e}")
        finally:
            loop.stop()
            loop.close()


class WhatsappQueueHandler(QueueHandler):
    """Manages queue for processing data synchronously."""

    def __init__(self, writer: Writer):
        super().__init__()
        self.wa = Whatsapp()
        self.wr = writer

    def process_queue(self, data: Tuple) -> None:
        res = self.wa.check_exist_whatsapp(data)
        if res is not None:
            self.wr.write_json("Whatsapp", res)
        else:
            pass

# numbers which has no telegram account by the phone_number
has_no_telegram = {}


class Telegram(Observer):
    """Handle data processing specific to messenger."""

    def __init__(self):
        self.data = None

    def telegram_contact(self) -> InputPhoneContact:
        """Add contact to telegram contacts."""
        account_future_contact = InputPhoneContact(
            client_id=0, phone=self.data, first_name=f"{self.data}", last_name="")
        return account_future_contact

    def update(self, manager_data: str) -> InputPhoneContact:
        self.data = manager_data
        return self.telegram_contact()

    @staticmethod
    async def tg_import_contact(phone_contact: InputPhoneContact) -> Dict | None:
        async with client:
            # for contact in phone_contact:
            res = await client(ImportContactsRequest([phone_contact]))
            user_dict = res.to_dict()
            if user_dict.get("users"):
                new = {
                    "phone": user_dict["users"][0]["phone"],
                    "username": user_dict["users"][0]["username"],
                    "premium": user_dict["users"][0]["premium"],
                    "verified": user_dict["users"][0]["verified"]
                }
                return new
            else:
                has_no_telegram.update({phone_contact.to_dict().get("phone"): user_dict})


class Whatsapp(Observer):
    """Handle data processing specific to messenger."""

    error_logged = False

    def __init__(self) -> None:
        self.data = None

    def whatsapp_data(self) -> Tuple:
        url = f"{wa_api_url}/waInstance{wa_instance_id}/checkWhatsapp/{wa_api_token}"
        payload = {"phoneNumber": self.data}
        headers = {"Content-Type": "application/json"}
        return url, payload, headers,

    def update(self, manager_data: str) -> Tuple:
        self.data = manager_data
        return self.whatsapp_data()

    @staticmethod
    def check_exist_whatsapp(request_data: Tuple) -> Dict[str, str] | None:
        url, payload, headers = request_data
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=5)
            r.raise_for_status()
            user_dict = r.json()
            if user_dict.get("existsWhatsapp"):
                user_dict["existsWhatsapp"] = payload.get("phoneNumber")
                return user_dict
        except (requests.exceptions.RequestException, ValueError) as e:
            if not Whatsapp.error_logged:
                print(f"WhatsApp API error, monthly quota has been exceeded,\n"
                      f"please go to your personal account and change the WhatsApp tariff.\n"
                      f"{e}")
                Whatsapp.error_logged = True
            return None

def main():
    print(f"Run")

    # Initialize the Writer class with the output file path to store the results in a JSON file.
    writer = Writer(path_to_output)

    # Create instances of the messenger classes, which will act as observers.
    tg_observer = Telegram()
    wa_observer = Whatsapp()

    # Initialize the QueueHandlers with the writer.
    # These handlers manage the processing of data asynchronously (Telegram) and synchronously (WhatsApp).
    tg_handler = TelegramQueueHandler(writer)
    wa_handler = WhatsappQueueHandler(writer)

    # Initialize the Reader class with the path to the input file, which contains the phone numbers to be processed.
    reader = Reader(path_to_file)

    # Create an instance of ObserverManager to manage the observers.
    observer_manager = ObserverManager()

    # Create an instance of QueueManager to manage the queue of data and register the observers and handlers.
    queue_manager = QueueManager(reader, observer_manager)

    # Register the observers with their respective handlers.
    queue_manager.register_handler(tg_observer, tg_handler)
    queue_manager.register_handler(wa_observer, wa_handler)

    # Register the observers with the ObserverManager.
    observer_manager.register_observer(tg_observer)
    observer_manager.register_observer(wa_observer)

    # Start processing the data, reading from the input file and distributing it to the registered handlers.
    print("Data is loading...")
    queue_manager.process_data()

    # Start the worker threads for processing the data.
    queue_manager.start_workers()

    # Finalize the JSON output by closing the JSON structure after all data has been processed and written.
    writer.finalize()
    print(f"Done, the results are in {path_to_output}.")

if __name__ == "__main__":
    main()
