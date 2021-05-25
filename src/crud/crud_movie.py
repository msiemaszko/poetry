from typing import List, Optional

from sqlalchemy import and_
from sqlalchemy.orm import Session

from src.models import Rating
from src.models.movie import Movie


class CRUDMovie:
    def get_movie(self, db: Session, movie_id: int) -> Movie:
        """ Return specific movie by id """
        return db.query(Movie).filter(Movie.id == movie_id).first()

    def get_movie_with_rate(self, db: Session, movie_id: int, user_id: int) -> dict:
        """ Return specific movie by id with rate from specific user """
        return db.query(Movie, Rating.rating)\
            .filter(Movie.id == movie_id)\
            .outerjoin(Rating, and_(Rating.movie_id == Movie.id, Rating.user_id == user_id))\
            .first()

    def get_movies(self, db: Session, skip: int = 0, limit: int = 100) -> List[Movie]:
        """Return list of movies with pagination arguments"""
        return db.query(Movie).offset(skip).limit(limit).all()

    def search_movies_by_title(self, db: Session, search_string: str) -> Optional[List[Movie]]:
        movies = db.query(Movie).filter(Movie.title.contains(search_string)).all()
        # .join(Rating)\
        return movies

    def search_movies_by_title_with_rate(self, db: Session, search_string: str, user_id: int) -> List[dict]:
        movies_rate_tuple = db.query(Movie, Rating.rating)\
            .filter(Movie.title.contains(search_string))\
            .outerjoin(Rating, and_(Rating.movie_id == Movie.id, Rating.user_id == user_id))\
            .all()
        return movies_rate_tuple


crud_movies = CRUDMovie()
