"""The ledger in MongoDB.

One document per symbol per trading day, all in one collection. A unique
index on (symbol, trade_date) makes a second entry for the same day
impossible even if two runs overlap, and it serves both queries the
repository makes.

The connection string comes from the MONGODB_URI environment variable. It
holds a password, so nothing here logs it or repeats it in an error.
"""

import logging
import os
from collections.abc import Mapping
from dataclasses import asdict
from datetime import date
from typing import Any

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError, PyMongoError

from pipeline.ledger import DayResult
from pipeline.repository import LedgerEntry, LedgerStorageError, OutOfOrderEntryError

logger = logging.getLogger(__name__)

MONGODB_URI_ENV_VAR = "MONGODB_URI"
# The database used when the connection string does not name one.
DEFAULT_DATABASE = "trading_simms"
LEDGER_COLLECTION = "ledger"
# Longest any one database operation may take, finding a server included.
# pymongo's default waits 30 seconds for a server that is not there; this
# matches the 10-second bound on market data requests.
OPERATION_TIMEOUT_MS = 10_000

UNAVAILABLE_MESSAGE = "The ledger database is unavailable. Try again shortly."


def configured_mongodb_uri() -> str | None:
    """The connection string from the environment, or None if it is not set."""
    return os.environ.get(MONGODB_URI_ENV_VAR, "").strip() or None


def entry_to_document(entry: LedgerEntry) -> dict[str, Any]:
    """The entry as a MongoDB document.

    Dates are stored as ISO strings such as "2026-11-13": BSON has no
    date-only type, and these strings sort in date order.
    """
    document = asdict(entry)
    document["trade_date"] = entry.trade_date.isoformat()
    document["signal_date"] = entry.signal_date.isoformat()
    return document


def entry_from_document(document: Mapping[str, Any]) -> LedgerEntry:
    """The entry a stored document describes."""
    fields = {key: value for key, value in document.items() if key != "_id"}
    fields["trade_date"] = date.fromisoformat(fields["trade_date"])
    fields["signal_date"] = date.fromisoformat(fields["signal_date"])
    fields["day"] = DayResult(**fields["day"])
    return LedgerEntry(**fields)


def _unavailable(exc: PyMongoError) -> LedgerStorageError:
    """Log a failed database operation and return the error to raise for it.

    The driver's message goes to the log and stays out of the error, whose
    text is shown to API callers: the message names the cluster's hosts.
    """
    logger.warning("ledger_storage_unavailable %s: %s", type(exc).__name__, exc)
    return LedgerStorageError(UNAVAILABLE_MESSAGE)


class MongoLedgerRepository:
    """A LedgerRepository kept in one MongoDB collection."""

    def __init__(self, collection: Collection) -> None:
        self.collection = collection
        self._index_ensured = False

    def latest(self, symbol: str) -> LedgerEntry | None:
        try:
            document = self.collection.find_one(
                {"symbol": symbol}, sort=[("trade_date", DESCENDING)]
            )
        except PyMongoError as exc:
            raise _unavailable(exc) from exc

        return entry_from_document(document) if document is not None else None

    def history(self, symbol: str) -> list[LedgerEntry]:
        try:
            documents = list(
                self.collection.find({"symbol": symbol}).sort("trade_date", ASCENDING)
            )
        except PyMongoError as exc:
            raise _unavailable(exc) from exc

        return [entry_from_document(document) for document in documents]

    def append(self, entry: LedgerEntry) -> None:
        latest = self.latest(entry.symbol)

        if latest is not None and entry.trade_date <= latest.trade_date:
            raise OutOfOrderEntryError(
                f"{entry.symbol} already has an entry for {latest.trade_date}; "
                f"cannot record {entry.trade_date}."
            )

        try:
            self._ensure_unique_index()
            self.collection.insert_one(entry_to_document(entry))
        except DuplicateKeyError as exc:
            # Another run recorded this day after the check above. The index
            # is what keeps the two from both being stored.
            raise OutOfOrderEntryError(
                f"{entry.symbol} already has an entry for {entry.trade_date}."
            ) from exc
        except PyMongoError as exc:
            raise _unavailable(exc) from exc

    def _ensure_unique_index(self) -> None:
        # Created by the first write rather than on connecting, so a process
        # that only reads the ledger needs no permission to create indexes.
        # Asking for an index that already exists does nothing.
        if not self._index_ensured:
            self.collection.create_index(
                [("symbol", ASCENDING), ("trade_date", ASCENDING)], unique=True
            )
            self._index_ensured = True


def ledger_repository_from_uri(
    uri: str, collection_name: str = LEDGER_COLLECTION
) -> MongoLedgerRepository:
    """A repository on the database a connection string points to.

    The database is the one named in the string's path, or DEFAULT_DATABASE
    if it names none. Nothing is connected here: the first operation does
    that, and raises LedgerStorageError if the database cannot be reached.
    """
    try:
        # connect=False leaves all network activity, including the DNS lookup
        # for a mongodb+srv:// address, to the first operation, so the only
        # thing that can fail here is the string itself.
        client = MongoClient(uri, connect=False, timeoutMS=OPERATION_TIMEOUT_MS)
        database = client.get_default_database(default=DEFAULT_DATABASE)
    except (PyMongoError, ValueError, TypeError):
        # The driver's message for a malformed string can quote part of it,
        # and so part of the password. Neither it nor the original error is
        # passed on.
        raise LedgerStorageError(
            f"{MONGODB_URI_ENV_VAR} is not a valid MongoDB connection string."
        ) from None

    return MongoLedgerRepository(database[collection_name])
