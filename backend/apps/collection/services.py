from .models import CollectionEntry


def create_collection_entry(*, capture_result):
    """Called inside the capture transaction; ownership comes only from the encounter."""
    encounter = capture_result.encounter
    return CollectionEntry.objects.create(
        capture_result=capture_result,
        user_id=encounter.user_id,
        character_variant_id=encounter.character_variant_id,
    )
