"""
"""
import logging

from rest_framework.decorators import api_view
from rest_framework.decorators import permission_classes
from rest_framework import permissions
from rest_framework import generics, status
from rest_framework.response import Response

import ozpcenter.model_access as model_access
import ozpcenter.api.listing.model_access as listing_model_access
import ozpcenter.api.listing.serializers as listing_serializers
import ozpiwc.hal as hal

# Get an instance of a logger
logger = logging.getLogger('ozp-iwc')

@api_view(['GET'])
@permission_classes((permissions.IsAuthenticated, ))
def ApplicationListView(request, profile_id='0'):
    """
    List of applications
    """
    listing_root_url = hal.get_abs_url_for_iwc(request)
    profile = model_access.get_profile(request.user.username)
    data = hal.create_base_structure(request)
    applications = listing_model_access.get_listings(profile.user.username)
    items = []
    for i in applications:
        item = {"href": '%slisting/%s/' % (listing_root_url, i.id)}
        items.append(item)
    data["item"] = items

    return Response(data)

@api_view(['GET'])
@permission_classes((permissions.IsAuthenticated, ))
def ApplicationView(request, app_id='0'):
    """
    Single application
    """
    listing_root_url = hal.get_abs_url_for_iwc(request)
    profile = model_access.get_profile(request.user.username)

    # TODO: only include the fields that are necessary for IWC. This will also
    # allow us to sever ties with ozpcenter.api.listing.serializers

    # This minimal definition of what a Listing object must have should be
    # advertised so that others can use IWC with their own systems
    queryset = listing_model_access.get_listing_by_id(profile.user.username, app_id)
    serializer = listing_serializers.ListingSerializer(queryset,
            context={'request': request})
    data = serializer.data
    data = hal.add_hal_structure(data, request)

    # TODO probably remove this
    data[hal.APPLICATION_ACTIVITY_REL] = {
        "href": '%slisting/%s/activity/' % (listing_root_url, app_id)
    }

    # TODO probably remove this
    data[hal.APPLICATION_REVIEW_REL] = {
        "href": '%slisting/%s/review/' % (listing_root_url, app_id)
    }

    return Response(data)

@api_view(['GET'])
@permission_classes((permissions.IsAuthenticated, ))
def SystemView(request):
    """
    System view - TODO
    """
    listing_root_url = hal.get_abs_url_for_iwc(request)
    profile = model_access.get_profile(request.user.username)

    data = hal.create_base_structure(request)
    data["version"] = "1.0"
    data["name"] = "TBD"
    return Response(data)
