from apps.characters.models import CharacterVariant


def eligible_rules(rules, *, at):
    # Rule rows are already locked. Catalog visibility is a fresh query snapshot;
    # later catalog changes do not revoke an already decided encounter.
    candidates = [
        rule
        for rule in rules
        if rule.is_active
        and (rule.starts_at is None or rule.starts_at <= at)
        and (rule.ends_at is None or at < rule.ends_at)
    ]
    active_variants = set(
        CharacterVariant.objects.filter(
            id__in=[rule.character_variant_id for rule in candidates],
            is_active=True,
            character__is_active=True,
        ).values_list("id", flat=True)
    )
    return [rule for rule in candidates if rule.character_variant_id in active_variants]
