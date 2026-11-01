"""Bíblia Livre (BLIVRE): importação para SQLite e referências bíblicas em pt-BR."""

from blivre.livros import BOOKS, Book, book_by_usfm
from blivre.referencias import (
    InvalidReferenceError,
    Reference,
    VerseRange,
    format_canonical,
    format_reference,
    parse_reference,
)

__all__ = [
    "BOOKS",
    "Book",
    "InvalidReferenceError",
    "Reference",
    "VerseRange",
    "book_by_usfm",
    "format_canonical",
    "format_reference",
    "parse_reference",
]
