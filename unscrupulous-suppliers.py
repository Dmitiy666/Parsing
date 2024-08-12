#!/usr/bin/env python3

import csv
import json
import os.path
from http.client import BadStatusLine
from tkinter import filedialog, messagebox
from urllib.parse import urlencode

import requests
import urllib3
from mechanicalsoup import Browser
from requests import exceptions


class Http403(exceptions.HTTPError): pass
class Http404(exceptions.HTTPError): pass
class Http500(exceptions.HTTPError): pass


class excel_rus(csv.unix_dialect):
    delimiter = ';'
    quoting = csv.QUOTE_MINIMAL


HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64; rv:122.0) Gecko/20100101 Firefox/122.0',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3',
    'Accept-Encoding': 'gzip, deflate, br',
    'DNT': '1',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'cross-site',
    'Sec-GPC': '1',
    'Pragma': 'no-cache',
    'Cache-Control': 'no-cache',
}


def do_request(url, **kwargs):
    global proxy, request_counter

    error = ''

    for _ in range(5):
        try:
            print("->", url, flush=True)
            resp = br.get(url, timeout=(30, 120), verify=False)

            if resp.status_code >= 400:
                print('\tError %i: %s' % (resp.status_code, url), flush=True)
                resp.raise_for_status()

            if resp.status_code >= 300:
                use_timeout = False
                netloc = urlparse(url).netloc
                url = resp.headers['Location']
                print('+ Redirect:', url, flush=True)
                if url.startswith('/'):
                    url = 'https://%s/%s' % (netloc, url)

                continue

            return resp
        except (
            exceptions.ReadTimeout,
            exceptions.ConnectionError,
            exceptions.ChunkedEncodingError
        ) as e:
            error = '\t[ HTTP ]\t%s\n\t%s' % (url, str(e))
            print(error, flush=True)
            sleep(10)
        except (
            BadStatusLine,
            exceptions.ContentDecodingError
        ) as e:
            error = '>>> \t[ %s ]\t%s\n\t%s' % (type(e), url, str(e))
            print(error, flush=True)
            sleep(10)
        except exceptions.TooManyRedirects:
            error = '>>> \t[ TooManyRedirects ]\t' + url
            print(error, flush=True)
            sleep(180)
        except exceptions.HTTPError as e:
            error = '>>> \t[ %s ]\t%s' % (str(e), url)
            print(error, flush=True)

            if resp.status_code == 403:
                raise Http403(response=resp, request=resp.request)

            if resp.status_code == 404:
                raise Http404(response=resp, request=resp.request)

            if resp.status_code == 500:
                raise Http500(response=resp, request=resp.request)

            sleep(180)

    print('\n\n!!! ' + error, flush=True, file=sys.stderr)
    exit(os.EX_IOERR)


def main():
    global br

    inp_filepath = filedialog.askopenfilename(
        title="Выбор входного файла",
        filetypes=(("Таблица CSV", "*.csv"),),
        defaultextension=".csv"
    )
    print("Входной файл:", inp_filepath, flush=True)
    if not inp_filepath or not os.path.exists(inp_filepath):
        messagebox.showerror(title="Ошибка выбора файла", message="Входной файл не выбран или не существует")
        exit()

    inp_f = open(inp_filepath, encoding="utf_8_sig")
    inp = csv.DictReader(inp_f, dialect=excel_rus)

    out_filepath = filedialog.asksaveasfilename(
        title="Выбор выходного файла",
        filetypes=(("Таблица CSV", "*.csv"),),
        defaultextension=".csv"
    )
    print("Выходной файл:", out_filepath, flush=True)
    if not out_filepath:
        messagebox.showerror(title="Ошибка выбора файла", message="Выходной файл не выбран или не существует")
        exit()

    if inp_filepath == out_filepath:
        messagebox.showerror(title="Ошибка выбора файла", message="Нет возможности писать результать обработки во входной файл")
        exit()

    out_f = open(out_filepath, "w", encoding="utf-8")
    out = csv.DictWriter(
        out_f,
        fieldnames=["ФИО", "ИНН", "Дата попадания", "Количество попаданий", "URL", "SearchURL"],
        dialect=excel_rus
    )
    out.writeheader()
    out_f.flush()

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    br = Browser()
    br.session.headers = HEADERS

    params = {
        "strictEqual": "true",
        "sortBy": "UPDATE_DATE",
        "pageNumber": 1,
        "sortDirection": "false",
        "recordsPerPage": "_50",
        "showLotsInfoHidden": "false",
        "fz94": "on",
        "fz223": "on",
        "ppRf615": "on",
        "customerINN": ""
    }

    for rec in inp:
        params["customerINN"] = rec["ИНН"]
        params["pageNumber"] = 1
        url = "https://zakupki.gov.ru/epz/dishonestsupplier/search/results.html?" + urlencode(params)
        print("\n##", url, flush=True)

        while True:
            html = do_request(url).soup

            results = []
            records_count = html.find("div", "search-results__total").string.strip().split(" ", 1)[0]
            if not records_count:
                print("<Skipped: ИНН %s не найден>" % rec["ИНН"], flush=True)
                break

            records_count = int(records_count)
            for res in html("div", "registry-entry__form"):
                data = {
                    "ФИО": rec["ФИО"],
                    "ИНН": rec["ИНН"],
                    "Дата попадания": res.find(
                            "div", "data-block__title", string="Включено"
                        ).find_next_sibling(
                            "div", "data-block__value"
                        ).string.strip(),
                    "Количество попаданий": records_count,
                    "URL": res.select_one("div.registry-entry__header-mid__number > a")["href"],
                    "SearchURL": url
                }
                print(">", json.dumps(data, ensure_ascii=False), flush=True)
                out.writerow(data)
                out_f.flush()

            if records_count < params["pageNumber"] * 50:
                break

            params["pageNumber"] += 1
            url = "https://zakupki.gov.ru/epz/dishonestsupplier/search/results.html?" + urlencode(params)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        import traceback
        import sys
        traceback.print_exc(file=sys.stderr)

    input("\n\nНажэмите Enter для закрытия окна")
