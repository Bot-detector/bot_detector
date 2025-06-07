import random
from datetime import datetime, timedelta

from models import (
    Labels,
    PlayerActivity,
    Players,
    PlayerSkill,
    Report,
    ScraperDataV3,
    ScraperPlayerActivity,
    ScraperPlayerSkill,
    session,
)
from sqlalchemy.exc import IntegrityError


def random_date():
    return datetime.utcnow() - timedelta(days=random.randint(0, 365))


def get_labels():
    # Query the labels table to get all id values
    label_ids = session.query(Labels.id).all()
    label_ids = [id[0] for id in label_ids]  # Convert list of tuples to list of ids
    return label_ids


def insert_players(len_players, label_ids: list):
    # Insert data into Players table
    for i in range(len_players):
        print(f"Player_{i}")
        # Check if the player already exists
        existing_player = session.query(Players).filter_by(name=f"Player_{i}").first()
        if not existing_player:
            player = Players(
                name=f"Player_{i}",
                created_at=random_date(),
                updated_at=random_date(),
                possible_ban=random.choice([True, False]),
                confirmed_ban=random.choice([True, False]),
                confirmed_player=random.choice([True, False]),
                label_id=random.choice(label_ids),  # Select a random id from label_ids
                label_jagex=random.randint(0, 2),
                normalized_name=f"Player_{i}",
            )
            session.add(player)
    session.commit()
    return


def insert_reports(len_reports, len_players):
    for i in range(1, len_reports + 1):
        print(f"Report_{i}")
        # pick random player
        reporter = random.randint(1, len_players)
        reported = random.randint(1, len_players)

        if reporter == reported:
            reported = random.randint(1, len_players)

        try:
            session.add(
                Report(
                    created_at=random_date(),
                    reportedID=reporter,
                    reportingID=reported,
                    region_id=random.randint(1, 30000),
                    x_coord=random.randint(1, 30000),
                    y_coord=random.randint(1, 30000),
                    z_coord=random.randint(1, 30000),
                    timestamp=random_date(),
                    manual_detect=random.choice([0, 1]),
                    on_members_world=random.choice([0, 1]),
                    on_pvp_world=random.choice([0, 1]),
                    world_number=random.randint(1, 300),
                    equip_head_id=random.randint(1, 30000),
                    equip_amulet_id=random.randint(1, 30000),
                    equip_torso_id=random.randint(1, 30000),
                    equip_legs_id=random.randint(1, 30000),
                    equip_boots_id=random.randint(1, 30000),
                    equip_cape_id=random.randint(1, 30000),
                    equip_hands_id=random.randint(1, 30000),
                    equip_weapon_id=random.randint(1, 30000),
                    equip_shield_id=random.randint(1, 30000),
                    equip_ge_value=random.randint(1, 2000000000),
                )
            )
        except IntegrityError:
            session.rollback()  # Rollback the transaction if a duplicate entry is encountered
        finally:
            session.commit()


def generate_random_scraper_data(len_scrapers, len_players, skill_ids, activity_ids):
    # TODO:
    ...


def main():
    len_players = 250
    label_ids = get_labels()
    insert_players(len_players, label_ids)
    insert_reports(len_reports=10_000, len_players=len_players)


if __name__ == "__main__":
    main()
