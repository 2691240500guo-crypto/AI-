from datetime import datetime
from sqlalchemy import Column, DateTime, Integer, JSON, String, Text
from app.core.database import Base

class SocialPost(Base):
    __tablename__ = "social_posts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    user_name = Column(String(100), nullable=False, default="匿名用户")
    content = Column(Text, nullable=False)
    images = Column(JSON, default=list)
    tags = Column(JSON, default=list)
    likes_count = Column(Integer, default=0)
    comments_count = Column(Integer, default=0)
    status = Column(String(20), default="published", index=True)
    created_at = Column(DateTime, default=datetime.now, index=True)

class SocialComment(Base):
    __tablename__ = "social_comments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(Integer, nullable=False, index=True)
    user_id = Column(String(64), nullable=False)
    user_name = Column(String(100), nullable=False, default="匿名用户")
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.now)

class SocialLike(Base):
    __tablename__ = "social_likes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    post_id = Column(Integer, nullable=False, index=True)
    user_id = Column(String(64), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.now)

class SocialFollow(Base):
    __tablename__ = "social_follows"
    id = Column(Integer, primary_key=True, autoincrement=True)
    follower_id = Column(String(64), nullable=False, index=True)
    following_id = Column(String(64), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.now)
