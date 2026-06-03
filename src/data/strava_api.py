"""Strava API client for listing activities and downloading activity streams."""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
import requests

from .activity import Activity
from src.constants import STRAVA_TOKENS_PATH


class StravaClientError(Exception):
    """Raised for errors interacting with the Strava API."""


class StravaClient:
    """Client for requesting Strava activity metadata and streams."""

    TOKEN_FILE = STRAVA_TOKENS_PATH
    BASE_URL = 'https://www.strava.com/api/v3'
    STREAM_KEYS = 'time,altitude,heartrate,cadence,watts,velocity_smooth,distance'

    def __init__(self, access_token: Optional[str] = None):
        self.tokens = self._load_tokens()
        if access_token:
            self.tokens['access_token'] = access_token
        self.access_token = self.tokens['access_token']
        self.headers = {'Authorization': f'Bearer {self.access_token}'}
        self._check_and_refresh_token()

    def _load_tokens(self) -> Dict[str, Any]:
        if self.TOKEN_FILE.exists():
            with open(self.TOKEN_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data

        raise StravaClientError(
            f'Unable to find Strava access token. Create {STRAVA_TOKENS_PATH} with {{"access_token": "...", "refresh_token": "..."}}.'
        )

    def _check_and_refresh_token(self):
        try:
            response = requests.get(
                f'{self.BASE_URL}/athlete',
                headers=self.headers,
                timeout=10,
            )
            if response.status_code == 401:
                self._refresh_token()
        except requests.RequestException:
            # If there's a network error, we can't refresh, so proceed anyway
            pass

    def _refresh_token(self):
        client_id = self.tokens.get('strava_client_id')
        client_secret = self.tokens.get('strava_client_secret')
        if not client_id or not client_secret:
            raise StravaClientError('Client ID and Client Secret required for token refresh. Include strava_client_id and strava_client_secret in strava_tokens.json.')
        refresh_token = self.tokens.get('refresh_token')
        if not refresh_token:
            raise StravaClientError('Refresh token not found in strava_tokens.json.')

        response = requests.post(
            'https://www.strava.com/api/v3/oauth/token',
            data={
                'client_id': client_id,
                'client_secret': client_secret,
                'grant_type': 'refresh_token',
                'refresh_token': refresh_token,
            },
            timeout=30,
        )
        if response.status_code == 200:
            new_tokens = response.json()
            self.tokens.update(new_tokens)
            self._save_tokens()
            self.access_token = self.tokens['access_token']
            self.headers = {'Authorization': f'Bearer {self.access_token}'}
        else:
            raise StravaClientError(f'Failed to refresh token: {response.status_code} {response.text}')

    def _save_tokens(self):
        self.TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(self.TOKEN_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.tokens, f, indent=2)

    def list_activities(self, after: datetime) -> List[Dict[str, Any]]:
        """List activities on Strava after a given date."""
        activities: List[Dict[str, Any]] = []
        page = 1
        per_page = 200

        while True:
            params = {
                'after': int(after.timestamp()),
                'per_page': per_page,
                'page': page,
            }
            response = requests.get(
                f'{self.BASE_URL}/athlete/activities',
                headers=self.headers,
                params=params,
                timeout=30,
            )
            if response.status_code != 200:
                raise StravaClientError(
                    f'Failed to load Strava activities: {response.status_code} {response.text}'
                )

            page_data = response.json()
            if not page_data:
                break

            activities.extend(page_data)
            if len(page_data) < per_page:
                break
            page += 1

        return activities

    def download_activity(self, activity_id: int) -> Activity:
        """Download a single activity and convert it to an Activity object."""
        self._check_and_refresh_token()
        metadata = self._get_activity_detail(activity_id)
        streams = self._get_activity_streams(activity_id)
        return self._build_activity(metadata, streams)

    def _get_activity_detail(self, activity_id: int) -> Dict[str, Any]:
        try:
            response = requests.get(
                f'{self.BASE_URL}/activities/{activity_id}',
                headers=self.headers,
                timeout=30,
            )
        except requests.RequestException as e:
            raise StravaClientError(f'Failed to fetch activity detail: {e}') from e
        if response.status_code != 200:
            raise StravaClientError(
                f'Failed to fetch activity detail: {response.status_code} {response.text}'
            )
        return response.json()

    def _get_activity_streams(self, activity_id: int) -> Dict[str, List[Any]]:
        try:
            response = requests.get(
                f'{self.BASE_URL}/activities/{activity_id}/streams',
                headers=self.headers,
                params={'keys': self.STREAM_KEYS, 'key_by_type': 'true'},
                timeout=30,
            )
        except requests.RequestException as e:
            raise StravaClientError(f'Failed to fetch activity streams: {e}') from e
        if response.status_code != 200:
            raise StravaClientError(
                f'Failed to fetch activity streams: {response.status_code} {response.text}'
            )

        return response.json()

    def _build_activity(self, metadata: Dict[str, Any], streams: Dict[str, Any]) -> Activity:
        start_date = metadata.get('start_date_local') or metadata.get('start_date')
        if not start_date:
            raise StravaClientError('Activity metadata is missing start time.')

        start_time = pd.to_datetime(start_date)
        if start_time.tzinfo is not None:
            start_time = start_time.tz_convert(None)

        time_stream = streams.get('time')
        if not time_stream:
            raise StravaClientError('No time stream available for activity.')

        time_values = time_stream.get('data') if isinstance(time_stream, dict) else time_stream
        if not time_values:
            raise StravaClientError('No time values found in the time stream.')

        data = {'timestamp': start_time + pd.to_timedelta(time_values, unit='s')}
        field_mapping = {
            'distance': 'distance',
            'altitude': 'altitude',
            'heartrate': 'heart_rate',
            'cadence': 'cadence',
            'watts': 'power',
            'velocity_smooth': 'speed',
        }

        for stream_key, column_name in field_mapping.items():
            stream = streams.get(stream_key)
            if stream is not None:
                data[column_name] = stream["data"]

        activity = Activity(
            sport=metadata.get('sport') or metadata.get('type') or 'cycling',
            start_time=start_time,
            total_distance=metadata.get('distance'),
            total_elapsed_time=metadata.get('elapsed_time'),
            data=pd.DataFrame(data),
        )

        return activity
