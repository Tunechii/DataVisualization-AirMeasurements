from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime

Base = declarative_base()

class AirQualityReading(Base):
    __tablename__ = "air_quality_readings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    city = Column(String)
    parameter = Column(String)  # e.g., O₃, CO, NO₂
    value = Column(Float)
    time = Column(DateTime)
    location = Column(String)

# Create database connection
engine = create_engine("sqlite:///air_quality.db")
Base.metadata.create_all(engine)

SessionLocal = sessionmaker(bind=engine)
