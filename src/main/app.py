from typing import List

import uvicorn
from fastapi import Body, Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from src.auth import JWTBearer, hash_password, sign_jwt
from src.crud import crud_movie, crud_rate, crud_user
from src.database import db_base, db_engine, get_db
from src.schemas.movie import MovieSchema
from src.schemas.rating import RatingCreateSchema, RatingSchema
from src.schemas.user import (UserCreateSchema, UserLoginSchema, UserSchema, UserTokenizedSchema)

from src.rcmmnd import rcmmnd

# Apply migrations to db and populate it
db_base.metadata.create_all(bind=db_engine)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://localhost:3000",
        "*"  # fck the cors
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/signup", tags=["user"], response_model=UserTokenizedSchema)
async def create_user(user: UserCreateSchema, db: Session = Depends(get_db)):
    """POST: Register new user"""
    db_user = crud_user.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered"
        )

    try:
        new_user = crud_user.create_user(db=db, new_user=user)
        if new_user:
            token = sign_jwt(new_user.email).access_token
            user = UserSchema.from_orm(new_user)
            logged_user = UserTokenizedSchema(user=user, access_token=token)
            return logged_user
    except:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Registration error"
        )


@app.post("/login", tags=["user"], response_model=UserTokenizedSchema)
async def user_login(
        user: UserLoginSchema = Body(...),
        db: Session = Depends(get_db)
):
    db_user = crud_user.get_user_by_email(db, email=user.email)
    if db_user:
        if db_user.hashed_password == hash_password(user.password):
            token = sign_jwt(user.email).access_token
            user = UserSchema.from_orm(db_user)
            logged_user = UserTokenizedSchema(user=user, access_token=token)
            return logged_user
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST, detail="Wrong login details!"
    )


@app.get("/users", tags=["user"], response_model=List[UserSchema])
async def read_users(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """GET: Return all user with pagination arguments"""
    users = crud_user.get_users(db, skip=skip, limit=limit)
    return users


@app.get("/users/{user_id}", tags=["user"], response_model=UserSchema)
async def read_user(user_id: int, db: Session = Depends(get_db)):
    """GET: Return specific user by id"""
    db_user = crud_user.get_payload(db, user_id=user_id)
    if db_user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
        )
    return db_user


@app.get("/movies/{movie_id}", tags=["movies"], response_model=MovieSchema)
async def read_movie_with_rating(
        movie_id: int,
        token: JWTBearer = Depends(JWTBearer()),
        db: Session = Depends(get_db)
):
    """ GET: Return specific movie by id with user rate - authentication required """
    user = crud_user.get_user_from_payload(payload=token.get_payload(), db=db)
    movie_tuple = crud_movie.get_movie_with_rate(db, movie_id, user.id)

    if movie_tuple:
        # convert tuple to movie schema
        i_movie, i_rate = movie_tuple
        db_movie = MovieSchema.from_orm(i_movie)
        db_movie.user_rating = i_rate
        return db_movie
    else:
        return None
        # TODO: Sprawdzić to None


@app.get("/movies/", tags=["movies"], response_model=List[MovieSchema])
async def read_movies(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    """ Get list of movies """
    return crud_movie.get_movies(db=db, skip=skip, limit=limit)


@app.get("/movies/search/{req_search_str}", tags=["movies"], response_model=List[MovieSchema])
async def search_movies_with_rates_attached(
        req_search_str: str,
        token: JWTBearer = Depends(JWTBearer()),
        db: Session = Depends(get_db)
):
    """ Searches for movies by title with user ratings attached """
    user = crud_user.get_user_from_payload(db=db, payload=token.get_payload())
    movies_rate_tuple = await crud_movie.search_movies_by_title_with_rate(db=db, search_string=req_search_str,
                                                                          user_id=user.id)

    # convert list of tuple to list with movie schemas
    movies_with_user_rate = []
    for i_movie, i_rate in movies_rate_tuple:
        movie = MovieSchema.from_orm(i_movie)
        movie.user_rating = i_rate
        movies_with_user_rate.append(movie)

    return movies_with_user_rate


@app.post("/movies/rate/", tags=["ratings"], dependencies=[Depends(JWTBearer())], response_model=RatingSchema)
async def rate_movie(req_rating: RatingCreateSchema, db: Session = Depends(get_db)):
    """ Create or update user rating for specific movie """
    return crud_rate.apply_user_rating(db=db, req_rating=req_rating)


@app.get("/recommend/content_based/{req_movie_id}", tags=["recommendations"])
async def get_rcm_content_based(req_movie_id: int, db: Session = Depends(get_db)):
    """ Return rcmmnd list based on similarity for specific movie """
    recommended_id_list = rcmmnd.content_based_filtering(movie_id=req_movie_id, no_of_movies=15)
    recommended_movie_list = crud_movie.get_movies_by_list_id(db=db, movie_id_list=recommended_id_list)
    return recommended_movie_list


@app.get("/recommend/content_based_last", tags=["recommendations"])
async def get_rcm_content_based_last(token: JWTBearer = Depends(JWTBearer()), db: Session = Depends(get_db)):
    """ Return rcmmnd list based on similarity for last watched movie by user """
    user = crud_user.get_user_from_payload(db=db, payload=token.get_payload())
    latest_watched_movie_id = crud_movie.latest_movie_id_watched_by_user(db=db, user_id=user.id)
    recommended_list = rcmmnd.content_based_filtering(movie_id=latest_watched_movie_id, no_of_movies=15)

    latest_watched_movie = crud_movie.get_movie(db=db, movie_id=latest_watched_movie_id)
    recommended_list = crud_movie.get_movies_by_list_id(db=db, movie_id_list=recommended_list)

    return {
        'latest_movie': latest_watched_movie,
        'recommended_list': recommended_list
    }


@app.get("/recommend/rating_based/{req_movie_id}", tags=["recommendations"])
async def get_rcm_rating_based(req_movie_id: int, db: Session = Depends(get_db)):
    """ Return rcmmnd list based on rating for specific movie """
    recommended_id_list = rcmmnd.based_on_ratings(movie_id=req_movie_id, no_of_movies=15)
    recommended_movie_list = crud_movie.get_movies_by_list_id(db=db, movie_id_list=recommended_id_list)
    return recommended_movie_list


@app.get("/recommend/rating_based_last", tags=["recommendations"])
async def get_rcm_rating_based_last(token: JWTBearer = Depends(JWTBearer()), db: Session = Depends(get_db)):
    """ Return rcmmnd list based on movie rating for last watched movie by user"""
    user = crud_user.get_user_from_payload(db=db, payload=token.get_payload())
    latest_watched_movie_id = crud_movie.latest_movie_id_watched_by_user(db=db, user_id=user.id)
    recommended_id_list = rcmmnd.based_on_ratings(movie_id=latest_watched_movie_id, no_of_movies=15)

    latest_watched_movie = crud_movie.get_movie(db=db, movie_id=latest_watched_movie_id)
    recommended_movie_list = crud_movie.get_movies_by_list_id(db=db, movie_id_list=recommended_id_list)

    return {
        'latest_movie': latest_watched_movie,
        'recommended_list': recommended_movie_list
    }


@app.get("/recommend/collaborative_filtering", tags=["recommendations"])
async def get_rcm_collaborative_filtering(token: JWTBearer = Depends(JWTBearer()), db: Session = Depends(get_db)):
    """ Return rcmmnd list based on similarity between users """
    user = crud_user.get_user_from_payload(db=db, payload=token.get_payload())
    recommended_id_list = rcmmnd.collaborative_filtering(user_id=user.id, no_of_movies=15)
    recommended_movie_list = crud_movie.get_movies_by_list_id(db=db, movie_id_list=recommended_id_list)
    return recommended_movie_list


# TESTOWE !!!
@app.get("/test", tags=["test"])
async def test_get_no_protected():
    return {"dump": "GET: no protected dump"}


@app.post("/test", tags=["test"])
async def test_post_no_protected():
    return {"dump": "POST: no protected dump"}


@app.get("/protected", dependencies=[Depends(JWTBearer())], tags=["test"])
async def test_protected():
    return {"dump": "GET: something protected"}


@app.get("/protected/user/{test}", tags=["test"])
async def test_protected_user(
        test: str,
        token_object: JWTBearer = Depends(JWTBearer()),
        db: Session = Depends(get_db)
):
    payload = token_object.get_payload()
    # user = db.query(User).filter(User.email == payload['user_id']).first()
    user = crud_user.get_user_from_payload(db=db, payload=payload)
    return {'AUTORIZED_user': user, 'test_string': test}


@app.post("/protected", dependencies=[Depends(JWTBearer())], tags=["test"])
async def test_protected():
    return {"dump": "POST: something protected"}


if __name__ == "__main__":
    uvicorn.run("app:app", host="localhost", port=5000, reload=True, log_level="info")
    # uvicorn.run(app, host=DEFAULT_HOST, port=DEFAULT_HOST_PORT)
