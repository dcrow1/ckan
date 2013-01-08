import datetime

from sqlalchemy import orm, types, Column, Table, ForeignKey, desc, or_

import meta
import types as _types
import domain_object

__all__ = ['Activity', 'activity_table',
           'ActivityDetail', 'activity_detail_table',
           ]

activity_table = Table(
    'activity', meta.metadata,
    Column('id', types.UnicodeText, primary_key=True, default=_types.make_uuid),
    Column('timestamp', types.DateTime),
    Column('user_id', types.UnicodeText),
    Column('object_id', types.UnicodeText),
    Column('revision_id', types.UnicodeText),
    Column('activity_type', types.UnicodeText),
    Column('data', _types.JsonDictType),
    )

activity_detail_table = Table(
    'activity_detail', meta.metadata,
    Column('id', types.UnicodeText, primary_key=True, default=_types.make_uuid),
    Column('activity_id', types.UnicodeText, ForeignKey('activity.id')),
    Column('object_id', types.UnicodeText),
    Column('object_type', types.UnicodeText),
    Column('activity_type', types.UnicodeText),
    Column('data', _types.JsonDictType),
    )

class Activity(domain_object.DomainObject):

    def __init__(self, user_id, object_id, revision_id, activity_type,
            data=None):
        self.id = _types.make_uuid()
        self.timestamp = datetime.datetime.now()
        self.user_id = user_id
        self.object_id = object_id
        self.revision_id = revision_id
        self.activity_type = activity_type
        if data is None:
            self.data = {}
        else:
            self.data = data

meta.mapper(Activity, activity_table)


class ActivityDetail(domain_object.DomainObject):

    def __init__(self, activity_id, object_id, object_type, activity_type,
            data=None):
        self.activity_id = activity_id
        self.object_id = object_id
        self.object_type = object_type
        self.activity_type = activity_type
        if data is None:
            self.data = {}
        else:
            self.data = data


meta.mapper(ActivityDetail, activity_detail_table, properties = {
    'activity':orm.relation ( Activity, backref=orm.backref('activity_detail'))
    })


def _activities_at_offset(q, limit, offset):
    '''Return an SQLAlchemy query for all activities at an offset with a limit.

    '''
    q = q.order_by(desc(Activity.timestamp))
    if offset:
        q = q.offset(offset)
    if limit:
        q = q.limit(limit)
    return q.all()

def _activities_from_user_query(user_id):
    '''Return an SQLAlchemy query for all activities from user_id.'''
    q = meta.Session.query(Activity)
    q = q.filter(Activity.user_id == user_id)
    return q


def _activities_about_user_query(user_id):
    '''Return an SQLAlchemy query for all activities about user_id.'''
    q = meta.Session.query(Activity)
    q = q.filter(Activity.object_id == user_id)
    return q


def _user_activity_query(user_id):
    '''Return an SQLAlchemy query for all activities from or about user_id.'''
    q = _activities_from_user_query(user_id)
    q = q.union(_activities_about_user_query(user_id))
    return q


def user_activity_list(user_id, limit, offset):
    '''Return user_id's public activity stream.

    Return a list of all activities from or about the given user, i.e. where
    the given user is the subject or object of the activity, e.g.:

    "{USER} created the dataset {DATASET}"
    "{OTHER_USER} started following {USER}"
    etc.

    '''
    q = _user_activity_query(user_id)
    return _activities_at_offset(q, limit, offset)


def _package_activity_query(package_id):
    '''Return an SQLAlchemy query for all activities about package_id.

    '''
    q = meta.Session.query(Activity)
    q = q.filter_by(object_id=package_id)
    return q


def package_activity_list(package_id, limit, offset):
    '''Return the given dataset (package)'s public activity stream.

    Returns all activities  about the given dataset, i.e. where the given
    dataset is the object of the activity, e.g.:

    "{USER} created the dataset {DATASET}"
    "{USER} updated the dataset {DATASET}"
    etc.

    '''
    q = _package_activity_query(package_id)
    return _activities_at_offset(q, limit, offset)


def _group_activity_query(group_id):
    '''Return an SQLAlchemy query for all activities about group_id.

    Returns a query for all activities whose object is either the group itself
    or one of the group's datasets.

    '''
    import ckan.model as model

    group = model.Group.get(group_id)
    if not group:
        # Return a query with no results.
        return meta.Session.query(Activity).filter("0=1")

    dataset_ids = [dataset.id for dataset in group.packages()]

    q = meta.Session.query(Activity)
    if dataset_ids:
        q = q.filter(or_(Activity.object_id == group_id,
            Activity.object_id.in_(dataset_ids)))
    else:
        q = q.filter(Activity.object_id == group_id)
    return q


def group_activity_list(group_id, limit, offset):
    '''Return the given group's public activity stream.

    Returns all activities where the given group or one of its datasets is the
    object of the activity, e.g.:

    "{USER} updated the group {GROUP}"
    "{USER} updated the dataset {DATASET}"
    etc.

    '''
    q = _group_activity_query(group_id)
    return _activities_at_offset(q, limit, offset)


def _activites_from_users_followed_by_user_query(user_id):
    '''Return a query for all activities from users that user_id follows.'''
    import ckan.model as model
    q = meta.Session.query(Activity)
    q = q.join(model.UserFollowingUser,
            model.UserFollowingUser.object_id == Activity.user_id)
    q = q.filter(model.UserFollowingUser.follower_id == user_id)
    return q


def _activities_from_datasets_followed_by_user_query(user_id):
    '''Return a query for all activities from datasets that user_id follows.'''
    import ckan.model as model
    q = meta.Session.query(Activity)
    q = q.join(model.UserFollowingDataset,
            model.UserFollowingDataset.object_id == Activity.object_id)
    q = q.filter(model.UserFollowingDataset.follower_id == user_id)
    return q


def _activities_from_groups_followed_by_user_query(user_id):
    '''Return a query for all activities about groups the given user follows.

    Return a query for all activities about the groups the given user follows,
    or about any of the group's datasets. This is the union of
    _group_activity_query(group_id) for each of the groups the user follows.

    '''
    import ckan.model as model

    # Get a list of the group's that the user is following.
    follower_objects = model.UserFollowingGroup.followee_list(user_id)
    if not follower_objects:
        # Return a query with no results.
        return meta.Session.query(Activity).filter("0=1")

    q = _group_activity_query(follower_objects[0].object_id)
    q = q.union_all(*[_group_activity_query(follower.object_id)
        for follower in follower_objects[1:]])
    return q


def _activities_from_everything_followed_by_user_query(user_id):
    '''Return a query for all activities from everything user_id follows.'''
    q = _activites_from_users_followed_by_user_query(user_id)
    q = q.union(_activities_from_datasets_followed_by_user_query(user_id))
    q = q.union(_activities_from_groups_followed_by_user_query(user_id))
    return q


def activities_from_everything_followed_by_user(user_id, limit, offset):
    '''Return activities from everything that the given user is following.

    Returns all activities where the object of the activity is anything
    (user, dataset, group...) that the given user is following.

    '''
    q = _activities_from_everything_followed_by_user_query(user_id)
    return _activities_at_offset(q, limit, offset)


def _dashboard_activity_query(user_id):
    '''Return an SQLAlchemy query for user_id's dashboard activity stream.'''
    q = _activities_from_user_query(user_id)
    q = q.union(_activities_about_user_query(user_id),
                _activites_from_users_followed_by_user_query(user_id),
                _activities_from_datasets_followed_by_user_query(user_id),
                _activities_from_groups_followed_by_user_query(user_id))
    return q

def dashboard_activity_list(user_id, limit, offset):
    '''Return the given user's dashboard activity stream.

    Returns activities from the user's public activity stream, plus
    activities from everything that the user is following.

    This is the union of user_activity_list(user_id) and
    activities_from_everything_followed_by_user(user_id).

    '''
    q = _dashboard_activity_query(user_id)
    return _activities_at_offset(q, limit, offset)

def _changed_packages_activity_query():
    '''Return an SQLAlchemyu query for all changed package activities.

    Return a query for all activities with activity_type '*package', e.g.
    'new_package', 'changed_package', 'deleted_package'.

    '''
    q = meta.Session.query(Activity)
    q = q.filter(Activity.activity_type.endswith('package'))
    return q


def recently_changed_packages_activity_list(limit, offset):
    '''Return the site-wide stream of recently changed package activities.

    This activity stream includes recent 'new package', 'changed package' and
    'deleted package' activities for the whole site.

    '''
    q = _changed_packages_activity_query()
    return _activities_at_offset(q, limit, offset)
