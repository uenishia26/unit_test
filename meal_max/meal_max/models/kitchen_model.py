from dataclasses import dataclass
import logging
import os
import sqlite3
from typing import Any

from meal_max.utils.sql_utils import get_db_connection
from meal_max.utils.logger import configure_logger


logger = logging.getLogger(__name__)
configure_logger(logger)


@dataclass
class Meal:
    """Represents a meal with specific attributes.

    Attributes:
        id (int): The unique identifier for the meal.
        meal (str): The name of the meal.
        cuisine (str): The cuisine type of the meal.
        price (float): The price of the meal.
        difficulty (str): The preparation difficulty level of the meal, must be 'LOW', 'MED', or 'HIGH'.
    """

    id: int
    meal: str
    cuisine: str
    price: float
    difficulty: str

    def __post_init__(self):
        """Validates price and difficulty level upon initialization.

        Raises:
            ValueError: If `price` is negative or `difficulty` is not 'LOW', 'MED', or 'HIGH'.
        """
        if self.price < 0:
            raise ValueError("Price must be a positive value.")
        if self.difficulty not in ['LOW', 'MED', 'HIGH']:
            raise ValueError("Difficulty must be 'LOW', 'MED', or 'HIGH'.")


def create_meal(meal: str, cuisine: str, price: float, difficulty: str) -> None:
    """Adds a new meal to the database.

    Args:
        meal (str): The name of the meal.
        cuisine (str): The cuisine type of the meal.
        price (float): The price of the meal, must be a positive number.
        difficulty (str): The preparation difficulty, must be 'LOW', 'MED', or 'HIGH'.

    Raises:
        ValueError: If `price` is not positive or `difficulty` is invalid.
        sqlite3.IntegrityError: If a meal with the same name already exists.
        sqlite3.Error: For other database errors.
    """
    if not isinstance(price, (int, float)) or price <= 0:
        raise ValueError(f"Invalid price: {price}. Price must be a positive number.")
    if difficulty not in ['LOW', 'MED', 'HIGH']:
        raise ValueError(f"Invalid difficulty level: {difficulty}. Must be 'LOW', 'MED', or 'HIGH'.")

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO meals (meal, cuisine, price, difficulty)
                VALUES (?, ?, ?, ?)
            """, (meal, cuisine, price, difficulty))
            conn.commit()
            logger.info("Meal successfully added to the database: %s", meal)

    except sqlite3.IntegrityError:
        logger.error("Duplicate meal name: %s", meal)
        raise ValueError(f"Meal with name '{meal}' already exists")

    except sqlite3.Error as e:
        logger.error("Database error: %s", str(e))
        raise e


def clear_meals() -> None:
    """Recreates the meals table, effectively deleting all meals.

    Raises:
        sqlite3.Error: If any database error occurs.
    """
    try:
        with open(os.getenv("SQL_CREATE_TABLE_PATH", "/app/sql/create_meal_table.sql"), "r") as fh:
            create_table_script = fh.read()
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.executescript(create_table_script)
            conn.commit()
            logger.info("Meals cleared successfully.")

    except sqlite3.Error as e:
        logger.error("Database error while clearing meals: %s", str(e))
        raise e


def delete_meal(meal_id: int) -> None:
    """Marks a meal as deleted in the database.

    Args:
        meal_id (int): The unique identifier of the meal to delete.

    Raises:
        ValueError: If the meal is not found or has already been deleted.
        sqlite3.Error: For any database errors.
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT deleted FROM meals WHERE id = ?", (meal_id,))
            try:
                deleted = cursor.fetchone()[0]
                if deleted:
                    logger.info("Meal with ID %s has already been deleted", meal_id)
                    raise ValueError(f"Meal with ID {meal_id} has been deleted")
            except TypeError:
                logger.info("Meal with ID %s not found", meal_id)
                raise ValueError(f"Meal with ID {meal_id} not found")

            cursor.execute("UPDATE meals SET deleted = TRUE WHERE id = ?", (meal_id,))
            conn.commit()
            logger.info("Meal with ID %s marked as deleted.", meal_id)

    except sqlite3.Error as e:
        logger.error("Database error: %s", str(e))
        raise e


def get_leaderboard(sort_by: str = "wins") -> list[dict[str, Any]]:
    """Retrieves the leaderboard of meals based on battle performance.

    Args:
        sort_by (str): Sorting criterion for leaderboard, either 'wins' or 'win_pct'.

    Returns:
        list[dict[str, Any]]: A sorted list of meals with battle statistics.

    Raises:
        ValueError: If `sort_by` is not 'wins' or 'win_pct'.
        sqlite3.Error: For any database errors.
    """
    query = """
        SELECT id, meal, cuisine, price, difficulty, battles, wins, (wins * 1.0 / battles) AS win_pct
        FROM meals WHERE deleted = false AND battles > 0
    """

    if sort_by == "win_pct":
        query += " ORDER BY win_pct DESC"
    elif sort_by == "wins":
        query += " ORDER BY wins DESC"
    else:
        logger.error("Invalid sort_by parameter: %s", sort_by)
        raise ValueError("Invalid sort_by parameter: %s" % sort_by)

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()

        leaderboard = []
        for row in rows:
            meal = {
                'id': row[0],
                'meal': row[1],
                'cuisine': row[2],
                'price': row[3],
                'difficulty': row[4],
                'battles': row[5],
                'wins': row[6],
                'win_pct': round(row[7] * 100, 1)  # Convert to percentage
            }
            leaderboard.append(meal)

        logger.info("Leaderboard retrieved successfully")
        return leaderboard

    except sqlite3.Error as e:
        logger.error("Database error: %s", str(e))
        raise e


def get_meal_by_id(meal_id: int) -> Meal:
    """Retrieves a meal by its ID.

    Args:
        meal_id (int): The unique identifier of the meal.

    Returns:
        Meal: The meal with the specified ID.

    Raises:
        ValueError: If the meal is not found or has been deleted.
        sqlite3.Error: For any database errors.
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, meal, cuisine, price, difficulty, deleted FROM meals WHERE id = ?", (meal_id,))
            row = cursor.fetchone()

            if row:
                if row[5]:
                    logger.info("Meal with ID %s has been deleted", meal_id)
                    raise ValueError(f"Meal with ID {meal_id} has been deleted")
                return Meal(id=row[0], meal=row[1], cuisine=row[2], price=row[3], difficulty=row[4])
            else:
                logger.info("Meal with ID %s not found", meal_id)
                raise ValueError(f"Meal with ID {meal_id} not found")

    except sqlite3.Error as e:
        logger.error("Database error: %s", str(e))
        raise e


def get_meal_by_name(meal_name: str) -> Meal:
    """Retrieves a meal by its name.

    Args:
        meal_name (str): The name of the meal to retrieve.

    Returns:
        Meal: The meal with the specified name.

    Raises:
        ValueError: If the meal is not found or has been deleted.
        sqlite3.Error: For any database errors.
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, meal, cuisine, price, difficulty, deleted FROM meals WHERE meal = ?", (meal_name,))
            row = cursor.fetchone()

            if row:
                if row[5]:
                    logger.info("Meal with name %s has been deleted", meal_name)
                    raise ValueError(f"Meal with name {meal_name} has been deleted")
                return Meal(id=row[0], meal=row[1], cuisine=row[2], price=row[3], difficulty=row[4])
            else:
                logger.info("Meal with name %s not found", meal_name)
                raise ValueError(f"Meal with name {meal_name} not found")

    except sqlite3.Error as e:
        logger.error("Database error: %s", str(e))
        raise e


def update_meal_stats(meal_id: int, result: str) -> None:
    """Updates the battle statistics for a meal based on battle result.

    Args:
        meal_id (int): The unique identifier of the meal.
        result (str): The result of the battle, must be 'win' or 'loss'.

    Raises:
        ValueError: If the meal is not found, has been deleted, or `result` is invalid.
        sqlite3.Error: For any database errors.
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT deleted FROM meals WHERE id = ?", (meal_id,))
            try:
                deleted = cursor.fetchone()[0]
                if deleted:
                    logger.info("Meal with ID %s has been deleted", meal_id)
                    raise ValueError(f"Meal with ID {meal_id} has been deleted")
            except TypeError:
                logger.info("Meal with ID %s not found", meal_id)
                raise ValueError(f"Meal with ID {meal_id} not found")

            if result == 'win':
                cursor.execute("UPDATE meals SET battles = battles + 1, wins = wins + 1 WHERE id = ?", (meal_id,))
            elif result == 'loss':
                cursor.execute("UPDATE meals SET battles = battles + 1 WHERE id = ?", (meal_id,))
            else:
                raise ValueError(f"Invalid result: {result}. Expected 'win' or 'loss'.")

            conn.commit()

    except sqlite3.Error as e:
        logger.error("Database error: %s", str(e))
        raise e
