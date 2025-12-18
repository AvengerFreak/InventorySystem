"""Data models for the Inventory API.

This module defines the SQLModel models used by the API: Category, Item and
History.

Copyright (c) Bryn Gwalad 2025
"""

from datetime import datetime
from typing import Optional, List

from sqlmodel import Field, Relationship, SQLModel


class Category(SQLModel, table=True):
    """A category for grouping items.

    Attributes:
        id: primary key
        name: category name
        description: optional free-text description
        items: reverse relationship to Item
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    description: Optional[str] = None
    items: List["Item"] = Relationship(back_populates="category")


class Item(SQLModel, table=True):
    """An inventory item.

    Attributes:
        id: primary key
        name: item name
        category_id: foreign key to Category
        description: optional description
        image_file: filename or external file id (e.g. Google Drive file id)
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    category_id: Optional[int] = Field(default=None, foreign_key="category.id")
    description: Optional[str] = None
    image_file: Optional[str] = None
    category: Optional[Category] = Relationship(back_populates="items")


class History(SQLModel, table=True):
    """Audit/history table to log modifications to Category and Item.

    The ``id`` field is a composed string used to make simple text searches
    convenient while the record keeps structured fields for queries.
    """

    id: str = Field(primary_key=True)
    table_operation: str
    table_modified: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    user_id: str
    modified_id: Optional[int] = None
