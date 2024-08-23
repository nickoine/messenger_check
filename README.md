# Messenger check

### Overview:

Messenger Check is a Python-based program
designed to process a list of phone numbers,
verify their existence on messaging platforms such as Telegram and WhatsApp(so far),
and store the results in a structured JSON file. In case of a large dataset of phone numbers
the program adheres to incremental processing of data without excessive memory consumption.

### Installation:
1) `git clone`
2) `venv`
3) `pip install -r requirements.txt`

### Prerequisites:
1) Whatsapp and Telegram accounts.

### Set Up Configuration:
1) go to https://green-api.com/ and https://my.telegram.org/ to obtain `api_id, api_hash, api_url`.
2) open main.py and put your parameters to the corresponding variables.
3) put the phone numbers, one per raw, in `target_list.csv`.

### Proper Usage:
**1) `target_list.csv`  must be in the same directory as a `main.py `**.

**2) to start a program run `$ python3 main.py`**.

**3) after the program is finished the `results.json` will appear in the program directory**.

### Warnings:
1) Whatsapp API instance developer tariff has limitations of 100 requests per month.
2) Checked phone numbers by Telegram will be added to contacts of account you use.
3) `target_list.csv`  must not be renamed (unless you know what you doing).
