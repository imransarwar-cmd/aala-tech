"""Pure upgrade decisions. Existing managers are never silently replaced."""


def legacy_assignment_plan(current_manager_id, legacy_users):
    """Return (target_manager_id_or_None, status, reason).

    legacy_users contains dictionaries with id, active, share and company_ok.
    Selecting one of multiple people would be arbitrary, so it is never done.
    """
    users = {user['id']: user for user in legacy_users}
    if not users:
        return None, 'no_legacy_assignment', 'Nothing to migrate.'
    if current_manager_id:
        if set(users) == {current_manager_id}:
            return None, 'already_native_manager', 'The same person is already Project Manager.'
        return None, 'review_existing_manager', (
            'Existing Project Manager kept. Other legacy users no longer receive '
            'whole-project access; review their individual task assignments.'
        )
    if len(users) != 1:
        return None, 'review_multiple_users', (
            'Project Manager is blank and several legacy users exist. '
            'HOD must select one responsible Project Manager.'
        )
    user = next(iter(users.values()))
    if not user.get('active') or user.get('share') or not user.get('company_ok'):
        return None, 'review_ineligible_user', (
            'The sole legacy user is archived, external, or does not have access '
            'to the project company. No new manager was selected.'
        )
    return user['id'], 'migrated', 'Sole eligible legacy user moved to the blank Project Manager field.'
