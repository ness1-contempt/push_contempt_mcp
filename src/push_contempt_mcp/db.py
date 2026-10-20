"""Accesso diretto al DB di WordPress/WooCommerce — solo lettura.

Qui vanno tool a basso rischio e alto volume (liste, ricerche, report).
Tutto ciò che scrive o ha effetti collaterali (ordini, pagamenti, pubblicazione
contenuti) passa invece dall'automazione browser in browser_tools.py, così
l'utente può rivedere l'operazione prima che venga confermata.
"""

import os

import pymysql
import pymysql.cursors
from dotenv import load_dotenv

load_dotenv()

TABLE_PREFIX = os.environ.get("WP_TABLE_PREFIX", "wp_")


def get_connection() -> pymysql.connections.Connection:
    return pymysql.connect(
        host=os.environ["WP_DB_HOST"],
        port=int(os.environ.get("WP_DB_PORT", "3306")),
        user=os.environ["WP_DB_USER"],
        password=os.environ["WP_DB_PASSWORD"],
        database=os.environ["WP_DB_NAME"],
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )
