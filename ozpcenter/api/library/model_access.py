"""
Library Model Access
"""
import logging

from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist

from ozpcenter import models
from ozpcenter import utils
import ozpcenter.api.listing.model_access as listing_model_access
import ozpcenter.api.notification.model_access as notification_model_access
import ozpcenter.model_access as generic_model_access


# Get an instance of a logger
logger = logging.getLogger('ozp-center.' + str(__name__))


def get_all_library_entries():
    """
    Get all ApplicationLibrary objects

    Cache:
        Key: library_entries

    Return:
        [ApplicationLibraryEntry]: List of All ApplicationLibrary Entry Objects
    """
    key = 'library_entries'
    data = cache.get(key)
    if data is None:
        try:
            data = models.ApplicationLibraryEntry.objects.filter(listing__is_deleted=False).all()
            cache.set(key, data)
            return data
        except ObjectDoesNotExist:
            return None
    else:
        return data


def get_library_entry_by_id(library_entry_id):
    """
    Get ApplicationLibrary by library_entry_id

    Cache:
        Key: library:<library_entry_id>

    Args:
        library_entry_id (int): library_entry_id for entry

    Return:
        ApplicationLibraryEntry: Get an ApplicationLibrary Entry Object based on library_entry_id
    """
    key = 'library:{0!s}'.format(library_entry_id)
    data = cache.get(key)
    if data is None:
        try:
            data = models.ApplicationLibraryEntry.objects.filter(listing__is_deleted=False).get(id=library_entry_id)
            cache.set(key, data)
            return data
        except ObjectDoesNotExist:
            return None
    else:
        return data


def get_self_application_library(username, listing_type=None, folder_name=None):
    """
    Get the ApplicationLibrary for this user

    Cache:
        Key: app_library:<username>

    Args:
        username (str): username
        listing_type (str) optional: filter by listing type
        folder_name(str) optional: filter by folder_name

    return:
        Queryset(ApplicationLibraryEntry): User's Application Library

    """
    username = utils.make_keysafe(username)
    key = 'app_library({0!s}):{1!s}'.format(listing_type, username)
    data = cache.get(key)
    if data is None:
        try:
            data = models.ApplicationLibraryEntry.objects
            data = data.filter(owner__user__username=username)
            data = data.filter(listing__is_enabled=True)
            data = data.filter(listing__is_deleted=False)

            if listing_type:
                data = data.filter(listing__listing_type__title=listing_type)

            if folder_name:
                data = data.filter(folder=folder_name)

            cache.set(key, data)
            return data
        except ObjectDoesNotExist:
            return None
    else:
        return data


def create_self_user_library_entry(username, listing_id, folder_name=None):
    """
    Create ApplicationLibrary Entry

    Args:
        username (str): the username to create a library entry for (Bookmark)
        listing_id (str): the id of the listing
        folder_name (str) optional: the name of the folder

    Return:
        ApplicationLibrary: New Entry of ApplicationLibrary

    Raise:
        Exception: if profile was not found based on username or
            or listing was not found based on listing_id
    """
    listing = listing_model_access.get_listing_by_id(username, listing_id)
    owner = generic_model_access.get_profile(username)

    if not listing or not owner:
        raise Exception('Listing or user not found')

    logger.debug('Adding bookmark for listing[{0!s}], user[{1!s}]'.format(listing.title, username), extra={'user': username})

    entry = models.ApplicationLibraryEntry(listing=listing, owner=owner, folder=folder_name)
    entry.save()
    return entry


def import_bookmarks(current_username, peer_bookmark_notification_id):
    """
    Import Bookmarks to current user

    Steps:
        * Return Peer Bookmark Notification Entry {notification_entry} using {peer_bookmark_notification_id}
            * If not found add to error list
        * Validate {notification_entry} is a 'PEER.BOOKMARK' notification
            * If fail add error to error list
        * Extract {peer} from {notification_entry}
        * Validate {peer.user.username} is same current user's username {current_username}
            * If fail add error to error list
        * Validation on {peer.folder_name} for current user
            if folder_name already exist for that user then increament folder_name by 1
                (ex 'folder name 1' to 'folder name 1 (1)')
                (ex 'cool (1)' to 'cool (2)')
        * Iterate {peer._bookmark_listing_ids}
            create_self_user_library_entry({current_username}, {peer._bookmark_listing_ids.id})
        * Dismiss {notification_entry}

    Args:
        username: dictionary
        peer_bookmark_notification_id (int): peer bookmark notification id

    Returns:
        [ models.ApplicationLibraryEntry, ...]
    """
    validated_data = []
    errors = []

    notification_entry = notification_model_access.get_notification_by_id(current_username, peer_bookmark_notification_id)

    if not notification_entry:
        errors.append('Could not find Notification Entry')
        return errors, None

    notification_entry_type = notification_entry.notification_type()

    if not notification_entry_type == 'PEER.BOOKMARK':
        errors.append('Notification Entry should be \'PEER.BOOKMARK\' but it is \'{0}\''.format(notification_entry_type))
        return errors, None

    peer_data = notification_entry.peer

    peer_username = peer_data.get('user', {}).get('username')
    peer_folder_name = peer_data.get('folder_name')
    peer_bookmark_list = peer_data.get('_bookmark_listing_ids', [])

    if not peer_username == current_username:
        errors.append('Target username does not match current user\'s username')

    if not peer_folder_name:
        errors.append('Could not find folder_name entry')

    if not peer_bookmark_list:
        errors.append('Could not find peer bookmark list entry')

    # TODO Validate Folder Name

    if errors:
        return errors, None

    for current_bookmark_listing_id in peer_bookmark_list:
        try:
            validated_data.append(create_self_user_library_entry(current_username, current_bookmark_listing_id, peer_folder_name))
        except Exception:
            pass  # ignore exception Exception('Listing or user not found')

    notification_model_access.dismiss_notification(notification_entry, current_username)

    if errors:
        return errors, None
    return None, validated_data


def batch_update_user_library_entry(username, data):
    """
    Update ALL of the user's library entries

    Used to move library entries into different folders for HUD

    Args:
        username (str): username
        data (List<Dict>): Payload
            [
                {
                    "listing": {
                        "id": 1
                    },
                    "folder": "folderName" (or null),
                    "id": 2
                },
                {
                    "listing": {
                        "id": 2
                    },
                    "folder": "folderName" (or null),
                    "id": 1
                }
            ]

        Return:
            List<Dict>: payload data

        Raise:
            Exception: if validation fails
    """
    validated_data = []
    errors = []
    # validate input
    for data_entry in data:
        error = False
        # Validates Listing

        new_data_entry = {}

        if 'listing' not in data_entry:
            errors.append('Missing listing from data entry')
            error = True
        else:
            listing_id = data_entry.get('listing', {}).get('id')
            listing_obj = listing_model_access.get_listing_by_id(username, listing_id)
            if not listing_obj:
                errors.append('Listing obj not found')
                error = True
            else:
                new_data_entry['listing'] = listing_obj

        if 'id' not in data_entry:
            errors.append('Missing id from data entry')
            error = True
        else:
            new_data_entry['id'] = data_entry['id']

        if 'folder' not in data_entry:
            new_data_entry['folder'] = None
        else:
            new_data_entry['folder'] = data_entry['folder']

        if not error:
            validated_data.append(new_data_entry)

    if errors:
        return errors, None

    for data_entry in validated_data:
        instance = get_library_entry_by_id(data_entry['id'])
        instance.folder = data_entry['folder']
        instance.listing = data_entry['listing']
        instance.save()

    return None, data
