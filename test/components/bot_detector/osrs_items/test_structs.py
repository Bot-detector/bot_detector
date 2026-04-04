from bot_detector.osrs_items.structs import ItemStruct


def test_item_struct_creation():
    item = ItemStruct(
        id=1,
        name="Bronze dagger",
        examine="A short dagger made of bronze.",
        members=False,
        lowalch=1,
        highalch=2,
        limit=40,
        value=10,
        icon="bronze_dagger.png",
    )
    assert item.id == 1
    assert item.name == "Bronze dagger"
    assert item.members is False
