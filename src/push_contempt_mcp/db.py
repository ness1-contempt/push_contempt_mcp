"""Accesso diretto al DB di WordPress/WooCommerce — solo lettura.

Qui vanno tool a basso rischio e alto volume (liste, ricerche, confronto
nomi per la scansione cartella prodotti). Le scritture vere e proprie oggi
passano quasi tutte dalla REST API del plugin push_contempt (vedi
inventory_tools.py, pricing_tools.py, seo_tools.py, product_tools.py,
catalog_health.py, sales_tools.py) - solo le due operazioni rimaste su
automazione browser in browser_tools.py (modifica prezzo con anteprima,
SEO categoria) non passano né da qui né da REST.
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
