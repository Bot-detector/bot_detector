from sqlalchemy import BigInteger, Column, Integer, SmallInteger, TIMESTAMP
from src.core.database.database import Base

class Report(Base):
    __tablename__ = "Reports"

    ID = Column(BigInteger, primary_key=True, autoincrement=True)
    created_at = Column(TIMESTAMP)
    reportedID = Column(Integer)
    reportingID = Column(Integer)
    region_id = Column(Integer)
    x_coord = Column(Integer)
    y_coord = Column(Integer)
    z_coord = Column(Integer)
    timestamp = Column(TIMESTAMP)
    manual_detect = Column(SmallInteger)
    on_members_world = Column(Integer)
    on_pvp_world = Column(SmallInteger)
    world_number = Column(Integer)
    equip_head_id = Column(Integer)
    equip_amulet_id = Column(Integer)
    equip_torso_id = Column(Integer)
    equip_legs_id = Column(Integer)
    equip_boots_id = Column(Integer)
    equip_cape_id = Column(Integer)
    equip_hands_id = Column(Integer)
    equip_weapon_id = Column(Integer)
    equip_shield_id = Column(Integer)
    equip_ge_value = Column(BigInteger)
